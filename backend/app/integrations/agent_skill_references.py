"""Concrete selection in original Agent metadata; current native facts authorize reads."""

import hashlib
import os
import re
from pathlib import Path
from typing import Literal

import yaml
from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from app.models.agents import CustomAgent
from deerflow.database.models import Tenant, TenantMembership, TenantSkill
from deerflow.skills import get_skills_root_path
from deerflow.skills.resource_deletion_files import OwnedRemoval
from deerflow.skills.resource_identity import public_resource_id, registered_resource_id, resource_directory

KEY = "prismos_skill_references"


class SkillResourceReference(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=64, pattern=r"^[a-z0-9_-]+$")
    scope: Literal["global", "tenant", "personal"]
    resource_id: str = Field(min_length=1, max_length=160)


class SkillBinding(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: Literal[1] = 1
    mode: Literal["all", "selected", "unresolved"]
    legacy_names: list[str] = Field(default_factory=list, max_length=128)
    resources: list[SkillResourceReference] = Field(default_factory=list, max_length=128)


def binding(agent):
    meta = agent.meta_info or {}
    if not isinstance(meta, dict):
        raise ValueError("Skill reference configuration is unavailable")
    if KEY not in meta:
        return None
    return SkillBinding.model_validate(meta[KEY])


def _public_directories(root):
    parent = root / "public"
    if parent.resolve() != parent or not parent.is_dir():
        return
    for current, dirs, files in os.walk(parent, followlinks=False):
        dirs[:] = sorted(name for name in dirs if not name.startswith(".") and not (Path(current) / name).is_symlink())
        if "SKILL.md" in files:
            yield Path(current)


def _read_main(directory):
    removal = OwnedRemoval(directory.parent)
    try:
        tree = removal.snapshot(directory.name)
        expected = tree["files"].get("SKILL.md")
        if expected is None:
            raise ValueError("Skill main file unavailable")
        fd = os.open(directory.name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=removal.fd)
        try:
            if [os.fstat(fd).st_dev, os.fstat(fd).st_ino] != tree["directories"]["."]["identity"]:
                raise ValueError("Skill directory changed")
            main = os.open("SKILL.md", os.O_RDONLY | os.O_NOFOLLOW, dir_fd=fd)
            with os.fdopen(main, "rb") as file:
                info = os.fstat(file.fileno())
                data = file.read()
                if [info.st_dev, info.st_ino] != expected["identity"] or hashlib.sha256(data).hexdigest() != expected["sha256"]:
                    raise ValueError("Skill main file changed")
            if removal.snapshot(directory.name) != tree:
                raise ValueError("Skill members changed")
        finally:
            os.close(fd)
        content = data.decode("utf-8")
        front = re.match(r"^---\s*\n(.*?)\n---\s*\n", content, re.DOTALL)
        meta = yaml.safe_load(front.group(1)) if front else None
        if not isinstance(meta, dict) or not isinstance(meta.get("name"), str) or not isinstance(meta.get("description"), str):
            raise ValueError("Skill metadata unavailable")
        return meta, content[front.end() :], expected["sha256"]
    finally:
        removal.close()


async def resolve_reference(session, tenant, actor, shared_agent, reference, *, use=False, root=None):
    root = (root or get_skills_root_path()).resolve()
    owner = f"__tenant_shared_skill__:{tenant}" if reference.scope == "tenant" else actor
    if reference.scope == "personal" and shared_agent:
        raise HTTPException(403, "Shared Agent cannot bind a personal resource")
    if reference.scope == "global":
        directory = next((p for p in _public_directories(root) if public_resource_id(p.relative_to(root / "public").as_posix()) == reference.resource_id), None)
        if directory is None:
            raise HTTPException(409, "Selected public source is unavailable")
        directory = resource_directory(root, tenant, actor, {"scope": "global", "install_dir": str(directory)})
        override = (
            (await session.exec(select(TenantSkill).where(TenantSkill.tenant_id == tenant, TenantSkill.user_id == f"__tenant_shared_skill__:{tenant}", TenantSkill.name == reference.name, TenantSkill.category == "public"))).scalars().first()
        )
        enabled = override.enabled if override is not None else True
        relative = directory.relative_to(root / "public").as_posix()
        location = "public/" + relative
    else:
        row = (await session.exec(select(TenantSkill).where(TenantSkill.tenant_id == tenant, TenantSkill.user_id == owner, TenantSkill.name == reference.name).with_for_update())).scalars().first()
        if row is None or row.category == "public" or registered_resource_id(row) != reference.resource_id:
            raise HTTPException(409, "Selected registered instance is unavailable or changed")
        directory = resource_directory(root, tenant, actor, {"name": row.name, "scope": reference.scope, "install_dir": row.install_dir, "relative_path": row.relative_path})
        enabled = row.enabled
        location = "custom/" + directory.relative_to(root / "custom").as_posix()
    meta, instructions, digest = _read_main(directory)
    if meta["name"] != reference.name:
        raise HTTPException(409, "Selected instance metadata changed")
    if use and not enabled:
        raise HTTPException(403, "Selected Skill is disabled")
    return {**reference.model_dump(), "description": meta["description"], "instructions": instructions, "file_sha256": digest, "location": location + "/SKILL.md", "enabled": enabled}


async def save_binding(session, agent, tenant, actor, mode, resources, *, explicit, names_changed=False, scope_changed=False):
    try:
        previous = binding(agent)
    except ValueError:
        if not explicit:
            return
        previous = None
    if not explicit:
        if previous is None:
            return
        if names_changed and set(agent.skills or []) != {r.name for r in previous.resources}:
            kept = [r for r in previous.resources if r.name in (agent.skills or [])]
            selected = SkillBinding(mode="unresolved", resources=kept, legacy_names=[n for n in (agent.skills or []) if n not in {r.name for r in kept}])
        elif not scope_changed:
            return
        else:
            selected = previous
    else:
        selected = SkillBinding(mode=mode or "selected", resources=resources or [])
    if selected.mode == "all" and selected.resources:
        raise HTTPException(422, "All-current mode cannot carry fixed resources")
    ids = [(r.scope, r.resource_id) for r in selected.resources]
    if len(set(ids)) != len(ids):
        raise HTTPException(422, "Duplicate concrete resource selection")
    try:
        for reference in selected.resources:
            await resolve_reference(session, tenant, actor, agent.user_id == "tenant-shared", reference)
    except (ValueError, OSError, yaml.YAMLError):
        raise HTTPException(409, "Selected resource contents or ownership cannot be verified") from None
    agent.skills = list(dict.fromkeys([r.name for r in selected.resources] + selected.legacy_names))
    meta = dict(agent.meta_info or {}) if isinstance(agent.meta_info or {}, dict) else {}
    meta[KEY] = selected.model_dump()
    agent.meta_info = meta


def references_instance(agent, resource_id, name):
    try:
        selected = binding(agent)
    except ValueError:
        return name in (agent.skills or [])
    if selected is None:
        return name in (agent.skills or [])
    return (selected.mode == "unresolved" and name in selected.legacy_names) or any(r.resource_id == resource_id for r in selected.resources)


async def current_skill_prompt(session, agent_name, tenant, actor, skill_name=None, resource_id=None, *, root=None, expected_agent_id=None):
    rows = (await session.exec(select(CustomAgent).where(CustomAgent.tenant_id == tenant, CustomAgent.user_id.in_([actor, "tenant-shared"]), CustomAgent.name == agent_name))).scalars().all()
    agent = next((a for a in rows if a.user_id == actor), rows[0] if rows else None)
    if agent is None or not agent.enabled:
        raise HTTPException(403, "Current Agent is unavailable")
    if expected_agent_id is not None and agent.id != expected_agent_id:
        raise HTTPException(409, "Selected Agent identity differs from name-based execution")
    selected = binding(agent)
    if selected is None:
        return None  # Legacy-name migration/use review remains explicit work.
    if selected.mode == "unresolved":
        raise HTTPException(409, "Confirm unresolved Skill source choices before use")
    member = (await session.exec(select(TenantMembership).where(TenantMembership.tenant_id == tenant, TenantMembership.user_id == actor, TenantMembership.status == "active"))).scalars().first()
    tenant_row = await session.get(Tenant, tenant)
    if not agent.enabled or member is None or tenant_row is None or tenant_row.status != "active":
        raise HTTPException(403, "Current Agent or membership is unavailable")
    references = selected.resources
    root = (root or get_skills_root_path()).resolve()
    if selected.mode == "all":
        references = []
        for directory in _public_directories(root):
            try:
                meta, _, _ = _read_main(directory)
                references.append(SkillResourceReference(name=meta["name"], scope="global", resource_id=public_resource_id(directory.relative_to(root / "public").as_posix())))
            except (ValueError, OSError, yaml.YAMLError):
                continue
        native = (
            (await session.exec(select(TenantSkill).where(TenantSkill.tenant_id == tenant, TenantSkill.user_id.in_([actor, f"__tenant_shared_skill__:{tenant}"]), TenantSkill.category != "public", TenantSkill.enabled.is_(True))))
            .scalars()
            .all()
        )
        references += [SkillResourceReference(name=r.name, scope="personal" if r.user_id == actor else "tenant", resource_id=registered_resource_id(r)) for r in native]
    if skill_name or resource_id:
        references = [r for r in references if (not skill_name or r.name == skill_name) and (not resource_id or r.resource_id == resource_id)]
        if len(references) != 1:
            raise HTTPException(409, "Choose one concrete Skill from the Agent selection")
    resolved = []
    for reference in references:
        try:
            # Dynamic all-current uses this actor's authorized resources, not
            # the shared creator's private selection.
            item = await resolve_reference(session, tenant, actor, agent.user_id == "tenant-shared" and selected.mode == "selected", reference, use=True, root=root)
            resolved.append(item)
        except (HTTPException, ValueError, OSError, yaml.YAMLError):
            if selected.mode == "selected" or skill_name or resource_id:
                raise
    sections = []
    for item in resolved:
        sections.append(
            f'<selected_skill name="{item["name"]}" scope="{item["scope"]}" '
            f'resource_id="{item["resource_id"]}" file_sha256="{item["file_sha256"]}">\n'
            f'Location: /mnt/skills/{item["location"]}\n{item["description"]}\n'
            f'{item["instructions"] if len(resolved) == 1 else ""}\n</selected_skill>'
        )
    return "<skill_system>\nUse only these current selected sources; recheck access when loading referenced members.\n" + "\n".join(sections) + "\n</skill_system>"
