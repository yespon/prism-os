"""Actual native mutation failures; denied requests must preserve DB and files."""

import asyncio

from fastapi.testclient import TestClient
from sqlalchemy import select
from test_skill_import_recovery import scoped_client as recovery_client
from test_skill_resource_identity import source_tree

from deerflow.database.models import TenantSkill

scoped_client = recovery_client


def native_rows(factory):
    async def read():
        async with factory() as session:
            return (await session.exec(select(TenantSkill))).scalars().all()

    return asyncio.run(read())


def test_member_shared_patch_cannot_change_native_state_before_rejection(scoped_client, monkeypatch):
    http, factory, root = source_tree(scoped_client, monkeypatch)
    before = (root / "custom/tenant-a/collision/SKILL.md").read_bytes()
    with TestClient(http.app, raise_server_exceptions=False) as client:
        response = client.patch("/api/tenants/skills/collision", json={"enabled": False})
    assert response.status_code == 403
    assert next(row for row in native_rows(factory) if row.user_id != "user-a").enabled
    assert (root / "custom/tenant-a/collision/SKILL.md").read_bytes() == before


def test_personal_patch_rejects_foreign_path_before_db_or_file_changes(scoped_client, monkeypatch):
    http, factory, root = source_tree(scoped_client, monkeypatch)
    foreign = root / "custom/tenant-a/user-b/collision"
    foreign.mkdir(parents=True)
    target = foreign / "SKILL.md"
    target.write_text("---\nname: collision\ndescription: OTHER USER\n---\nPRIVATE BODY\n")

    async def point_at_foreign():
        async with factory() as session:
            row = (await session.exec(select(TenantSkill).where(TenantSkill.user_id == "user-a"))).scalars().one()
            row.install_dir = str(foreign)
            session.add(row)
            await session.commit()

    asyncio.run(point_at_foreign())
    before = target.read_bytes()
    response = http.patch("/api/skills/personal/collision", json={"enabled": False, "description": "changed", "instructions": "overwritten"})
    assert response.status_code == 409
    assert next(row for row in native_rows(factory) if row.user_id == "user-a").enabled
    assert target.read_bytes() == before


def test_public_patch_rejected_before_changing_tenant_override(scoped_client, monkeypatch):
    http, factory, root = source_tree(scoped_client, monkeypatch)

    async def public_override():
        async with factory() as session:
            row = (await session.exec(select(TenantSkill).where(TenantSkill.user_id != "user-a"))).scalars().one()
            row.category = "public"
            row.install_dir = str(root / "public/collision")
            row.relative_path = "collision"
            session.add(row)
            await session.commit()

    asyncio.run(public_override())
    before = (root / "public/collision/SKILL.md").read_bytes()
    with TestClient(http.app, raise_server_exceptions=False) as client:
        response = client.patch("/api/tenants/skills/collision", headers={"x-tenant-role": "tenant_admin"}, json={"enabled": False, "description": "changed", "instructions": "overwrite public"})
    assert response.status_code == 403
    assert next(row for row in native_rows(factory) if row.user_id != "user-a").enabled
    assert (root / "public/collision/SKILL.md").read_bytes() == before


def test_stale_instance_patch_cannot_update_same_name_row(scoped_client, monkeypatch):
    http, factory, root = source_tree(scoped_client, monkeypatch)
    before = (root / "custom/tenant-a/user-a/collision/SKILL.md").read_bytes()
    response = http.patch("/api/skills/personal/collision", json={"expected_resource_id": "skill:withdrawn", "enabled": False})
    assert response.status_code == 409
    assert next(row for row in native_rows(factory) if row.user_id == "user-a").enabled
    assert (root / "custom/tenant-a/user-a/collision/SKILL.md").read_bytes() == before


def personal_detail(http):
    response = http.get("/api/skills/collision/detail", params={"scope": "personal"})
    assert response.status_code == 200
    return response.json()


