"""Selected native Skill members read through held descriptors and original facts."""

import hashlib
import os
from pathlib import PurePosixPath

from sqlalchemy import select

from app.integrations.agent_skill_references import _public_directories, current_skill_resources
from deerflow.database.models import TenantSkill
from deerflow.sandbox.local.list_dir import _should_ignore
from deerflow.skills import get_skills_root_path
from deerflow.skills.resource_deletion_files import OwnedRemoval


def _snapshot_read(directory, relative, operation, virtual_root, boundaries, expected_snapshot):
    removal = OwnedRemoval(directory.parent)
    opened = []
    try:
        tree = removal.snapshot(directory.name)
        if tree != expected_snapshot:
            raise ValueError("Skill changed after source resolution")
        fd = os.open(directory.name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=removal.fd)
        opened.append(fd)
        if [os.fstat(fd).st_dev, os.fstat(fd).st_ino] != tree["directories"]["."]["identity"]:
            raise ValueError("Skill directory changed")
        if operation == "read":
            parts = PurePosixPath(relative).parts
            if not parts:
                raise IsADirectoryError
            for index, name in enumerate(parts[:-1]):
                fd = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                opened.append(fd)
                expected = tree["directories"]["/".join(parts[: index + 1])]
                if [os.fstat(fd).st_dev, os.fstat(fd).st_ino] != expected["identity"]:
                    raise ValueError("Skill member ancestor changed")
            expected = tree["files"].get(relative)
            if expected is None:
                raise ValueError("Skill member unavailable")
            member = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW, dir_fd=fd)
            with os.fdopen(member, "rb") as file:
                info = os.fstat(file.fileno())
                data = file.read()
                if [info.st_dev, info.st_ino] != expected["identity"] or hashlib.sha256(data).hexdigest() != expected["sha256"]:
                    raise ValueError("Skill member changed")
            result = data.decode("utf-8").replace("\r\n", "\n").replace("\r", "\n")
        elif operation == "ls":
            if (relative or ".") not in tree["directories"]:
                raise ValueError("Skill member directory unavailable")
            result = []
            prefix = relative + "/" if relative else ""
            for kind in ("directories", "files"):
                for name in tree[kind]:
                    if name == "." or not name.startswith(prefix):
                        continue
                    tail = PurePosixPath(name[len(prefix) :])
                    if not 1 <= len(tail.parts) <= 2 or any(_should_ignore(p) for p in tail.parts):
                        continue
                    full = virtual_root / name
                    if any(full == b or full.is_relative_to(b) for b in boundaries if b != virtual_root):
                        continue
                    result.append(str(full) + ("/" if kind == "directories" else ""))
            result.sort()
        else:
            raise ValueError("Unsupported Skill member operation")
        if removal.snapshot(directory.name) != tree:
            raise ValueError("Skill members changed during access")
        return result
    finally:
        for fd in reversed(opened):
            os.close(fd)
        removal.close()


async def current_member(session, context, operation, path, container_prefix):
    requested = PurePosixPath("/" + path.lstrip("/"))
    prefix = PurePosixPath(container_prefix)
    if ".." in path.split("/") or not requested.is_relative_to(prefix):
        raise ValueError("Skill path unavailable")
    root = get_skills_root_path().resolve()
    resolved = await current_skill_resources(session, context["agent_name"], context["tenant_id"], context["user_id"], selected_agent_id=context["agent_id"], root=root, include_snapshot=True)
    if resolved is None:
        return None
    choices = [(prefix / PurePosixPath(item["location"]).parent, item) for item in resolved]
    # A registered nested resource is its own authority boundary, even if an
    # enclosing selected resource shares the old custom directory namespace.
    boundaries = [prefix / "public" / p.relative_to(root / "public").as_posix() for p in _public_directories(root)]
    rows = (await session.exec(select(TenantSkill).where(TenantSkill.tenant_id == context["tenant_id"], TenantSkill.category != "public"))).scalars().all()
    for row in rows:
        owner = () if row.user_id == f"__tenant_shared_skill__:{context['tenant_id']}" else (row.user_id,)
        boundaries.append(prefix / "custom" / context["tenant_id"] / PurePosixPath(*owner) / row.name)
    candidates = [(base, item) for base, item in choices if requested == base or requested.is_relative_to(base)]
    if not candidates:
        if operation == "ls" and any(base.is_relative_to(requested) for base, _ in choices):
            entries = set()
            for base, _ in choices:
                if base.is_relative_to(requested):
                    parts = base.relative_to(requested).parts
                    for depth in range(1, min(len(parts), 2) + 1):
                        entries.add(str(requested.joinpath(*parts[:depth])) + "/")
            return sorted(entries)
        raise ValueError("Skill source is outside the current selection")
    base, item = max(candidates, key=lambda pair: len(pair[0].parts))
    if any(b != base and b.is_relative_to(base) and (requested == b or requested.is_relative_to(b)) for b in boundaries):
        raise ValueError("Nested resource needs its own current selection")
    directory = root / base.relative_to(prefix).as_posix()
    relative = requested.relative_to(base).as_posix()
    return _snapshot_read(directory, "" if relative == "." else relative, operation, base, boundaries, item["member_snapshot"])
