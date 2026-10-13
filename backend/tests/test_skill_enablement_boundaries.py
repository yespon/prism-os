"""Native tenant enablement must target the selected current resource."""

import asyncio

from sqlalchemy import select
from test_skill_import_recovery import scoped_client as recovery_client
from test_skill_mutation_boundaries import native_rows
from test_skill_resource_identity import source_tree

from deerflow.database.models import TenantSkill

scoped_client = recovery_client
ADMIN = {"x-tenant-role": "tenant_admin"}


def resources(http):
    return {item["scope"]: item for item in http.get("/api/skills/available", headers=ADMIN).json()["skills"]}


def test_stale_instance_toggle_cannot_update_same_name_row(scoped_client, monkeypatch):
    http, factory, root = source_tree(scoped_client, monkeypatch)
    response = http.put("/api/tenants/skills/collision", headers=ADMIN, json={"enabled": False, "expected_resource_id": "skill:withdrawn"})
    assert response.status_code == 409
    assert all(row.enabled for row in native_rows(factory))


def test_selected_public_toggle_cannot_modify_same_name_shared_resource(scoped_client, monkeypatch):
    http, factory, root = source_tree(scoped_client, monkeypatch)
    before = {p: p.read_bytes() for p in root.rglob("SKILL.md")}
    response = http.put("/api/tenants/skills/collision", headers=ADMIN, json={"enabled": False, "expected_resource_id": resources(http)["global"]["resource_id"]})
    assert response.status_code == 409
    assert all(row.enabled for row in native_rows(factory))
    assert before == {p: p.read_bytes() for p in before}


def test_unknown_name_toggle_cannot_create_an_unowned_registration(scoped_client, monkeypatch):
    http, factory, root = source_tree(scoped_client, monkeypatch)
    response = http.put("/api/tenants/skills/absent", headers=ADMIN, json={"enabled": False})
    assert response.status_code == 404
    assert len(native_rows(factory)) == 2
    assert not (root / "custom/absent").exists()


def test_foreign_location_toggle_cannot_change_native_state(scoped_client, monkeypatch):
    http, factory, root = source_tree(scoped_client, monkeypatch)

    async def replace():
        async with factory() as session:
            row = (await session.exec(select(TenantSkill).where(TenantSkill.user_id != "user-a"))).scalars().one()
            row.install_dir = str(root / "custom/tenant-b/collision")
            session.add(row)
            await session.commit()

    asyncio.run(replace())
    response = http.put("/api/tenants/skills/collision", headers=ADMIN, json={"enabled": False})
    assert response.status_code == 409
    assert all(row.enabled for row in native_rows(factory))


def test_concrete_shared_toggle_only_changes_its_native_state(scoped_client, monkeypatch):
    http, factory, root = source_tree(scoped_client, monkeypatch)
    shared = resources(http)["tenant"]
    before = {p: p.read_bytes() for p in root.rglob("SKILL.md")}
    response = http.put("/api/tenants/skills/collision", headers=ADMIN, json={"enabled": False, "expected_resource_id": shared["resource_id"]})
    assert response.status_code == 200, response.text
    assert response.json()["resource_id"] == shared["resource_id"] and response.json()["scope"] == "tenant"
    assert not response.json()["enabled"]
    assert next(row for row in native_rows(factory) if row.user_id == "user-a").enabled
    assert resources(http)["global"]["enabled"]
    assert before == {p: p.read_bytes() for p in before}


def remove_shared(factory):
    async def remove():
        async with factory() as session:
            row = (await session.exec(select(TenantSkill).where(TenantSkill.user_id != "user-a"))).scalars().one()
            await session.delete(row)
            await session.commit()

    asyncio.run(remove())


def test_concrete_public_toggle_creates_only_native_tenant_override(scoped_client, monkeypatch):
    http, factory, root = source_tree(scoped_client, monkeypatch)
    remove_shared(factory)
    public = resources(http)["global"]
    before = {p: p.read_bytes() for p in root.rglob("SKILL.md")}
    for enabled in [False, True]:
        response = http.put("/api/tenants/skills/collision", headers=ADMIN, json={"enabled": enabled, "expected_resource_id": public["resource_id"]})
        assert response.status_code == 200, response.text
        assert response.json()["scope"] == "global" and response.json()["resource_id"] == public["resource_id"]
        assert resources(http)["global"]["enabled"] == enabled
        shared = next(row for row in native_rows(factory) if row.user_id != "user-a")
        assert shared.category == "public" and shared.install_dir == str(root / "public/collision")
        assert shared.relative_path == "collision"
    assert len(native_rows(factory)) == 2
    assert before == {p: p.read_bytes() for p in before}


def test_legacy_name_selects_existing_shared_before_public(scoped_client, monkeypatch):
    http, factory, root = source_tree(scoped_client, monkeypatch)
    response = http.put("/api/tenants/skills/collision", headers=ADMIN, json={"enabled": False})
    assert response.status_code == 200 and response.json()["scope"] == "tenant"
    assert resources(http)["global"]["enabled"]


def test_legacy_public_name_remains_compatible_without_shared_collision(scoped_client, monkeypatch):
    http, factory, root = source_tree(scoped_client, monkeypatch)
    remove_shared(factory)
    response = http.put("/api/tenants/skills/collision", headers=ADMIN, json={"enabled": False})
    assert response.status_code == 200 and response.json()["scope"] == "global"
    assert not resources(http)["global"]["enabled"]


