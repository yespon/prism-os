"""Manual creation must reuse owned publication and current native authorization."""

import asyncio

import pytest
from test_skill_import_recovery import archive_bytes
from test_skill_import_recovery import scoped_client as recovery_client
from test_skill_mutation_boundaries import native_rows
from test_skill_resource_identity import source_tree

from deerflow.database import user_config_service as service
from deerflow.skills import installer

scoped_client = recovery_client
ADMIN = {"x-tenant-role": "tenant_admin"}


def published_unknown(root, name="manual-created"):
    archive = root.parent / (name + ".zip")
    archive.write_bytes(archive_bytes(name))
    with installer.prepare_skill_installation_from_archive(archive, skills_root=root, target_relative_path="tenant-a/user-a") as prepared:
        return prepared.publish()


def test_manual_creation_cannot_overwrite_native_published_unknown(scoped_client, monkeypatch):
    http, factory, root = source_tree(scoped_client, monkeypatch)
    result = published_unknown(root)
    file = root / "custom/tenant-a/user-a/manual-created/SKILL.md"
    before = file.read_bytes()
    response = http.post("/api/skills/personal", json={"name": "manual-created", "description": "New description", "instructions": "OVERWRITE"})
    assert response.status_code == 409
    assert file.read_bytes() == before and len(native_rows(factory)) == 2
    inspection = http.get("/api/skills/personal/imports/" + result["operation_id"])
    assert inspection.status_code == 200 and inspection.json()["files_verified"] and not inspection.json()["registered"]


def test_shared_manual_creation_rejects_member_before_any_write(scoped_client, monkeypatch):
    http, factory, root = source_tree(scoped_client, monkeypatch)
    response = http.post("/api/tenants/skills", json={"name": "manual-created", "description": "Shared description"})
    assert response.status_code == 403
    assert not (root / "custom/tenant-a/manual-created").exists()
    assert len(native_rows(factory)) == 2


def test_shared_manual_creation_cannot_create_a_public_override(scoped_client, monkeypatch):
    http, factory, root = source_tree(scoped_client, monkeypatch)
    response = http.post("/api/tenants/skills", headers=ADMIN, json={"name": "manual-created", "description": "Shared description", "category": "public"})
    assert response.status_code == 403
    assert not (root / "custom/tenant-a/manual-created").exists()
    assert len(native_rows(factory)) == 2


def test_new_personal_creation_does_not_inherit_old_same_name_settings(scoped_client, monkeypatch):
    http, factory, root = source_tree(scoped_client, monkeypatch)
    asyncio.run(service.update_tenant_personal_skill_settings("tenant-a", "user-a", "manual-created", bound_tools=["old-binding"], prompt_template="OLD TEMPLATE", strategy="old-strategy"))
    response = http.post("/api/skills/personal", json={"name": "manual-created", "description": "Own description", "instructions": "OWN BODY"})
    assert response.status_code == 201, response.text
    assert response.json()["bound_tools"] == []
    assert not response.json()["prompt_template"] and not response.json()["strategy"]


def create(http, shared=False, **body):
    payload = {"name": "manual-created", "description": "SOP: quoted description", "instructions": "OWN MANUAL BODY", **body}
    return http.post("/api/tenants/skills" if shared else "/api/skills/personal", headers=ADMIN if shared else {}, json=payload)


def operation_url(response, shared=False):
    prefix = "/api/tenants/skills/imports/" if shared else "/api/skills/personal/imports/"
    body = response.json()
    return prefix + (body.get("operation_id") or body["detail"]["operation_id"])




@pytest.mark.parametrize("shared", [False, True])
def test_manual_success_preserves_requested_disabled_state_and_metadata(scoped_client, monkeypatch, shared):
    http, factory, root = source_tree(scoped_client, monkeypatch)
    response = create(http, shared, enabled=False, bound_tools=["reviewed-tool"], prompt_template="Reviewed template", strategy="guided", changelog="Initial: reviewed")
    assert response.status_code == 201, response.text
    value = response.json()
    assert not value["enabled"] and value["scope"] == ("tenant" if shared else "personal")
    assert value["category"] == ("custom" if shared else "personal")
    assert value["description"] == "SOP: quoted description" and value["created_by"] == "user-a"
    assert value["changelog"] == "Initial: reviewed" and value["version"] == 1
    assert value["bound_tools"] == ["reviewed-tool"] and value["prompt_template"] == "Reviewed template"
    headers = ADMIN if shared else {}
    operation = http.get(operation_url(response, shared), headers=headers).json()
    assert operation["registered"] and operation["files_verified"] and not operation["enabled"]
    assert operation["kind"] == "manual_create" and operation["configuration_phase"] == "confirmed"
    assert operation["resource_id"] == value["resource_id"]
    directory = root / "custom/tenant-a" / ("" if shared else "user-a") / "manual-created"
    assert not list(directory.parent.glob(".prismos-stage-*"))


