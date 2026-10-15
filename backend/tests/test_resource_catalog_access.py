"""Actual current-member boundaries for resource observations and fixed-source installs."""
import asyncio

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from prismos_octop.catalog import list_templates
from test_octop_resource_installations import add, package, write_package
from test_octop_resource_installations import client as source_database_fixture

from app.gateway.routers import agent_catalog
from app.integrations.octop.resources import resource_preflight
from app.integrations.octop.skill_packages import prepare_skill_package
from deerflow.database.models import Tenant, TenantMembership

original_client = source_database_fixture


@pytest.fixture
def source_client(original_client, monkeypatch):
    _, factory, root = original_client
    from app.integrations import skill_imports
    from deerflow.skills import loader

    monkeypatch.setattr(skill_imports, "get_skills_root_path", lambda: root)
    monkeypatch.setattr(loader, "get_skills_root_path", lambda: root)
    app = FastAPI()

    @app.middleware("http")
    async def identity(request: Request, call_next):
        request.state.tenant_id = "tenant-a"
        request.state.user_id = "user-a"
        request.state.tenant_role = request.headers.get("x-tenant-role", "tenant_member")
        request.state.user_role = "user"
        return await call_next(request)

    app.include_router(agent_catalog.router)
    from app.gateway.routers import skills

    app.include_router(skills.router)
    with TestClient(app) as http:
        yield http, factory, root


def membership(factory, *, status="active", role="member"):
    async def seed():
        async with factory() as db:
            db.add(Tenant(id="tenant-a", name="Tenant A", slug="tenant-a"))
            await db.flush()
            db.add(TenantMembership(tenant_id="tenant-a", user_id="user-a", status=status, role=role))
            await db.commit()
    asyncio.run(seed())


def test_withdrawn_member_cannot_observe_owned_installation(source_client):
    http, factory, root = source_client
    membership(factory, status="inactive")
    _, _, pkg = package()
    folder = root / "custom/tenant-a/user-a" / pkg["name"]
    write_package(folder, pkg)
    add(factory, pkg["name"], folder)
    response = http.get("/api/agent-catalog/templates/expert:ai-coding-coach/resources?check_installation=true")
    assert response.status_code == 403
    assert "source_match" not in response.text


def test_withdrawn_member_cannot_publish_a_source_package(source_client):
    http, factory, root = source_client
    membership(factory, status="inactive")
    declaration, resource, pkg = package()
    response = http.post(f"/api/agent-catalog/templates/{declaration['template_id']}/resources/{resource['id']}/install", json={"scope":"personal","bundle_sha256":resource["bundle_sha256"]})
    assert response.status_code == 403
    assert not (root / "custom/tenant-a/user-a" / pkg["name"]).exists()


def test_cached_admin_role_cannot_publish_a_tenant_resource(source_client):
    http, factory, root = source_client
    membership(factory, role="member")
    declaration, resource, pkg = package()
    response = http.post(f"/api/agent-catalog/templates/{declaration['template_id']}/resources/{resource['id']}/install", headers={"x-tenant-role":"tenant_admin"}, json={"scope":"tenant","bundle_sha256":resource["bundle_sha256"]})
    assert response.status_code == 403
    assert not (root / "custom/tenant-a" / pkg["name"]).exists()


@pytest.mark.parametrize("role", ["admin", "owner", "tenant_admin"])
def test_current_original_admin_roles_override_stale_member_headers(source_client, role):
    http, factory, _ = source_client
    membership(factory, role=role)
    declaration, resource, _ = package()
    response = http.post(f"/api/agent-catalog/templates/{declaration['template_id']}/resources/{resource['id']}/install", json={"scope":"tenant","bundle_sha256":resource["bundle_sha256"]})
    assert response.status_code == 201, response.text


