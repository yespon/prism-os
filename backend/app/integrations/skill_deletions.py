"""Current-instance withdrawal and owned reclamation on original tables/receipts."""

import uuid

from sqlalchemy import select

from app.models.agents import CustomAgent
from deerflow.database import user_config_service as service
from deerflow.database.models import TenantSkill, UserConfig
from deerflow.database.secrets_crypto import decrypt_extensions_payload, encrypt_extensions_payload
from deerflow.skills.install_receipts import read_receipt, scoped_parent, write_receipt
from deerflow.skills.resource_deletion_files import OwnedRemoval, tree_digest
from deerflow.skills.resource_identity import public_resource_id, registered_resource_id, resource_directory

from .agent_skill_references import references_instance
from .skill_imports import owner_and_scope
from .skill_mutations import SkillMutationRejected
from .skill_reference_transactions import begin_reference_transaction


class SkillDeletionUnknown(Exception):
    def __init__(self, operation_id, resource_id):
        self.operation_id = operation_id
        self.resource_id = resource_id
        super().__init__("Deletion outcome requires inspection; owned operation facts were preserved")


async def _references(session, tenant, actor, shared, name, resource_id=None):
    query = select(CustomAgent).where(CustomAgent.tenant_id == tenant)
    if not shared:
        query = query.where(CustomAgent.user_id.in_([actor, "tenant-shared"]))
    agents = (await session.exec(query.with_for_update())).scalars().all()
    # Old names cannot prove which same-name source was bound. Do not expose
    # another user's agent id or contents in an aggregate management conflict.
    return sum(references_instance(agent, resource_id, name) for agent in agents)


def _public_directory(root, row):
    raw = row.install_dir
    if not raw:
        raise SkillMutationRejected(409, "Public override location cannot be verified")
    try:
        directory = resource_directory(root, row.tenant_id, row.user_id, {"scope": "global", "install_dir": raw})
    except ValueError:
        raise SkillMutationRejected(409, "Public override location cannot be verified") from None
    relative = directory.relative_to(root.resolve() / "public").as_posix()
    if row.relative_path and row.relative_path != relative:
        raise SkillMutationRejected(409, "Public override source differs from its registration")
    return public_resource_id(relative)


def _selection(root, tenant, actor, shared, row, expected_resource_id, expected_tree_sha256=None, expected_file_sha256=None):
    resource_id = registered_resource_id(row)
    if row.category == "public":
        if not shared:
            raise SkillMutationRejected(403, "Personal management cannot remove a public source override")
        selected = _public_directory(root, row)
        if expected_resource_id is not None and expected_resource_id not in {selected, resource_id}:
            raise SkillMutationRejected(409, "Public override instance changed")
        tree = {"directories": {}, "files": {}}
        return resource_id, selected, "public_override", tree
    if expected_resource_id is not None and expected_resource_id != resource_id:
        raise SkillMutationRejected(409, "Skill instance changed; inspect the current resource")
    try:
        target = resource_directory(root, tenant, actor, {"name": row.name, "scope": "tenant" if shared else "personal", "install_dir": row.install_dir, "relative_path": row.relative_path})
    except ValueError:
        raise SkillMutationRejected(409, "Skill directory does not match its current owner") from None
    parent, _ = scoped_parent(root, tenant if shared else f"{tenant}/{actor}")
    tree = {"directories": {}, "files": {}}
    kind = "missing"
    if parent.is_dir():
        files = OwnedRemoval(parent)
        try:
            if files.exists(target.name):
                tree = files.snapshot(target.name)
                kind = "owned"
        finally:
            files.close()
    if expected_tree_sha256 is not None and expected_tree_sha256 != tree_digest(tree):
        raise SkillMutationRejected(409, "Complete resource tree changed; inspect before deleting")
    if expected_file_sha256 is not None and expected_file_sha256 != tree["files"].get("SKILL.md", {}).get("sha256"):
        raise SkillMutationRejected(409, "Skill main file changed; inspect before deleting")
    return resource_id, resource_id, kind, tree


def _source_operations(root, scope, name, tree, resource_id):
    parent, _ = scoped_parent(root, scope)
    sources = []
    for path in parent.glob(".prismos-import-*.json"):
        operation_id = path.name.removeprefix(".prismos-import-").removesuffix(".json")
        record = read_receipt(root, scope, operation_id)
        if record["skill_name"] != name:
            continue
        if record.get("kind") == "resource_delete":
            if record["resource_id"] == resource_id and record["state"] != "delete_reclaimed":
                raise SkillMutationRejected(409, "A deletion operation already exists; inspect its record")
            continue
        if record["state"] == "withdrawn":
            continue
        moved = tree["directories"].get(".", {}).get("identity") == record.get("directory_identity")
        if moved or (not tree["directories"] and record["state"] in {"published", "registered", "registration_observed", "registration_unknown", "withdrawn"}):
            sources.append(operation_id)
    return sources