@pytest.mark.parametrize("requested", [False, True])
def test_registration_failure_preserves_manual_intent_and_recovery_stays_disabled(scoped_client, monkeypatch, requested):
    http, factory, root = source_tree(scoped_client, monkeypatch)

    async def unavailable(*args, **kwargs):
        raise RuntimeError("injected manual registration failure")

    with monkeypatch.context() as patch:
        patch.setattr(service, "create_tenant_personal_skill", unavailable)
        response = create(http, enabled=requested, bound_tools=["explicit-new-tool"])
    assert response.status_code == 503 and response.json()["detail"]["inspection_required"]
    url = operation_url(response)
    before = http.get(url).json()
    assert before["files_verified"] and not before["registered"] and before["requested_enabled"] == requested
    assert before["configuration_phase"] == "pending" and len(native_rows(factory)) == 2
    recovered = http.post(url + "/recover").json()
    assert recovered["registered"] and not recovered["enabled"] and recovered["configuration_phase"] == "pending"
    assert http.post(url + "/recover").json()["resource_id"] == recovered["resource_id"]
    assert next(row for row in native_rows(factory) if row.name == "manual-created").category == "personal"
    assert http.get(url, headers={"x-user-id": "user-b"}).status_code == 404
    assert http.get(url, headers={"x-tenant-id": "tenant-b"}).status_code == 404
    record = next((root / "custom/tenant-a/user-a").glob(".prismos-import-*.json")).read_text()
    assert "explicit-new-tool" not in record and "prompt_template" not in record


def test_configuration_transaction_failure_keeps_registered_disabled_and_old_slot(scoped_client, monkeypatch):
    from sqlalchemy import event
    from sqlmodel.ext.asyncio.session import AsyncSession

    http, factory, root = source_tree(scoped_client, monkeypatch)
    asyncio.run(service.update_tenant_personal_skill_settings("tenant-a", "user-a", "manual-created", bound_tools=["old-binding"]))

    def fail(session):
        if any(getattr(row, "name", None) == "manual-created" and getattr(row, "enabled", False) for row in session.identity_map.values()):
            raise RuntimeError("injected configuration transaction failure")

    event.listen(AsyncSession.sync_session_class, "before_commit", fail)
    try:
        response = create(http, bound_tools=["new-binding"])
    finally:
        event.remove(AsyncSession.sync_session_class, "before_commit", fail)
    assert response.status_code == 503
    result = http.get(operation_url(response)).json()
    assert result["registered"] and not result["enabled"] and result["configuration_phase"] == "unknown"
    current = asyncio.run(service.get_tenant_personal_skill_settings("tenant-a", "user-a"))["manual-created"]
    assert current["bound_tools"] == ["old-binding"]
    assert (root / "custom/tenant-a/user-a/manual-created/SKILL.md").exists()


def test_actual_configuration_commit_then_timeout_preserves_enabled_and_settings(scoped_client, monkeypatch):
    from sqlalchemy import event
    from sqlmodel.ext.asyncio.session import AsyncSession

    http, factory, root = source_tree(scoped_client, monkeypatch)

    def fail(session):
        if any(getattr(row, "name", None) == "manual-created" and getattr(row, "enabled", False) for row in session.identity_map.values()):
            raise TimeoutError("injected delivery after actual configuration commit")

    event.listen(AsyncSession.sync_session_class, "after_commit", fail)
    try:
        response = create(http, bound_tools=["new-binding"], strategy="reviewed")
    finally:
        event.remove(AsyncSession.sync_session_class, "after_commit", fail)
    assert response.status_code == 503 and response.json()["detail"]["inspection_required"]
    operation = http.get(operation_url(response)).json()
    assert operation["registered"] and operation["enabled"] and operation["configuration_phase"] == "unknown"
    current = asyncio.run(service.get_tenant_personal_skill_settings("tenant-a", "user-a"))["manual-created"]
    assert current["bound_tools"] == ["new-binding"] and current["strategy"] == "reviewed"
    assert http.post(operation_url(response) + "/recover").json()["enabled"]