@pytest.mark.parametrize("phase", ["publish", "register", "confirm"])
def test_withdrawal_at_actual_import_boundary_preserves_truth_and_requires_inspection(source_client, monkeypatch, phase):
    import json

    from sqlalchemy import select

    from deerflow.database.models import TenantSkill

    http, factory, root = source_client
    membership(factory)
    declaration, resource, pkg = package()
    real_guard = agent_catalog.resource_operation_guard

    def guard(request, shared):
        original = real_guard(request, shared)

        async def check(current_phase):
            if current_phase == phase:
                async with factory() as db:
                    member = (await db.exec(select(TenantMembership))).scalars().one()
                    member.status = "inactive"
                    db.add(member)
                    await db.commit()
            await original(current_phase)
        return check

    monkeypatch.setattr(agent_catalog, "resource_operation_guard", guard)
    response = http.post(f"/api/agent-catalog/templates/{declaration['template_id']}/resources/{resource['id']}/install", json={"scope":"personal","bundle_sha256":resource["bundle_sha256"]})
    assert response.status_code in {403, 503}
    folder = root / "custom/tenant-a/user-a" / pkg["name"]
    assert folder.exists() is (phase != "publish")

    async def rows_and_regrant():
        async with factory() as db:
            rows = (await db.exec(select(TenantSkill))).scalars().all()
            member = (await db.exec(select(TenantMembership))).scalars().one()
            member.status = "active"
            db.add(member)
            await db.commit()
            return rows

    rows = asyncio.run(rows_and_regrant())
    assert len(rows) == (1 if phase == "confirm" else 0)
    receipts = [json.loads(p.read_text()) for p in folder.parent.glob(".prismos-import-*.json")]
    assert len(receipts) == 1
    if phase == "publish":
        assert receipts[0]["state"] == "aborted"
    else:
        assert receipts[0]["state"] == "registration_unknown"
        recovered = http.post(f"/api/skills/personal/imports/{receipts[0]['operation_id']}/recover")
        assert recovered.status_code == 200, recovered.text
        assert recovered.json()["state"] == "registered"


def test_revocation_before_resource_result_delivery_drops_observed_private_state(source_client, monkeypatch):
    from sqlalchemy import select

    from app.gateway import resource_authorization

    http, factory, root = source_client
    membership(factory)
    _, _, pkg = package()
    folder = root / "custom/tenant-a/user-a" / pkg["name"]
    write_package(folder, pkg)
    add(factory, pkg["name"], folder)
    original = resource_authorization.current_resource_actor
    calls = 0

    async def current(tenant, actor):
        nonlocal calls
        calls += 1
        if calls == 2:
            async with factory() as db:
                row = (await db.exec(select(TenantMembership))).scalars().one()
                row.status = "inactive"
                db.add(row)
                await db.commit()
        return await original(tenant, actor)

    monkeypatch.setattr(resource_authorization, "current_resource_actor", current)
    response = http.get("/api/agent-catalog/templates/expert:ai-coding-coach/resources?check_installation=true")
    assert response.status_code == 403 and "source_match" not in response.text



AUXILIARY_HTTP = [(t["id"], r["id"]) for t in list_templates("zh", "expert") for r in resource_preflight(t["id"])["resources"] if r["kind"] != "skill_bundle"]


