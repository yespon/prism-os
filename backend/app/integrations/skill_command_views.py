"""Ephemeral copies of original selected resources, with complete source proof."""

import hashlib
import os
from pathlib import PurePosixPath

from sqlalchemy import select

from app.integrations.agent_skill_references import current_skill_resources
from deerflow.database.models import TenantSkill
from deerflow.skills import get_skills_root_path
from deerflow.skills.resource_deletion_files import OwnedRemoval


def copy_verified_tree(directory, expected, destination, excluded):
    removal = OwnedRemoval(directory.parent)
    root_fd = None
    try:
        if removal.snapshot(directory.name) != expected:
            raise ValueError("Skill changed before copying")
        root_fd = os.open(directory.name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=removal.fd)
        if [os.fstat(root_fd).st_dev, os.fstat(root_fd).st_ino] != expected["directories"]["."]["identity"]:
            raise ValueError("Skill directory changed")
        for name in expected["directories"]:
            relative = PurePosixPath(name)
            if not any(relative == b or relative.is_relative_to(b) for b in excluded):
                (destination / name).mkdir(parents=True, exist_ok=True)
        for name, entry in expected["files"].items():
            relative = PurePosixPath(name)
            if any(relative == boundary or relative.is_relative_to(boundary) for boundary in excluded):
                continue
            fd = root_fd
            opened = []
            try:
                for depth, part in enumerate(relative.parts[:-1]):
                    fd = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                    opened.append(fd)
                    identity = expected["directories"]["/".join(relative.parts[: depth + 1])]["identity"]
                    if [os.fstat(fd).st_dev, os.fstat(fd).st_ino] != identity:
                        raise ValueError("Skill member ancestor changed")
                member = os.open(relative.name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=fd)
                with os.fdopen(member, "rb") as file:
                    info = os.fstat(file.fileno())
                    content = file.read()
                    if [info.st_dev, info.st_ino] != entry["identity"] or hashlib.sha256(content).hexdigest() != entry["sha256"]:
                        raise ValueError("Skill member changed")
                target = destination / name
                target.parent.mkdir(parents=True, exist_ok=True)
                with target.open("xb") as output:
                    output.write(content)
                target.chmod((info.st_mode & 0o777) | 0o444)
            finally:
                for child in reversed(opened):
                    os.close(child)
        if removal.snapshot(directory.name) != expected:
            raise ValueError("Skill changed while copying")
    finally:
        if root_fd is not None:
            os.close(root_fd)
        removal.close()


async def materialize(session, context, destination):
    tenant, actor = context["tenant_id"], context["user_id"]
    resources = await current_skill_resources(session, context["agent_name"], tenant, actor, selected_agent_id=context["agent_id"], include_snapshot=True)
    if resources is None:
        return None
    root = get_skills_root_path().resolve()
    rows = (await session.exec(select(TenantSkill).where(TenantSkill.tenant_id == tenant, TenantSkill.category != "public"))).scalars().all()
    registered = []
    for row in rows:
        owner = () if row.user_id == f"__tenant_shared_skill__:{tenant}" else (row.user_id,)
        registered.append(PurePosixPath("custom", tenant, *owner, row.name))
    for resource in sorted(resources, key=lambda item: len(PurePosixPath(item["location"]).parts)):
        relative = PurePosixPath(resource["location"]).parent
        directory = root / str(relative)
        excluded = [boundary.relative_to(relative) for boundary in registered if boundary != relative and boundary.is_relative_to(relative)]
        # An unregistered nested main file is an unknown independent source,
        # never implicit access granted by a selected enclosing source.
        excluded += [PurePosixPath(p).parent for p in resource["member_snapshot"]["files"] if p != "SKILL.md" and PurePosixPath(p).name == "SKILL.md"]
        copy_verified_tree(directory, resource["member_snapshot"], destination / str(relative), excluded)
    return resources
