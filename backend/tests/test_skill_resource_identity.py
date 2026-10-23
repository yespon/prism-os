"""Native DB/file resource identity faults before copy/share lifecycle writes."""
import asyncio
import shutil

from sqlalchemy import select
from test_skill_import_recovery import scoped_client as recovery_client

from deerflow.config.tenant_context import tenant_context
from deerflow.database import user_config_service as service
from deerflow.database.models import TenantSkill
from deerflow.skills import loader

scoped_client = recovery_client


def source_tree(scoped_client, monkeypatch):
    http, factory, root = scoped_client
    monkeypatch.setattr(loader, "get_skills_root_path", lambda: root)
    monkeypatch.setattr(service, "get_skills_root_path", lambda: root)
    monkeypatch.setattr(service, "_build_default_payloads", lambda: ({"models": []}, {"skills": {}, "mcpServers": {}}))
    public = root / "public/collision"
    public.mkdir(parents=True)
    (public / "SKILL.md").write_text("---\nname: collision\ndescription: public description\n---\nPUBLIC ONLY\n")

    async def rows():
        for user, scope, description in [("user-a", "personal", "PERSONAL ONLY"), ("__tenant_shared_skill__:tenant-a", "tenant", "SHARED ONLY")]:
            path = root / "custom/tenant-a" / ("user-a" if scope == "personal" else "") / "collision"
            path.mkdir(parents=True)
            (path / "SKILL.md").write_text(f"---\nname: collision\ndescription: {description}\n---\n{description}\n")
            async with factory() as session:
                session.add(TenantSkill(tenant_id="tenant-a", user_id=user, name="collision", category="custom", enabled=True, install_dir=str(path), relative_path=str(path.relative_to(root / "custom"))))
                await session.commit()
    asyncio.run(rows())
    return http, factory, root


def test_available_resources_do_not_collapse_custom_shared_into_public(scoped_client, monkeypatch):
    http, _, _ = source_tree(scoped_client, monkeypatch)
    response = http.get("/api/skills/available")
    assert response.status_code == 200
    items = response.json()["skills"]
    assert {item["scope"] for item in items} == {"global", "tenant", "personal"}
    assert len({item["resource_id"] for item in items}) == 3
    assert {item["scope"]: item["description"] for item in items} == {"global": "public description", "tenant": "SHARED ONLY", "personal": "PERSONAL ONLY"}


def test_explicit_personal_detail_does_not_return_a_public_name_match(scoped_client, monkeypatch):
    http, _, _ = source_tree(scoped_client, monkeypatch)
    response = http.get("/api/skills/collision/detail", params={"scope": "personal"})
    assert response.status_code == 200 and response.json()["scope"] == "personal"
    assert response.json()["instructions"] == "PERSONAL ONLY"


def test_public_detail_reads_actual_public_directory(scoped_client, monkeypatch):
    http, _, _ = source_tree(scoped_client, monkeypatch)
    response = http.get("/api/skills/collision/detail", params={"scope": "global"})
    assert response.status_code == 200 and response.json()["instructions"] == "PUBLIC ONLY"


def test_registered_path_cannot_read_another_users_file(scoped_client, monkeypatch):
    http, factory, root = source_tree(scoped_client, monkeypatch)
    shutil.rmtree(root / "public/collision")
    secret_dir = root / "custom/tenant-a/user-b/collision"
    secret_dir.mkdir(parents=True)
    (secret_dir / "SKILL.md").write_text("---\nname: collision\ndescription: private b\n---\nOTHER USER PRIVATE\n")

    async def replace():
        async with factory() as session:
            shared = (await session.exec(select(TenantSkill).where(TenantSkill.user_id != "user-a"))).scalars().one()
            await session.delete(shared)
            row = (await session.exec(select(TenantSkill).where(TenantSkill.user_id == "user-a"))).scalars().one()
            row.install_dir = str(secret_dir)
            session.add(row)
            await session.commit()
    asyncio.run(replace())
    response = http.get("/api/skills/collision/detail", params={"scope": "personal"})
    assert response.status_code == 409 and "OTHER USER PRIVATE" not in response.text


def test_concrete_id_cannot_fall_back_after_row_removal_or_across_scope(scoped_client, monkeypatch):
    http, factory, _ = source_tree(scoped_client, monkeypatch)
    personal = next(item for item in http.get("/api/skills/available").json()["skills"] if item["scope"] == "personal")
    selector = {"scope": "personal", "resource_id": personal["resource_id"]}
    assert http.get("/api/skills/collision/detail", params=selector).json()["instructions"] == "PERSONAL ONLY"
    assert http.get("/api/skills/collision/detail", params={**selector, "scope": "global"}).status_code == 404
    assert http.get("/api/skills/collision/detail", params=selector, headers={"x-user-id": "user-b"}).status_code == 404
    assert http.get("/api/skills/collision/detail", params=selector, headers={"x-tenant-id": "tenant-b"}).status_code == 404

    async def remove():
        async with factory() as session:
            row = (await session.exec(select(TenantSkill).where(TenantSkill.user_id == "user-a"))).scalars().one()
            await session.delete(row)
            await session.commit()
    asyncio.run(remove())
    assert http.get("/api/skills/collision/detail", params=selector).status_code == 404
    assert http.get("/api/skills/collision/detail").json()["scope"] == "global"