async def preflight(root, tenant, actor, shared, name, expected_resource_id=None):
    owner, scope = owner_and_scope(tenant, actor, shared)
    async with service.get_session_factory()() as session:
        row = (await session.exec(select(TenantSkill).where(TenantSkill.tenant_id == tenant, TenantSkill.user_id == owner, TenantSkill.name == name))).scalars().first()
        if row is None:
            raise SkillMutationRejected(404, "Current registered resource not found; files were preserved")
        resource_id, selected, kind, tree = _selection(root, tenant, actor, shared, row, expected_resource_id)
        references = 0 if kind == "public_override" else await _references(session, tenant, actor, shared, name, resource_id)
        _source_operations(root, scope, name, tree, resource_id)
        return {
            "name": name,
            "resource_id": resource_id,
            "selected_resource_id": selected,
            "scope": "tenant" if shared else "personal",
            "target_kind": kind,
            "tree_sha256": tree_digest(tree),
            "file_sha256": tree["files"].get("SKILL.md", {}).get("sha256"),
            "members": len(tree["files"]),
            "references": references,
            "eligible": references == 0,
            "physical_reclamation": kind == "owned",
        }


async def _remove_native_and_configuration(session, tenant, owner, row):
    config = (await session.exec(select(UserConfig).where(UserConfig.user_id == owner, UserConfig.tenant_id == tenant).with_for_update())).scalars().first()
    if config is not None:
        payload = decrypt_extensions_payload(dict(config.extensions_config or {}))
        original = payload.get("tenant_skill_settings")
        if isinstance(original, dict) and row.name in original:
            slots = dict(original)
            slots.pop(row.name)
            payload["tenant_skill_settings"] = slots
            config.extensions_config = encrypt_extensions_payload(payload)
            session.add(config)
    await session.delete(row)


def _withdraw_source_receipts(root, scope, record):
    parent, _ = scoped_parent(root, scope)
    for operation in record["source_operations"]:
        original = read_receipt(root, scope, operation)
        if original.get("kind") == "resource_delete" or original["skill_name"] != record["skill_name"]:
            raise ValueError("Deletion source record is invalid")
        if original["state"] == "withdrawn":
            continue
        if record["target_kind"] == "owned" and original.get("directory_identity") != record["directory_identity"]:
            raise ValueError("Deletion source directory identity changed")
        original.update(state="withdrawn", withdrawn_by=record["operation_id"], withdrawn_resource_id=record["resource_id"])
        write_receipt(parent, original)


async def delete_owned(root, tenant, actor, shared, name, *, expected_resource_id=None, expected_tree_sha256=None, expected_file_sha256=None):
    owner, scope = owner_and_scope(tenant, actor, shared)
    record = None
    removal = None
    try:
        async with service.get_session_factory()() as session:
            async with session.begin():
                await begin_reference_transaction(session, tenant)
                row = (await session.exec(select(TenantSkill).where(TenantSkill.tenant_id == tenant, TenantSkill.user_id == owner, TenantSkill.name == name).with_for_update())).scalars().first()
                if row is None:
                    raise SkillMutationRejected(404, "Current registered resource not found; files were preserved")
                resource_id, selected, kind, tree = _selection(root, tenant, actor, shared, row, expected_resource_id, expected_tree_sha256, expected_file_sha256)
                if kind != "public_override" and await _references(session, tenant, actor, shared, name, resource_id):
                    raise SkillMutationRejected(409, "Legacy Agent references need review before physical deletion")
                sources = [] if kind == "public_override" else _source_operations(root, scope, name, tree, resource_id)
                parent, relative = scoped_parent(root, scope, create=True)
                operation = uuid.uuid4().hex
                record = {
                    "schema_version": "prismos.skill-install.v1",
                    "kind": "resource_delete",
                    "operation_id": operation,
                    "scope": relative.as_posix(),
                    "skill_name": name,
                    "stage_name": ".prismos-stage-" + operation,
                    "state": "delete_prepared",
                    "resource_id": resource_id,
                    "selected_resource_id": selected,
                    "target_kind": kind,
                    "tree": tree,
                    "directory_identity": tree["directories"].get(".", {}).get("identity"),
                    "source_operations": sources,
                }
                write_receipt(parent, record, initial=True)
                if kind == "owned":
                    removal = OwnedRemoval(parent)
                    removal.quarantine(record)
                record["state"] = "delete_quarantined"
                write_receipt(parent, record)
                _withdraw_source_receipts(root, scope, record)
                await _remove_native_and_configuration(session, tenant, owner, row)
        record["state"] = "delete_withdrawn"
        write_receipt(parent, record)
        finish_reclamation(parent, record, removal)
        return record
    except SkillMutationRejected:
        if record is not None:
            raise SkillDeletionUnknown(record["operation_id"], record["selected_resource_id"]) from None
        raise
    except Exception:
        if record is not None:
            raise SkillDeletionUnknown(record["operation_id"], record["selected_resource_id"]) from None
        raise
    finally:
        if removal is not None:
            removal.close()


