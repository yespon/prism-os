"""Existing Skill registration plus filesystem reconciliation; no execution facts."""

import base64
import hashlib
import json
import re
from pathlib import Path

from sqlalchemy import select

from deerflow.database import user_config_service as service
from deerflow.database.models import TenantSkill
from deerflow.skills.install_receipts import InvalidSkillReceipt, abort_staged_operation, mark_registration, read_receipt, resume_publication, scoped_parent, verified_publication, verified_stage, write_receipt
from deerflow.skills.installer import SkillAlreadyExistsError, prepare_skill_installation_from_archive
from deerflow.skills.loader import get_skills_root_path


async def current_row(tenant_id: str, user_id: str, name: str) -> TenantSkill | None:
    async with service.get_session_factory()() as session:
        result = await session.exec(select(TenantSkill).where(TenantSkill.tenant_id == tenant_id, TenantSkill.user_id == user_id, TenantSkill.name == name))
        return result.scalars().first()


def owner_and_scope(tenant_id: str, user_id: str, shared: bool):
    if not user_id:
        raise ValueError("User identity is required")
    return (f"__tenant_shared_skill__:{tenant_id}", tenant_id) if shared else (user_id, f"{tenant_id}/{user_id}")


async def register(tenant_id: str, user_id: str, shared: bool, result: dict) -> TenantSkill:
    payload = {"enabled": True, "skill_name": result["skill_name"], "category": result["category"], "relative_path": result["relative_path"], "install_dir": result["install_dir"]}
    if shared:
        return await service.create_tenant_shared_skill(tenant_id, **payload)
    return await service.create_tenant_personal_skill(tenant_id, user_id, **payload)


async def import_archive(archive: Path, tenant_id: str, user_id: str, shared: bool, *, root: Path | None = None) -> tuple[dict, TenantSkill]:
    owner, scope = owner_and_scope(tenant_id, user_id, shared)
    root = root or get_skills_root_path()
    result = None
    with prepare_skill_installation_from_archive(archive, skills_root=root, target_relative_path=scope) as prepared:
        if await current_row(tenant_id, owner, prepared.record["skill_name"]) is not None:
            raise SkillAlreadyExistsError(f"Skill '{prepared.record['skill_name']}' is already registered")
        try:
            try:
                result = prepared.publish()
            except FileExistsError:
                raise SkillAlreadyExistsError(f"Skill '{prepared.record['skill_name']}' already exists") from None
            row = await register(tenant_id, user_id, shared, result)
            mark_registration(result, "registered", row_id=row.id)
            return result, row
        except Exception as error:
            if prepared.published or prepared.publication_exists():
                # The DB may have committed even if refresh/response transport failed.
                # Preserve files. Recovery checks current rows and the owned directory.
                if result is None:
                    result = prepared.result
                try:
                    mark_registration(result, "registration_unknown")
                except (OSError, ValueError):
                    pass  # The prepared receipt still permits inode/digest reconciliation.
                error.skill_operation_id = prepared.operation_id
            raise


async def observe_operation(operation_id: str, tenant_id: str, user_id: str, shared: bool, *, root: Path | None = None) -> dict:
    owner, scope = owner_and_scope(tenant_id, user_id, shared)
    root = root or get_skills_root_path()
    record = read_receipt(root, scope, operation_id)
    row = await current_row(tenant_id, owner, record["skill_name"])
    summary = {
        "operation_id": operation_id,
        "name": record["skill_name"],
        "scope": "tenant" if shared else "personal",
        "state": record["state"],
        "phase": record["state"],
        "files_verified": False,
        "registered": False,
        "enabled": row.enabled if row else None,
        "execution_ready": False,
    }
    try:
        _, target = verified_publication(root, scope, operation_id)
    except ValueError:
        try:
            verified_stage(root, scope, operation_id)
            summary["state"] = "publication_pending" if row is None else "registration_conflict"
            summary["staged_files_verified"] = True
        except ValueError:
            summary["state"] = "aborted" if record["state"] == "aborted" else "files_unverified"
        return summary
    summary["files_verified"] = True
    if row is None:
        summary["state"] = "registration_pending"
    elif row.install_dir and Path(row.install_dir).absolute() == target:
        summary["state"] = "registered"
        summary["registered"] = True
    else:
        summary["state"] = "registration_conflict"
    return summary


async def recover_operation(operation_id: str, tenant_id: str, user_id: str, shared: bool, *, root: Path | None = None) -> dict:
    owner, scope = owner_and_scope(tenant_id, user_id, shared)
    root = root or get_skills_root_path()
    record = read_receipt(root, scope, operation_id)
    row = await current_row(tenant_id, owner, record["skill_name"])
    try:
        record, target = verified_publication(root, scope, operation_id)
    except ValueError:
        if row is not None:
            raise SkillAlreadyExistsError("Current Skill registration conflicts with staged publication")
        resume_publication(root, scope, operation_id)
        record, target = verified_publication(root, scope, operation_id)
    if row is not None:
        if not row.install_dir or Path(row.install_dir).absolute() != target:
            raise SkillAlreadyExistsError("Current Skill registration points to different files")
        state = "registration_observed"
    else:
        from deerflow.skills.validation import _validate_skill_frontmatter

        valid, _, name = _validate_skill_frontmatter(target)
        if not valid or name != record["skill_name"]:
            raise ValueError("Published Skill format is unavailable")
        parent, relative = scoped_parent(root, scope)
        result = {"skill_name": name, "category": "custom", "relative_path": (relative / name).as_posix(), "install_dir": str(target)}
        row = await register(tenant_id, user_id, shared, result)
        state = "registered"
    # Reading a matching existing row does not claim this operation created it.
    record.update(state=state, row_id=row.id)
    parent, _ = scoped_parent(root, scope)
    write_receipt(parent, record)
    return await observe_operation(operation_id, tenant_id, user_id, shared, root=root)