def test_changed_native_instance_cannot_receive_old_configuration_initialization(scoped_client, monkeypatch):
    from sqlalchemy import select

    from app.gateway.routers import skills
    from deerflow.database.models import TenantSkill

    http, factory, root = source_tree(scoped_client, monkeypatch)
    initialize = skills.initialize_owned_skill_configuration

    async def replace(tenant, user, name, **kwargs):
        async with factory() as session:
            row = (await session.exec(select(TenantSkill).where(TenantSkill.name == name))).scalars().one()
            values = {key: getattr(row, key) for key in ["id", "tenant_id", "user_id", "name", "category", "enabled", "relative_path", "install_dir"]}
            await session.delete(row)
            await session.commit()
            session.add(TenantSkill(**values))
            await session.commit()
        return await initialize(tenant, user, name, **kwargs)

    monkeypatch.setattr(skills, "initialize_owned_skill_configuration", replace)
    response = create(http, bound_tools=["stale-binding"])
    assert response.status_code == 503
    row = next(row for row in native_rows(factory) if row.name == "manual-created")
    assert not row.enabled
    settings = asyncio.run(service.get_tenant_personal_skill_settings("tenant-a", "user-a"))
    assert "stale-binding" not in settings.get("manual-created", {}).get("bound_tools", [])


def test_bad_manual_intent_is_isolated_without_reading_or_destroying_contents(scoped_client, monkeypatch):
    import json

    http, factory, root = source_tree(scoped_client, monkeypatch)
    response = create(http)
    assert response.status_code == 201, response.text
    receipt = next((root / "custom/tenant-a/user-a").glob(".prismos-import-*.json"))
    value = json.loads(receipt.read_text())
    value["manual_creation"]["configuration_phase"] = []
    receipt.write_text(json.dumps(value))
    listing = http.get("/api/skills/personal/imports")
    assert listing.status_code == 200 and listing.json()["operations"][0]["state"] == "receipt_unavailable"
    assert (root / "custom/tenant-a/user-a/manual-created/SKILL.md").exists()


def test_late_empty_target_is_not_overwritten_or_deleted(scoped_client, monkeypatch):
    from app.integrations import skill_imports

    http, factory, root = source_tree(scoped_client, monkeypatch)
    read = skill_imports.current_row
    target = root / "custom/tenant-a/user-a/manual-created"
    identities = []

    async def late(tenant, owner, name):
        result = await read(tenant, owner, name)
        target.mkdir()
        identities.append(target.stat().st_ino)
        return result

    monkeypatch.setattr(skill_imports, "current_row", late)
    response = create(http)
    assert response.status_code == 409 and target.stat().st_ino == identities[0] and not list(target.iterdir())
    assert len(native_rows(factory)) == 2


def test_missing_current_actor_is_rejected_before_staging(scoped_client, monkeypatch):
    http, factory, root = source_tree(scoped_client, monkeypatch)
    response = http.post("/api/skills/personal", headers={"x-user-id": ""}, json={"name": "manual-created", "description": "Own"})
    assert response.status_code == 401 and len(native_rows(factory)) == 2
    assert not list(root.rglob(".prismos-import-*"))


def test_existing_registry_without_files_remains_a_conflict(scoped_client, monkeypatch):
    import shutil

    http, factory, root = source_tree(scoped_client, monkeypatch)
    target = root / "custom/tenant-a/user-a/collision"
    shutil.rmtree(target)
    response = create(http, name="collision")
    assert response.status_code == 409 and len(native_rows(factory)) == 2 and not target.exists()


def test_shared_manual_same_name_public_has_distinct_custom_category(scoped_client, monkeypatch):
    http, factory, root = source_tree(scoped_client, monkeypatch)
    public = root / "public/manual-created"
    public.mkdir()
    file = public / "SKILL.md"
    file.write_text("---\nname: manual-created\ndescription: Public source\n---\nPUBLIC\n")
    before = file.read_bytes()
    response = create(http, True)
    assert response.status_code == 201 and response.json()["category"] == "custom" and response.json()["scope"] == "tenant"
    assert file.read_bytes() == before


def test_real_process_exit_after_manual_publication_recovers_disabled_intent(scoped_client, monkeypatch):
    import subprocess
    import sys

    http, factory, root = source_tree(scoped_client, monkeypatch)
    archive = root.parent / "interrupted.zip"
    archive.write_bytes(archive_bytes("manual-created"))
    code = """
import asyncio,os,sys
from pathlib import Path
from app.integrations import skill_imports
async def none(*args): return None
async def crash(*args): os._exit(81)
skill_imports.current_row=none
skill_imports.register=crash
asyncio.run(skill_imports.import_archive(Path(sys.argv[1]),'tenant-a','user-a',False,root=Path(sys.argv[2]),manual_creation={'enabled':True,'category':'personal','configuration_phase':'pending'}))
"""
    child = subprocess.run([sys.executable, "-c", code, str(archive), str(root)], timeout=30)
    assert child.returncode == 81
    operation = http.get("/api/skills/personal/imports").json()["operations"][0]
    assert operation["files_verified"] and not operation["registered"] and operation["configuration_phase"] == "pending"
    url = "/api/skills/personal/imports/" + operation["operation_id"]
    recovered = http.post(url + "/recover").json()
    assert recovered["registered"] and not recovered["enabled"] and recovered["requested_enabled"]