def test_disabled_custom_shared_does_not_disable_public_and_has_no_use_grant(scoped_client, monkeypatch):
    http, factory, _ = source_tree(scoped_client, monkeypatch)

    async def disable():
        async with factory() as session:
            row = (await session.exec(select(TenantSkill).where(TenantSkill.user_id != "user-a"))).scalars().one()
            row.enabled = False
            session.add(row)
            await session.commit()
    asyncio.run(disable())
    rows = http.get("/api/skills/available").json()["skills"]
    assert next(item for item in rows if item["scope"] == "global")["enabled"]
    shared = next(item for item in rows if item["scope"] == "tenant")
    assert not shared["enabled"] and "use" not in shared["effective_permissions"]
    assert not shared["managed_by_current_user"]
    admin_rows = http.get("/api/skills/available", headers={"x-tenant-role": "tenant_admin"}).json()["skills"]
    assert "manage" in next(item for item in admin_rows if item["scope"] == "tenant")["effective_permissions"]
    platform_rows = http.get("/api/skills/available", headers={"x-user-role": "platform_admin"}).json()["skills"]
    assert not next(item for item in platform_rows if item["scope"] == "tenant")["managed_by_current_user"]


def test_public_tenant_toggle_remains_a_public_override(scoped_client, monkeypatch):
    http, factory, root = source_tree(scoped_client, monkeypatch)

    async def override():
        async with factory() as session:
            row = (await session.exec(select(TenantSkill).where(TenantSkill.user_id != "user-a"))).scalars().one()
            row.category = "public"
            row.install_dir = str(root / "public/collision")
            row.relative_path = "collision"
            row.enabled = False
            session.add(row)
            await session.commit()
    asyncio.run(override())
    rows = http.get("/api/skills/available").json()["skills"]
    assert {item["scope"] for item in rows} == {"global", "personal"}
    public = next(item for item in rows if item["scope"] == "global")
    assert not public["enabled"] and "use" not in public["effective_permissions"]
    assert http.get("/api/skills/collision/detail", params={"scope": "global"}) .json()["instructions"] == "PUBLIC ONLY"


def test_legacy_name_loader_keeps_public_default_without_custom_toggle(scoped_client, monkeypatch):
    _, _, root = source_tree(scoped_client, monkeypatch)
    monkeypatch.setattr(loader, "load_user_skill_records", lambda *a, **k: [{"name": "collision", "category": "custom", "enabled": False, "install_dir": str(root / "custom/tenant-a/collision")}])
    with tenant_context("user-a", tenant_id="tenant-a"):
        loaded = loader.load_skills(root, use_config=False, enabled_only=False)
    assert len(loaded) == 1 and loaded[0].category == "public" and loaded[0].enabled


def test_missing_personal_file_does_not_read_same_name_shared_file(scoped_client, monkeypatch):
    http, _, root = source_tree(scoped_client, monkeypatch)
    (root / "custom/tenant-a/user-a/collision/SKILL.md").unlink()
    rows = http.get("/api/skills/available").json()["skills"]
    personal = next(item for item in rows if item["scope"] == "personal")
    assert personal["files_status"] == "missing" and personal["description"] == "" and "use" not in personal["effective_permissions"]
    assert http.get("/api/skills/collision/detail", params={"scope": "personal"}).json()["instructions"] == ""


def test_deleted_sqlite_id_reused_by_new_registration_does_not_rebind_old_selection(scoped_client, monkeypatch):
    http, factory, root = source_tree(scoped_client, monkeypatch)
    before = next(item for item in http.get("/api/skills/available").json()["skills"] if item["scope"] == "personal")

    async def recreate():
        async with factory() as session:
            rows = (await session.exec(select(TenantSkill))).scalars().all()
            original_id = next(row.id for row in rows if row.user_id == "user-a")
            for row in rows:
                await session.delete(row)
            await session.commit()
            # Deliberately reuse the old primary key as a restored/recreated row.
            row = TenantSkill(id=original_id, tenant_id="tenant-a", user_id="user-a", name="collision", category="custom", enabled=True, install_dir=str(root / "custom/tenant-a/user-a/collision"), relative_path="tenant-a/user-a/collision")
            session.add(row)
            await session.commit()
    asyncio.run(recreate())
    after = next(item for item in http.get("/api/skills/available").json()["skills"] if item["scope"] == "personal")
    assert before["resource_id"] != after["resource_id"]
    assert http.get("/api/skills/collision/detail", params={"scope": "personal", "resource_id": before["resource_id"]}).status_code == 404
    assert http.get("/api/skills/collision/detail", params={"scope": "personal", "resource_id": after["resource_id"]}).status_code == 200
