"""Existing Skill registration plus filesystem reconciliation; no execution facts."""

from pathlib import Path

from sqlalchemy import select

from deerflow.database import user_config_service as service
from deerflow.database.models import TenantSkill
from deerflow.skills.install_receipts import abort_staged_operation, mark_registration, read_receipt, receipt_path, resume_publication, scoped_parent, verified_publication, verified_stage, write_receipt
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


async def list_operations(tenant_id: str, user_id: str, shared: bool, *, root: Path | None = None) -> list[dict]:
    _, scope = owner_and_scope(tenant_id, user_id, shared)
    root = root or get_skills_root_path()
    parent, _ = scoped_parent(root, scope)
    records = sorted(parent.glob(".prismos-import-*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    items = []
    for path in records[:100]:
        operation_id = path.name.removeprefix(".prismos-import-").removesuffix(".json")
        if receipt_path(parent, operation_id) != path:
            continue
        items.append(await observe_operation(operation_id, tenant_id, user_id, shared, root=root))
    return items


async def abort_operation(operation_id: str, tenant_id: str, user_id: str, shared: bool, *, root: Path | None = None) -> dict:
    _, scope = owner_and_scope(tenant_id, user_id, shared)
    root = root or get_skills_root_path()
    abort_staged_operation(root, scope, operation_id)
    return await observe_operation(operation_id, tenant_id, user_id, shared, root=root)