def test_member_and_cross_actor_instance_rejected_before_changes(scoped_client, monkeypatch):
    http, factory, root = source_tree(scoped_client, monkeypatch)
    own = resources(http)["personal"]
    assert http.put("/api/tenants/skills/collision", json={"enabled": False}).status_code == 403
    assert http.put("/api/tenants/skills/collision", headers={**ADMIN, "x-user-role": "admin", "x-tenant-role": "tenant_member"}, json={"enabled": False}).status_code == 403
    assert http.put("/api/tenants/skills/collision", headers=ADMIN, json={"enabled": False, "expected_resource_id": own["resource_id"]}).status_code == 409
    assert all(row.enabled for row in native_rows(factory))


def test_old_shared_id_cannot_toggle_a_recreated_row(scoped_client, monkeypatch):
    http, factory, root = source_tree(scoped_client, monkeypatch)
    old = resources(http)["tenant"]["resource_id"]

    async def recreate():
        async with factory() as session:
            row = (await session.exec(select(TenantSkill).where(TenantSkill.user_id != "user-a"))).scalars().one()
            values = {key: getattr(row, key) for key in ["id", "tenant_id", "user_id", "name", "category", "enabled", "relative_path", "install_dir"]}
            await session.delete(row)
            await session.commit()
            session.add(TenantSkill(**values))
            await session.commit()

    asyncio.run(recreate())
    assert resources(http)["tenant"]["resource_id"] != old
    assert http.put("/api/tenants/skills/collision", headers=ADMIN, json={"enabled": False, "expected_resource_id": old}).status_code == 409
    assert all(row.enabled for row in native_rows(factory))


def test_missing_owned_file_can_be_disabled_but_not_enabled(scoped_client, monkeypatch):
    http, factory, root = source_tree(scoped_client, monkeypatch)
    shared = resources(http)["tenant"]
    (root / "custom/tenant-a/collision/SKILL.md").unlink()
    disabled = http.put("/api/tenants/skills/collision", headers=ADMIN, json={"enabled": False, "expected_resource_id": shared["resource_id"]})
    assert disabled.status_code == 200 and disabled.json()["files_status"] == "missing"
    assert http.put("/api/tenants/skills/collision", headers=ADMIN, json={"enabled": True, "expected_resource_id": shared["resource_id"]}).status_code == 409
    assert not next(row for row in native_rows(factory) if row.user_id != "user-a").enabled


def test_removed_public_does_not_fall_back_to_shared(scoped_client, monkeypatch):
    http, factory, root = source_tree(scoped_client, monkeypatch)
    public = resources(http)["global"]
    remove_shared(factory)
    (root / "public/collision/SKILL.md").unlink()
    response = http.put("/api/tenants/skills/collision", headers=ADMIN, json={"enabled": False, "expected_resource_id": public["resource_id"]})
    assert response.status_code == 404
    assert len(native_rows(factory)) == 1


def test_actual_toggle_commit_then_timeout_requires_inspection(scoped_client, monkeypatch):
    from sqlalchemy import event
    from sqlmodel.ext.asyncio.session import AsyncSession

    http, factory, root = source_tree(scoped_client, monkeypatch)
    shared = resources(http)["tenant"]
    before = {p: p.read_bytes() for p in root.rglob("SKILL.md")}

    def interrupt(session):
        raise TimeoutError("injected enablement commit delivery failure")

    event.listen(AsyncSession.sync_session_class, "after_commit", interrupt)
    try:
        response = http.put("/api/tenants/skills/collision", headers=ADMIN, json={"enabled": False, "expected_resource_id": shared["resource_id"]})
    finally:
        event.remove(AsyncSession.sync_session_class, "after_commit", interrupt)
    assert response.status_code == 503 and response.json()["detail"]["inspection_required"]
    assert response.json()["detail"]["resource_id"] == shared["resource_id"]
    assert not resources(http)["tenant"]["enabled"]
    assert before == {p: p.read_bytes() for p in before}


def test_response_failure_preserves_committed_toggle(scoped_client, monkeypatch):
    from app.gateway.routers import skills

    http, factory, root = source_tree(scoped_client, monkeypatch)
    shared = resources(http)["tenant"]

    async def fail_response(*args, **kwargs):
        raise RuntimeError("injected enablement response read failure")

    monkeypatch.setattr(skills, "get_skill_detail", fail_response)
    response = http.put("/api/tenants/skills/collision", headers=ADMIN, json={"enabled": False, "expected_resource_id": shared["resource_id"]})
    assert response.status_code == 503 and response.json()["detail"]["inspection_required"]
    assert not next(row for row in native_rows(factory) if row.user_id != "user-a").enabled


def test_public_override_is_tenant_scoped_and_public_bytes_remain_shared(scoped_client, monkeypatch):
    http, factory, root = source_tree(scoped_client, monkeypatch)
    remove_shared(factory)
    public = resources(http)["global"]
    response = http.put("/api/tenants/skills/collision", headers={**ADMIN, "x-tenant-id": "tenant-b"}, json={"enabled": False, "expected_resource_id": public["resource_id"]})
    assert response.status_code == 200 and not response.json()["enabled"]
    assert resources(http)["global"]["enabled"]
    row = next(row for row in native_rows(factory) if row.category == "public")
    assert row.tenant_id == "tenant-b" and row.user_id == "__tenant_shared_skill__:tenant-b"


def test_filesystem_alias_cannot_be_enabled_or_disabled(scoped_client, monkeypatch):
    import shutil

    http, factory, root = source_tree(scoped_client, monkeypatch)
    shared = resources(http)["tenant"]
    path = root / "custom/tenant-a/collision"
    shutil.rmtree(path)
    path.symlink_to(root / "custom/tenant-a/user-a/collision", target_is_directory=True)
    response = http.put("/api/tenants/skills/collision", headers=ADMIN, json={"enabled": False, "expected_resource_id": shared["resource_id"]})
    assert response.status_code == 409 and all(row.enabled for row in native_rows(factory))