def test_personal_edit_preserves_instance_updates_owned_file_and_original_state(scoped_client, monkeypatch):
    http, factory, root = source_tree(scoped_client, monkeypatch)
    detail = personal_detail(http)
    file = root / "custom/tenant-a/user-a/collision/SKILL.md"
    mode = file.stat().st_mode & 0o777
    shared = (root / "custom/tenant-a/collision/SKILL.md").read_bytes()
    response = http.patch(
        "/api/skills/personal/collision",
        json={"expected_resource_id": detail["resource_id"], "expected_file_sha256": detail["file_sha256"], "enabled": False, "description": "Edited own description", "instructions": "NEW OWN BODY", "strategy": "reviewed"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["resource_id"] == detail["resource_id"] and body["file_sha256"] != detail["file_sha256"]
    assert body["instructions"] == "NEW OWN BODY" and body["version"] == 2 and body["strategy"] == "reviewed" and not body["enabled"]
    assert file.stat().st_mode & 0o777 == mode
    assert (root / "custom/tenant-a/collision/SKILL.md").read_bytes() == shared
    assert not list(file.parent.glob(".prismos-edit-*"))
    assert not next(row for row in native_rows(factory) if row.user_id == "user-a").enabled


def test_shared_admin_edit_reads_frontmatter_and_preserves_personal_and_public(scoped_client, monkeypatch):
    http, factory, root = source_tree(scoped_client, monkeypatch)
    detail = http.get("/api/skills/collision/detail", params={"scope": "tenant"}, headers={"x-tenant-role": "tenant_admin"}).json()
    unchanged = {p: p.read_bytes() for p in [root / "public/collision/SKILL.md", root / "custom/tenant-a/user-a/collision/SKILL.md"]}
    response = http.patch(
        "/api/tenants/skills/collision",
        headers={"x-tenant-role": "tenant_admin"},
        json={"expected_resource_id": detail["resource_id"], "expected_file_sha256": detail["file_sha256"], "description": "New shared description", "instructions": "NEW SHARED BODY"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["instructions"] == "NEW SHARED BODY" and response.json()["scope"] == "tenant"
    assert unchanged == {p: p.read_bytes() for p in unchanged}
    assert len(native_rows(factory)) == 2


def test_stale_content_digest_cannot_overwrite_a_later_edit(scoped_client, monkeypatch):
    http, factory, root = source_tree(scoped_client, monkeypatch)
    detail = personal_detail(http)
    file = root / "custom/tenant-a/user-a/collision/SKILL.md"
    file.write_bytes(file.read_bytes().replace(b"PERSONAL ONLY", b"LATER BODY"))
    before = file.read_bytes()
    response = http.patch("/api/skills/personal/collision", json={"expected_resource_id": detail["resource_id"], "expected_file_sha256": detail["file_sha256"], "enabled": False, "instructions": "OLD FORM"})
    assert response.status_code == 409 and file.read_bytes() == before
    assert next(row for row in native_rows(factory) if row.user_id == "user-a").enabled


def test_reserved_public_category_cannot_convert_an_owned_instance(scoped_client, monkeypatch):
    http, factory, root = source_tree(scoped_client, monkeypatch)
    before = (root / "custom/tenant-a/user-a/collision/SKILL.md").read_bytes()
    response = http.patch("/api/skills/personal/collision", json={"category": "public", "enabled": False})
    assert response.status_code == 403
    assert next(row for row in native_rows(factory) if row.user_id == "user-a").category == "custom"
    assert (root / "custom/tenant-a/user-a/collision/SKILL.md").read_bytes() == before


def test_main_file_alias_is_rejected_without_reading_or_changing_target(scoped_client, monkeypatch, tmp_path):
    http, factory, root = source_tree(scoped_client, monkeypatch)
    target = tmp_path / "private.md"
    target.write_text("PRIVATE TARGET")
    file = root / "custom/tenant-a/user-a/collision/SKILL.md"
    file.unlink()
    file.symlink_to(target)
    response = http.patch("/api/skills/personal/collision", json={"enabled": False, "instructions": "replace target"})
    assert response.status_code == 409 and target.read_text() == "PRIVATE TARGET" and file.is_symlink()
    assert next(row for row in native_rows(factory) if row.user_id == "user-a").enabled


def test_replaced_directory_is_not_edited_or_cleaned_as_owned(scoped_client, monkeypatch):
    import shutil

    from app.integrations import skill_mutations

    http, factory, root = source_tree(scoped_client, monkeypatch)
    directory = root / "custom/tenant-a/user-a/collision"
    old = directory.with_name("original-owned-directory")
    prepare = skill_mutations.OwnedMarkdown.prepare

    def replaced(self, content):
        prepare(self, content)
        directory.rename(old)
        shutil.copytree(old, directory)
        (directory / "SKILL.md").write_text("NEW DIRECTORY FILE")

    monkeypatch.setattr(skill_mutations.OwnedMarkdown, "prepare", replaced)
    response = http.patch("/api/skills/personal/collision", json={"enabled": False, "instructions": "unexpected update"})
    assert response.status_code == 409
    assert (directory / "SKILL.md").read_text() == "NEW DIRECTORY FILE"
    assert b"PERSONAL ONLY" in (old / "SKILL.md").read_bytes()
    assert not list(old.glob(".prismos-edit-*"))
    assert next(row for row in native_rows(factory) if row.user_id == "user-a").enabled


def test_file_change_between_prepare_and_publish_preserves_later_file(scoped_client, monkeypatch):
    from app.integrations import skill_mutations

    http, factory, root = source_tree(scoped_client, monkeypatch)
    file = root / "custom/tenant-a/user-a/collision/SKILL.md"
    prepare = skill_mutations.OwnedMarkdown.prepare

    def changed(self, content):
        prepare(self, content)
        file.write_text("LATER EXTERNAL EDIT")

    monkeypatch.setattr(skill_mutations.OwnedMarkdown, "prepare", changed)
    response = http.patch("/api/skills/personal/collision", json={"enabled": False, "instructions": "old update"})
    assert response.status_code == 409 and file.read_text() == "LATER EXTERNAL EDIT"
    assert not list(file.parent.glob(".prismos-edit-*"))
    assert next(row for row in native_rows(factory) if row.user_id == "user-a").enabled


def test_failure_after_file_replace_is_unknown_and_never_restores_old_bytes(scoped_client, monkeypatch):
    from app.integrations import skill_mutations

    http, factory, root = source_tree(scoped_client, monkeypatch)
    detail = personal_detail(http)
    publish = skill_mutations.OwnedMarkdown.publish

    def interrupted(self):
        publish(self)
        raise TimeoutError("injected response after replacement")

    monkeypatch.setattr(skill_mutations.OwnedMarkdown, "publish", interrupted)
    response = http.patch("/api/skills/personal/collision", json={"expected_resource_id": detail["resource_id"], "enabled": False, "instructions": "PUBLISHED NEW BODY"})
    assert response.status_code == 503 and response.json()["detail"]["inspection_required"]
    assert response.json()["detail"]["resource_id"] == detail["resource_id"]
    assert b"PUBLISHED NEW BODY" in (root / "custom/tenant-a/user-a/collision/SKILL.md").read_bytes()
    assert next(row for row in native_rows(factory) if row.user_id == "user-a").enabled
    assert personal_detail(http)["instructions"] == "PUBLISHED NEW BODY"


def test_actual_commit_followed_by_transport_failure_preserves_committed_facts(scoped_client, monkeypatch):
    from sqlalchemy import event
    from sqlmodel.ext.asyncio.session import AsyncSession

    http, factory, root = source_tree(scoped_client, monkeypatch)
    detail = personal_detail(http)

    def failed_delivery(session):
        raise TimeoutError("injected response after native commit")

    event.listen(AsyncSession.sync_session_class, "after_commit", failed_delivery)
    try:
        response = http.patch("/api/skills/personal/collision", json={"expected_resource_id": detail["resource_id"], "enabled": False, "instructions": "COMMITTED BODY"})
    finally:
        event.remove(AsyncSession.sync_session_class, "after_commit", failed_delivery)
    assert response.status_code == 503 and response.json()["detail"]["inspection_required"]
    assert not next(row for row in native_rows(factory) if row.user_id == "user-a").enabled
    assert personal_detail(http)["instructions"] == "COMMITTED BODY"
    assert b"COMMITTED BODY" in (root / "custom/tenant-a/user-a/collision/SKILL.md").read_bytes()


def test_settings_failure_is_unknown_and_preserves_the_completed_native_edit(scoped_client, monkeypatch):
    from deerflow.database import user_config_service

    http, factory, root = source_tree(scoped_client, monkeypatch)

    async def fail_settings(*args, **kwargs):
        raise RuntimeError("injected settings commit unknown")

    monkeypatch.setattr(user_config_service, "update_tenant_personal_skill_settings", fail_settings)
    response = http.patch("/api/skills/personal/collision", json={"enabled": False, "instructions": "KEPT BODY", "strategy": "new"})
    assert response.status_code == 503 and response.json()["detail"]["inspection_required"]
    assert not next(row for row in native_rows(factory) if row.user_id == "user-a").enabled
    assert b"KEPT BODY" in (root / "custom/tenant-a/user-a/collision/SKILL.md").read_bytes()


def test_invalid_description_has_no_native_or_file_side_effect(scoped_client, monkeypatch):
    http, factory, root = source_tree(scoped_client, monkeypatch)
    file = root / "custom/tenant-a/user-a/collision/SKILL.md"
    before = file.read_bytes()
    response = http.patch("/api/skills/personal/collision", json={"enabled": False, "description": "   "})
    assert response.status_code == 400 and file.read_bytes() == before
    assert next(row for row in native_rows(factory) if row.user_id == "user-a").enabled


def test_legacy_name_edit_remains_current_owner_scoped(scoped_client, monkeypatch):
    http, factory, root = source_tree(scoped_client, monkeypatch)
    file = root / "custom/tenant-a/user-a/collision/SKILL.md"
    before = file.read_bytes()
    response = http.patch("/api/skills/personal/collision", json={"enabled": False})
    assert response.status_code == 200 and not response.json()["enabled"]
    assert file.read_bytes() == before
    assert next(row for row in native_rows(factory) if row.user_id != "user-a").enabled
