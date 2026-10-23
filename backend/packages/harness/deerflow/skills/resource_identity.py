"""Concrete Skill read identities on the existing registry and scope directories."""
import hashlib
import json
import re
from datetime import UTC
from pathlib import Path

_NAME = re.compile(r"^[a-z0-9_-]+$")


def public_resource_id(relative_path: str) -> str:
    return "public:" + hashlib.sha256(relative_path.encode()).hexdigest()


def registered_resource_id(row) -> str:
    created = row.created_at
    if created.tzinfo is None:
        created = created.replace(tzinfo=UTC)
    created = created.astimezone(UTC).isoformat(timespec="microseconds")
    identity = [row.id, row.tenant_id, row.user_id, row.name, created]
    digest = hashlib.sha256(json.dumps(identity, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()
    return f"skill:{row.id}:{digest}"


def resource_directory(root: Path, tenant_id: str, user_id: str, row: dict) -> Path:
    root = root.resolve()
    scope = row.get("scope")
    raw = row.get("install_dir")
    if scope == "global":
        if not isinstance(raw, str) or not raw:
            raise ValueError("Public resource location is unavailable")
        target = Path(raw).absolute()
        if not target.is_relative_to(root / "public"):
            raise ValueError("Public resource location is outside its scope")
    else:
        name = row.get("name")
        if scope not in {"tenant", "personal"} or not isinstance(name, str) or not _NAME.fullmatch(name):
            raise ValueError("Skill resource scope or name is unavailable")
        parent = root / "custom" / tenant_id
        if scope == "personal":
            parent = parent / user_id
        target = parent / name
        if not target.is_relative_to(root / "custom"):
            raise ValueError("Skill resource target is outside its scope")
        if isinstance(raw, str) and raw and Path(raw).absolute() != target:
            raise ValueError("Registered Skill location differs from the current owner scope")
        relative = row.get("relative_path")
        if isinstance(relative, str) and relative:
            allowed = {name, target.relative_to(root / "custom").as_posix(), target.relative_to(root / "custom" / tenant_id).as_posix()}
            if relative not in allowed:
                raise ValueError("Registered Skill relative location differs from its owner scope")
    if target.resolve() != target or (target / "SKILL.md").is_symlink():
        raise ValueError("Skill resource contains a filesystem alias")
    return target
