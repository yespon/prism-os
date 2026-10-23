"""Actual owned deletion boundaries; old selection and unknown files are preserved."""

import asyncio

import pytest
from sqlalchemy import select
from test_skill_import_recovery import archive_bytes
from test_skill_import_recovery import scoped_client as recovery_client
from test_skill_mutation_boundaries import native_rows
from test_skill_resource_identity import source_tree

from app.models.agents import CustomAgent
from deerflow.database.models import TenantSkill
from deerflow.skills import installer

scoped_client = recovery_client
ADMIN = {"x-tenant-role": "tenant_admin"}


def test_stale_delete_cannot_remove_current_same_name_instance(scoped_client, monkeypatch):
    http, factory, root = source_tree(scoped_client, monkeypatch)
    target = root / "custom/tenant-a/user-a/collision/SKILL.md"
    before = target.read_bytes()
    response = http.delete("/api/skills/personal/collision", params={"expected_resource_id": "skill:withdrawn"})
    assert response.status_code == 409
    assert target.read_bytes() == before and len(native_rows(factory)) == 2


def test_delete_missing_registry_preserves_actual_native_unknown_publication(scoped_client, monkeypatch):
    http, factory, root = source_tree(scoped_client, monkeypatch)
    archive = root.parent / "unknown.zip"
    archive.write_bytes(archive_bytes("unknown-published"))
    with installer.prepare_skill_installation_from_archive(archive, skills_root=root, target_relative_path="tenant-a/user-a") as prepared:
        result = prepared.publish()
    target = root / "custom/tenant-a/user-a/unknown-published/payload.txt"
    before = target.read_bytes()
    response = http.delete("/api/skills/personal/unknown-published")
    assert response.status_code == 404
    assert target.read_bytes() == before
    assert http.get("/api/skills/personal/imports/" + result["operation_id"]).json()["files_verified"]
    assert len(native_rows(factory)) == 2


def test_mismatched_registered_directory_cannot_delete_canonical_name_files(scoped_client, monkeypatch):
    http, factory, root = source_tree(scoped_client, monkeypatch)
    target = root / "custom/tenant-a/user-a/collision/SKILL.md"
    before = target.read_bytes()

    async def change():
        async with factory() as session:
            row = (await session.exec(select(TenantSkill).where(TenantSkill.user_id == "user-a"))).scalars().one()
            row.install_dir = str(root / "custom/tenant-a/user-b/collision")
            session.add(row)
            await session.commit()

    asyncio.run(change())
    response = http.delete("/api/skills/personal/collision")
    assert response.status_code == 409 and target.read_bytes() == before and len(native_rows(factory)) == 2


def test_explicit_legacy_agent_reference_blocks_physical_reclamation(scoped_client, monkeypatch):
    http, factory, root = source_tree(scoped_client, monkeypatch)

    async def bind():
        async with factory() as session:
            session.add(CustomAgent(id="own-agent", tenant_id="tenant-a", user_id="user-a", name="own-agent", skills=["collision"]))
            await session.commit()

    asyncio.run(bind())
    response = http.delete("/api/skills/personal/collision")
    assert response.status_code == 409
    assert (root / "custom/tenant-a/user-a/collision/SKILL.md").exists() and len(native_rows(factory)) == 2


def test_public_override_removal_preserves_public_and_unregistered_custom_files(scoped_client, monkeypatch):
    http, factory, root = source_tree(scoped_client, monkeypatch)
    before = {p: p.read_bytes() for p in [root / "public/collision/SKILL.md", root / "custom/tenant-a/collision/SKILL.md"]}

    async def override():
        async with factory() as session:
            row = (await session.exec(select(TenantSkill).where(TenantSkill.user_id != "user-a"))).scalars().one()
            row.category = "public"
            row.install_dir = str(root / "public/collision")
            row.relative_path = "collision"
            session.add(row)
            await session.commit()

    asyncio.run(override())
    response = http.delete("/api/tenants/skills/collision", headers=ADMIN)
    assert response.status_code == 204
    assert all(p.exists() and p.read_bytes() == data for p, data in before.items())
    assert len(native_rows(factory)) == 1


def plan(http, name="collision", shared=False):
    prefix = "/api/tenants/skills/" if shared else "/api/skills/personal/"
    response = http.get(prefix + name + "/deletion-preflight", headers=ADMIN if shared else {})
    assert response.status_code == 200, response.text
    body = response.json()
    return {"expected_resource_id": body["resource_id"], "expected_tree_sha256": body["tree_sha256"]}