class InvalidImportCursor(ValueError):
    pass


_OPERATION_ID = re.compile(r"^[0-9a-f]{32}$")
_RECEIPT_NAME = re.compile(r"^\.prismos-import-([0-9a-f]{32})\.json$")
RECEIPT_RETENTION = {"mode": "retain_all", "automatic_deletion": False, "maintenance": "owned_stage_abort_only"}


def _cursor_scope(tenant_id: str, user_id: str, shared: bool) -> str:
    return hashlib.sha256(json.dumps([tenant_id, user_id, shared], separators=(",", ":")).encode()).hexdigest()


def _decode_cursor(cursor: str, identity: str, page_size: int) -> tuple[str, str]:
    try:
        if len(cursor) > 512:
            raise ValueError()
        payload = json.loads(base64.b64decode(cursor + "=" * (-len(cursor) % 4), altchars=b"-_", validate=True))
        if not isinstance(payload, dict) or set(payload) != {"v", "scope", "before", "ceiling", "page_size"}:
            raise ValueError()
        if type(payload["v"]) is not int or payload["v"] != 1 or payload["scope"] != identity or type(payload["page_size"]) is not int or payload["page_size"] != page_size:
            raise ValueError()
        before, ceiling = payload["before"], payload["ceiling"]
        if not isinstance(before, str) or not isinstance(ceiling, str) or not _OPERATION_ID.fullmatch(before) or not _OPERATION_ID.fullmatch(ceiling) or before > ceiling:
            raise ValueError()
        return before, ceiling
    except (ValueError, TypeError, UnicodeError):
        raise InvalidImportCursor("Import cursor is invalid for the current identity or page size; inspect again") from None


def _encode_cursor(identity: str, before: str, ceiling: str, page_size: int) -> str:
    payload = {"v": 1, "scope": identity, "before": before, "ceiling": ceiling, "page_size": page_size}
    return base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()).decode().rstrip("=")


async def list_operation_page(tenant_id: str, user_id: str, shared: bool, *, root: Path | None = None, cursor: str | None = None, page_size: int = 100) -> dict:
    if type(page_size) is not int or not 1 <= page_size <= 100:
        raise InvalidImportCursor("Import page size must be between 1 and 100")
    _, scope = owner_and_scope(tenant_id, user_id, shared)
    root = root or get_skills_root_path()
    parent, _ = scoped_parent(root, scope)
    identity = _cursor_scope(tenant_id, user_id, shared)
    before, ceiling = _decode_cursor(cursor, identity, page_size) if cursor is not None else (None, None)
    # Immutable IDs retain their place when recovery rewrites a receipt. This is
    # a live listing, not a frozen snapshot; refresh discovers new IDs in ranges
    # already visited. Every old ID still present remains reachable once.
    ids = []
    ignored = 0
    for path in parent.glob(".prismos-import-*.json"):
        match = _RECEIPT_NAME.fullmatch(path.name)
        if match:
            ids.append(match[1])
        else:
            ignored += 1
    ids.sort(reverse=True)
    ceiling = ceiling or (ids[0] if ids else "0" * 32)
    eligible = [value for value in ids if value <= ceiling and (before is None or value < before)]
    selected = eligible[:page_size]
    items = []
    for operation_id in selected:
        try:
            # Validate local metadata before consulting the database. A corrupt
            # receipt is isolated; a database outage must fail the whole request.
            read_receipt(root, scope, operation_id)
        except (OSError, ValueError):
            items.append({"operation_id": operation_id, "name": "", "scope": "tenant" if shared else "personal", "state": "receipt_unavailable", "files_verified": False, "registered": False, "enabled": None, "execution_ready": False})
            continue
        try:
            items.append(await observe_operation(operation_id, tenant_id, user_id, shared, root=root))
        except (InvalidSkillReceipt, FileNotFoundError):
            items.append({"operation_id": operation_id, "name": "", "scope": "tenant" if shared else "personal", "state": "receipt_unavailable", "files_verified": False, "registered": False, "enabled": None, "execution_ready": False})
    next_cursor = _encode_cursor(identity, selected[-1], ceiling, page_size) if len(eligible) > page_size else None
    return {"operations": items, "next_cursor": next_cursor, "total": len(ids), "ignored_entries": ignored, "ordering": "operation_id_desc", "listing": "live_refresh_for_new_records", "retention": dict(RECEIPT_RETENTION)}


async def abort_operation(operation_id: str, tenant_id: str, user_id: str, shared: bool, *, root: Path | None = None) -> dict:
    _, scope = owner_and_scope(tenant_id, user_id, shared)
    root = root or get_skills_root_path()
    abort_staged_operation(root, scope, operation_id)
    return await observe_operation(operation_id, tenant_id, user_id, shared, root=root)