def finish_reclamation(parent, record, removal=None):
    own = None
    try:
        record["state"] = "delete_reclaiming"
        write_receipt(parent, record)
        if record["target_kind"] == "owned":
            if removal is None:
                own = OwnedRemoval(parent)
                removal = own
            removal.reclaim(record)
        record["state"] = "delete_reclaimed"
        write_receipt(parent, record)
    finally:
        if own is not None:
            own.close()


async def observe_operation(operation_id, tenant, actor, shared, *, root):
    owner, scope = owner_and_scope(tenant, actor, shared)
    record = read_receipt(root, scope, operation_id)
    if record.get("kind") != "resource_delete":
        raise ValueError("Not a deletion operation")
    async with service.get_session_factory()() as session:
        row = (await session.exec(select(TenantSkill).where(TenantSkill.tenant_id == tenant, TenantSkill.user_id == owner, TenantSkill.name == record["skill_name"]))).scalars().first()
    original_exists = row is not None and registered_resource_id(row) == record["resource_id"]
    state = "deletion_pending" if original_exists else "reclamation_pending"
    verified = False
    parent, _ = scoped_parent(root, scope)
    if record["state"] == "delete_reclaimed" and not original_exists:
        state = "reclaimed"
    elif record["target_kind"] != "owned":
        verified = True
    else:
        removal = OwnedRemoval(parent)
        try:
            if removal.exists(record["stage_name"]):
                verified = removal.remaining(record) is not None
            elif original_exists:
                verified = removal.snapshot(record["skill_name"]) == record["tree"]
            elif record["state"] == "delete_reclaiming":
                verified = True
            if not verified:
                state = "deletion_files_unverified"
        except (OSError, ValueError):
            state = "deletion_files_unverified"
        finally:
            removal.close()
    return {
        "operation_id": operation_id,
        "name": record["skill_name"],
        "scope": "tenant" if shared else "personal",
        "kind": "resource_delete",
        "state": state,
        "phase": record["state"],
        "files_verified": verified,
        "registered": original_exists,
        "enabled": row.enabled if original_exists else None,
        "resource_id": record["selected_resource_id"],
        "withdrawn": not original_exists,
        "physical_reclamation": record["target_kind"] == "owned",
        "execution_ready": False,
    }


async def recover_operation(operation_id, tenant, actor, shared, *, root):
    owner, scope = owner_and_scope(tenant, actor, shared)
    record = read_receipt(root, scope, operation_id)
    if record.get("kind") != "resource_delete":
        raise ValueError("Not a deletion operation")
    if record["state"] == "delete_reclaimed":
        return await observe_operation(operation_id, tenant, actor, shared, root=root)
    parent, _ = scoped_parent(root, scope)
    removal = OwnedRemoval(parent) if record["target_kind"] == "owned" else None
    try:
        async with service.get_session_factory()() as session:
            async with session.begin():
                await begin_reference_transaction(session, tenant)
                row = (await session.exec(select(TenantSkill).where(TenantSkill.tenant_id == tenant, TenantSkill.user_id == owner, TenantSkill.name == record["skill_name"]).with_for_update())).scalars().first()
                original_exists = row is not None and registered_resource_id(row) == record["resource_id"]
                if original_exists:
                    if record["target_kind"] != "public_override" and await _references(session, tenant, actor, shared, record["skill_name"], record["resource_id"]):
                        raise ValueError("Current Agent references block deletion recovery")
                    if removal is not None:
                        if removal.exists(record["stage_name"]):
                            if removal.snapshot(record["stage_name"]) != record["tree"]:
                                raise ValueError("Quarantine changed before withdrawal")
                        else:
                            removal.quarantine(record)
                    _withdraw_source_receipts(root, scope, record)
                    await _remove_native_and_configuration(session, tenant, owner, row)
                elif record["state"] == "delete_prepared":
                    raise ValueError("Withdrawal could not be proven; content retained")
        record["state"] = "delete_withdrawn"
        write_receipt(parent, record)
        finish_reclamation(parent, record, removal)
        return await observe_operation(operation_id, tenant, actor, shared, root=root)
    finally:
        if removal is not None:
            removal.close()