def delete(http, name="collision", shared=False, **params):
    prefix = "/api/tenants/skills/" if shared else "/api/skills/personal/"
    return http.delete(prefix + name, headers=ADMIN if shared else {}, params=params)


def operation(http, response, shared=False):
    prefix = "/api/tenants/skills/imports/" if shared else "/api/skills/personal/imports/"
    url = prefix + response.json()["detail"]["operation_id"]
    value = http.get(url, headers=ADMIN if shared else {}).json()
    return url, value


@pytest.mark.parametrize("shared", [False, True])
def test_owned_tree_and_original_configuration_are_reclaimed(scoped_client, monkeypatch, shared):
    from deerflow.database import user_config_service as service

    http, factory, root = source_tree(scoped_client, monkeypatch)
    target = root / "custom/tenant-a" / ("" if shared else "user-a") / "collision"
    (target / "references").mkdir()
    (target / "references/owned.txt").write_text("owned reference")
    if shared:
        asyncio.run(service.update_tenant_shared_skill_settings("tenant-a", "collision", bound_tools=["old-binding"]))
    else:
        asyncio.run(service.update_tenant_personal_skill_settings("tenant-a", "user-a", "collision", bound_tools=["old-binding"]))
    before = {p: p.read_bytes() for p in root.rglob("SKILL.md") if not p.is_relative_to(target)}
    response = delete(http, shared=shared, **plan(http, shared=shared))
    assert response.status_code == 204, response.text
    assert not target.exists() and len(native_rows(factory)) == 1
    assert all(p.read_bytes() == value for p, value in before.items())
    settings = asyncio.run(service.get_tenant_shared_skill_settings("tenant-a") if shared else service.get_tenant_personal_skill_settings("tenant-a", "user-a"))
    assert "collision" not in settings
    prefix = "/api/tenants/skills/imports" if shared else "/api/skills/personal/imports"
    records = http.get(prefix, headers=ADMIN if shared else {}).json()["operations"]
    assert len(records) == 1 and records[0]["state"] == "reclaimed" and records[0]["withdrawn"]
    assert not list(target.parent.glob(".prismos-stage-*"))


def test_withdrawn_original_import_cannot_be_restored_or_rebound_to_new_same_name(scoped_client, monkeypatch):
    http, factory, root = source_tree(scoped_client, monkeypatch)
    imported = http.post("/api/skills/personal/import", files={"archive": ("source.zip", archive_bytes())})
    assert imported.status_code == 201
    old_url = "/api/skills/personal/imports/" + http.get("/api/skills/personal/imports").json()["operations"][0]["operation_id"]
    assert delete(http, "demo-skill", **plan(http, "demo-skill")).status_code == 204
    assert http.get(old_url).json()["state"] == "withdrawn" and http.post(old_url + "/recover").status_code == 409
    recreated = http.post("/api/skills/personal", json={"name": "demo-skill", "description": "New instance", "instructions": "NEW SAME NAME"})
    assert recreated.status_code == 201
    assert http.post(old_url + "/recover").status_code == 409
    assert "NEW SAME NAME" in (root / "custom/tenant-a/user-a/demo-skill/SKILL.md").read_text()


def test_current_full_tree_change_is_a_conflict_without_any_removal(scoped_client, monkeypatch):
    http, factory, root = source_tree(scoped_client, monkeypatch)
    selection = plan(http)
    extra = root / "custom/tenant-a/user-a/collision/late.txt"
    extra.write_text("late contents")
    response = delete(http, **selection)
    assert response.status_code == 409 and extra.read_text() == "late contents" and len(native_rows(factory)) == 2


def test_all_actor_scope_denials_happen_before_operation_or_files_change(scoped_client, monkeypatch):
    http, factory, root = source_tree(scoped_client, monkeypatch)
    selected = plan(http)
    assert http.delete("/api/skills/personal/collision", headers={"x-user-id": ""}, params=selected).status_code == 401
    assert http.delete("/api/tenants/skills/collision").status_code == 403
    assert http.delete("/api/skills/personal/collision", headers={"x-user-id": "user-b"}, params=selected).status_code == 404
    assert http.delete("/api/skills/personal/collision", headers={"x-tenant-id": "tenant-b"}, params=selected).status_code == 404
    assert len(native_rows(factory)) == 2 and not list(root.rglob(".prismos-import-*"))


