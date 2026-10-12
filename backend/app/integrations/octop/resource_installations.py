"""Read-only tenant installation observations; no config ensure or raw output."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

from sqlalchemy import select

from app.integrations.octop.resources import resource_preflight
from app.integrations.octop.skill_packages import SkillPackageUnavailable, prepare_skill_package
from deerflow.database.models import TenantSkill
from deerflow.database.session import get_session_factory
from deerflow.skills.loader import get_skills_root_path
from deerflow.skills.parser import parse_skill_file

_SEGMENT = re.compile(r"^[A-Za-z0-9_-]{1,255}$")


def _contents_match(folder: Path, expected: dict[str, str]) -> str:
    if not folder.is_dir():
        return "files_missing"
    actual = {}
    for path in folder.rglob("*"):
        if path.is_symlink() or path.resolve() != path.absolute():
            return "location_unverified"
        if path.is_file() and path.suffix != ".pyc":
            actual[path.relative_to(folder).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    return "source_match" if actual == expected else "modified"


async def scoped_resource_preflight(template_id: str, locale: str, tenant_id: str, user_id: str) -> dict:
    declaration = resource_preflight(template_id, locale)
    if not _SEGMENT.fullmatch(tenant_id) or not _SEGMENT.fullmatch(user_id):
        raise ValueError("Resource identity cannot map to a filesystem scope")
    shared_id = f"__tenant_shared_skill__:{tenant_id}"
    async with get_session_factory()() as session:
        result = await session.exec(select(TenantSkill).where(TenantSkill.tenant_id == tenant_id, TenantSkill.user_id.in_([shared_id, user_id])))
        rows = result.scalars().all()
    skills_root = get_skills_root_path().absolute()
    public = []
    public_root = skills_root / "public"
    if public_root.is_dir() and public_root.resolve() == public_root:
        for file in public_root.rglob("SKILL.md"):
            if file.resolve() != file.absolute() or file.is_symlink():
                continue
            parsed = parse_skill_file(file, "public", file.parent.relative_to(public_root))
            if parsed:
                override = next((row for row in rows if row.user_id == shared_id and row.name == parsed.name), None)
                public.append({"name": parsed.name, "enabled": override.enabled if override else True, "folder": file.parent})
    for resource in declaration["resources"]:
        if resource["kind"] != "skill_bundle":
            resource["installation"] = {"status": "binding_required", "candidates": []}
            continue
        try:
            package = prepare_skill_package(declaration, resource)
        except SkillPackageUnavailable as error:
            resource["host_adaptation"] = {"status": "unavailable", "detail": str(error)}
            resource["installation"] = {"status": "format_blocked", "candidates": []}
            continue
        resource["host_adaptation"] = {"status": "ready", "name": package["name"], "adapted": package["adapted"], "adapter_version": 1}
        name = package["name"]
        matches = [p for p in public if p["name"] == name]
        candidates = []
        for item in matches:
            state = _contents_match(item["folder"], package["host_files_sha256"])
            if state == "modified" and not package["adapted"]:
                state = _contents_match(item["folder"], package["source_files_sha256"])
            candidates.append({"scope": "global", "enabled": bool(item["enabled"]), "content_status": state})
        for row in rows:
            if row.name != name or (row.user_id == shared_id and matches):
                continue
            scope = "tenant" if row.user_id == shared_id else "personal"
            folder = skills_root / "custom" / tenant_id
            if scope == "personal":
                folder /= user_id
            folder /= name
            recorded = Path(row.install_dir).absolute() if row.install_dir else folder
            if recorded != folder or folder.resolve() != folder:
                state = "location_unverified"
            else:
                state = _contents_match(folder, package["host_files_sha256"])
                if state == "modified" and not package["adapted"]:
                    state = _contents_match(folder, package["source_files_sha256"])
            candidates.append({"scope": scope, "enabled": bool(row.enabled), "content_status": state})
        status = "not_installed" if not candidates else "multiple_visible_records" if len(candidates) > 1 else "disabled" if not candidates[0]["enabled"] else candidates[0]["content_status"]
        resource["installation"] = {"status": status, "candidates": candidates}
    declaration["installation_checked"] = True
    declaration["installation_scope"] = "current tenant shared/personal rows and public roots; exact source/host-package bytes"
    return declaration