@pytest.mark.parametrize("template_id,resource_id", AUXILIARY_HTTP)
def test_each_auxiliary_resource_installs_observes_and_withdraws_through_original_api(source_client, template_id, resource_id):
    import hashlib

    http, factory, root = source_client
    membership(factory)
    declaration = resource_preflight(template_id)
    resource = next(r for r in declaration["resources"] if r["id"] == resource_id)
    pkg = prepare_skill_package(declaration, resource)
    url = f"/api/agent-catalog/templates/{template_id}/resources/{resource_id}/install"
    response = http.post(url, json={"scope":"personal","bundle_sha256":resource["bundle_sha256"]})
    assert response.status_code == 201, response.text
    assert response.json()["execution_ready"] is False and response.json()["permission_grants"] is False
    folder = root / "custom/tenant-a/user-a" / pkg["name"]
    for member in resource["members"]:
        assert hashlib.sha256((folder / member["path"]).read_bytes()).hexdigest() == member["sha256"]
    observed = http.get(f"/api/agent-catalog/templates/{template_id}/resources?check_installation=true")
    assert observed.status_code == 200
    match = next(r for r in observed.json()["resources"] if r["id"] == resource_id)
    assert match["installation"]["status"] == "source_match"
    assert match["host_adaptation"]["name"] == pkg["name"]
    available = http.get("/api/skills/available")
    assert available.status_code == 200
    native = next(r for r in available.json()["skills"] if r["name"] == pkg["name"])
    disabled = http.patch(f"/api/skills/personal/{pkg['name']}", json={"expected_resource_id":native["resource_id"],"enabled":False})
    assert disabled.status_code == 200, disabled.text
    observed = http.get(f"/api/agent-catalog/templates/{template_id}/resources?check_installation=true")
    match = next(r for r in observed.json()["resources"] if r["id"] == resource_id)
    assert match["installation"]["status"] == "disabled"
    assert http.post(url, json={"scope":"personal","bundle_sha256":resource["bundle_sha256"]}).status_code == 409


def test_import_response_never_substitutes_same_name_global_metadata(source_client, monkeypatch):
    from types import SimpleNamespace

    from prismos_octop.upstream.frontmatter import parse_frontmatter

    from app.gateway.routers import skills
    from app.integrations.octop.skill_packages import skill_archive

    http, factory, _ = source_client
    membership(factory)
    _, _, pkg = package()
    monkeypatch.setattr(skills, "load_skills", lambda **kwargs: [SimpleNamespace(name=pkg["name"], description="UNRELATED SOURCE", license="unrelated-license")])
    response = http.post("/api/skills/personal/import", files={"archive": ("resource.zip", skill_archive(pkg), "application/zip")})
    assert response.status_code == 201, response.text
    metadata, _ = parse_frontmatter(pkg["files"]["SKILL.md"].decode())
    assert response.json()["description"] == metadata["description"]
    assert response.json()["license"] == metadata.get("license")
    assert "UNRELATED SOURCE" not in response.text


@pytest.mark.parametrize("alias", ["symlink", "hardlink"])
def test_original_resource_detail_refuses_file_aliases_without_host_bytes_or_paths(source_client, alias):
    import os

    from app.integrations.octop.skill_packages import skill_archive

    http, factory, root = source_client
    membership(factory)
    _, _, pkg = package()
    installed = http.post("/api/skills/personal/import", files={"archive": ("resource.zip", skill_archive(pkg), "application/zip")})
    assert installed.status_code == 201
    outside = root.parent / "outside-private.md"
    outside.write_text("---\nname: private\ndescription: OUTSIDE FILE CONTENT\n---\nOUTSIDE FILE CONTENT")
    owned = root / "custom/tenant-a/user-a" / pkg["name"] / "SKILL.md"
    owned.unlink()
    if alias == "symlink":
        owned.symlink_to(outside)
    else:
        os.link(outside, owned)
    response = http.get(f"/api/skills/{pkg['name']}/detail?scope=personal")
    assert response.status_code >= 400, response.text
    assert "OUTSIDE FILE CONTENT" not in response.text and str(root) not in response.text


def test_legacy_public_list_refuses_alias_metadata_before_response(source_client):
    http, factory, root = source_client
    membership(factory)
    outside = root.parent / "outside-public.md"
    outside.write_text("---\nname: public-canary\ndescription: OUTSIDE PUBLIC CONTENT\n---\nPRIVATE")
    folder = root / "public/public-canary"
    folder.mkdir(parents=True)
    (folder / "SKILL.md").symlink_to(outside)
    response = http.get("/api/skills")
    assert response.status_code == 200
    assert "OUTSIDE PUBLIC CONTENT" not in response.text and "public-canary" not in response.text