def test_member_cannot_inspect_or_resume_shared_deletion(scoped_client, monkeypatch):
    from app.integrations import skill_deletions

    http, factory, root = source_tree(scoped_client, monkeypatch)
    assert http.get("/api/tenants/skills/collision/deletion-preflight").status_code == 403

    def interrupt(*args, **kwargs):
        raise OSError("owned reclamation interruption")

    monkeypatch.setattr(skill_deletions, "finish_reclamation", interrupt)
    response = delete(http, shared=True, **plan(http, shared=True))
    assert response.status_code == 503
    url, value = operation(http, response, True)
    assert value["withdrawn"] and value["kind"] == "resource_delete"
    assert http.get(url).status_code == 403 and http.post(url + "/recover").status_code == 403


def test_configuration_and_native_withdrawal_before_commit_rollback_are_inspectable(scoped_client, monkeypatch):
    from sqlalchemy import event
    from sqlmodel.ext.asyncio.session import AsyncSession

    from deerflow.database import user_config_service as service

    http, factory, root = source_tree(scoped_client, monkeypatch)
    asyncio.run(service.update_tenant_personal_skill_settings("tenant-a", "user-a", "collision", bound_tools=["owned-binding"]))

    def fail(session):
        if any(isinstance(row, TenantSkill) and row.name == "collision" for row in session.deleted):
            raise RuntimeError("injected original withdrawal transaction failure")

    event.listen(AsyncSession.sync_session_class, "before_commit", fail)
    try:
        response = delete(http, **plan(http))
    finally:
        event.remove(AsyncSession.sync_session_class, "before_commit", fail)
    assert response.status_code == 503
    url, value = operation(http, response)
    assert value["registered"] and value["state"] == "deletion_pending"
    assert len(native_rows(factory)) == 2
    assert asyncio.run(service.get_tenant_personal_skill_settings("tenant-a", "user-a"))["collision"]["bound_tools"] == ["owned-binding"]
    result = http.post(url + "/recover")
    assert result.status_code == 200 and result.json()["state"] == "reclaimed"
    assert len(native_rows(factory)) == 1 and "collision" not in asyncio.run(service.get_tenant_personal_skill_settings("tenant-a", "user-a"))


def test_actual_withdrawal_commit_then_timeout_does_not_restore_original_contents(scoped_client, monkeypatch):
    from sqlalchemy import event
    from sqlmodel.ext.asyncio.session import AsyncSession

    http, factory, root = source_tree(scoped_client, monkeypatch)

    def before(session):
        if any(isinstance(row, TenantSkill) and row.name == "collision" for row in session.deleted):
            session.info["owned_delete_test"] = True

    def after(session):
        if session.info.get("owned_delete_test"):
            raise TimeoutError("injected delivery after actual withdrawal commit")

    event.listen(AsyncSession.sync_session_class, "before_commit", before)
    event.listen(AsyncSession.sync_session_class, "after_commit", after)
    try:
        response = delete(http, **plan(http))
    finally:
        event.remove(AsyncSession.sync_session_class, "before_commit", before)
        event.remove(AsyncSession.sync_session_class, "after_commit", after)
    assert response.status_code == 503 and len(native_rows(factory)) == 1
    url, value = operation(http, response)
    assert value["withdrawn"] and value["state"] == "reclamation_pending"
    assert http.post(url + "/recover").json()["state"] == "reclaimed"
    assert not (root / "custom/tenant-a/user-a/collision").exists()


def test_partial_owned_cleanup_is_resumed_without_guessing_other_members(scoped_client, monkeypatch):
    import os

    from deerflow.skills.resource_deletion_files import OwnedRemoval

    http, factory, root = source_tree(scoped_client, monkeypatch)
    target = root / "custom/tenant-a/user-a/collision"
    (target / "remaining.txt").write_text("remaining original")
    original = OwnedRemoval._remove

    def partial(self, fd, prefix, expected):
        if prefix == ".":
            os.unlink("SKILL.md", dir_fd=fd)
            raise OSError("injected cleanup after one owned member")
        return original(self, fd, prefix, expected)

    with monkeypatch.context() as patch:
        patch.setattr(OwnedRemoval, "_remove", partial)
        response = delete(http, **plan(http))
    assert response.status_code == 503
    url, value = operation(http, response)
    assert value["phase"] == "delete_reclaiming" and value["files_verified"]
    assert http.post(url + "/recover").json()["state"] == "reclaimed"
    assert not list(target.parent.glob(".prismos-stage-*"))


def test_changed_quarantine_is_not_reclaimed_as_owned(scoped_client, monkeypatch):
    from app.integrations import skill_deletions

    http, factory, root = source_tree(scoped_client, monkeypatch)

    def interrupt(*args, **kwargs):
        raise OSError("reclamation unavailable")

    with monkeypatch.context() as patch:
        patch.setattr(skill_deletions, "finish_reclamation", interrupt)
        response = delete(http, **plan(http))
    stage = next((root / "custom/tenant-a/user-a").glob(".prismos-stage-*"))
    foreign = stage / "foreign.txt"
    foreign.write_text("unverified added content")
    url, value = operation(http, response)
    assert value["state"] == "deletion_files_unverified"
    assert http.post(url + "/recover").status_code == 409 and foreign.read_text() == "unverified added content"


def test_new_same_name_instance_and_configuration_survive_old_deletion_recovery(scoped_client, monkeypatch):
    from app.integrations import skill_deletions
    from deerflow.database import user_config_service as service

    http, factory, root = source_tree(scoped_client, monkeypatch)

    def interrupt(*args, **kwargs):
        raise OSError("reclamation unavailable")

    with monkeypatch.context() as patch:
        patch.setattr(skill_deletions, "finish_reclamation", interrupt)
        response = delete(http, **plan(http))
    replacement = http.post("/api/skills/personal", json={"name": "collision", "description": "Replacement instance", "instructions": "NEW INSTANCE BODY", "bound_tools": ["new-binding"]})
    assert replacement.status_code == 201, replacement.text
    url, _ = operation(http, response)
    assert http.post(url + "/recover").json()["state"] == "reclaimed"
    row = next(row for row in native_rows(factory) if row.user_id == "user-a")
    assert row.enabled and "NEW INSTANCE BODY" in (root / "custom/tenant-a/user-a/collision/SKILL.md").read_text()
    assert asyncio.run(service.get_tenant_personal_skill_settings("tenant-a", "user-a"))["collision"]["bound_tools"] == ["new-binding"]


def test_missing_files_registry_can_be_withdrawn_without_touching_other_names(scoped_client, monkeypatch):
    import shutil

    http, factory, root = source_tree(scoped_client, monkeypatch)
    shutil.rmtree(root / "custom/tenant-a/user-a/collision")
    before = (root / "custom/tenant-a/collision/SKILL.md").read_bytes()
    assert delete(http, **plan(http)).status_code == 204 and len(native_rows(factory)) == 1
    assert (root / "custom/tenant-a/collision/SKILL.md").read_bytes() == before


def test_legacy_name_delete_stays_scoped_to_current_registered_owner(scoped_client, monkeypatch):
    http, factory, root = source_tree(scoped_client, monkeypatch)
    assert delete(http).status_code == 204
    assert not (root / "custom/tenant-a/user-a/collision").exists()
    assert (root / "custom/tenant-a/collision/SKILL.md").exists() and (root / "public/collision/SKILL.md").exists()


def test_public_preflight_conditions_the_native_override_generation(scoped_client, monkeypatch):
    http, factory, root = source_tree(scoped_client, monkeypatch)

    async def override():
        async with factory() as session:
            row = (await session.exec(select(TenantSkill).where(TenantSkill.user_id != "user-a"))).scalars().one()
            row.category = "public"
            row.install_dir = str(root / "public/collision")
            row.relative_path = "collision"
            session.add(row)
            await session.commit()

    asyncio.run(override())
    before = (root / "public/collision/SKILL.md").read_bytes()
    selected = plan(http, shared=True)
    assert selected["expected_resource_id"].startswith("skill:")

    async def change_generation():
        from datetime import timedelta

        async with factory() as session:
            row = (await session.exec(select(TenantSkill).where(TenantSkill.user_id != "user-a"))).scalars().one()
            row.created_at += timedelta(seconds=1)
            session.add(row)
            await session.commit()

    asyncio.run(change_generation())
    assert delete(http, shared=True, **selected).status_code == 409
    assert len(native_rows(factory)) == 2 and (root / "public/collision/SKILL.md").read_bytes() == before


def test_replaced_quarantine_root_is_preserved_and_cannot_resume(scoped_client, monkeypatch):
    from app.integrations import skill_deletions

    http, factory, root = source_tree(scoped_client, monkeypatch)

    def interrupt(*args, **kwargs):
        raise OSError("reclamation unavailable")

    with monkeypatch.context() as patch:
        patch.setattr(skill_deletions, "finish_reclamation", interrupt)
        response = delete(http, **plan(http))
    stage = next((root / "custom/tenant-a/user-a").glob(".prismos-stage-*"))
    preserved = stage.with_name("preserved-original")
    stage.rename(preserved)
    stage.mkdir()
    foreign = stage / "SKILL.md"
    foreign.write_text("foreign replacement")
    url, value = operation(http, response)
    assert value["state"] == "deletion_files_unverified"
    assert http.post(url + "/recover").status_code == 409
    assert foreign.read_text() == "foreign replacement" and (preserved / "SKILL.md").exists()
