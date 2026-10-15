"""Real scoped Skill rows and files; preflight never ensures a config or grant."""

from __future__ import annotations

import asyncio
import io
import os
import zipfile

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from app.gateway.routers import agent_catalog, skills
from app.integrations.octop import resource_installations as observations
from app.integrations.octop.resources import resource_preflight
from app.integrations.octop.skill_packages import prepare_skill_package, skill_archive
from deerflow.database import user_config_service
from deerflow.database.models import TenantSkill, UserConfig
from deerflow.skills import installer


@pytest.fixture
def client(tmp_path, monkeypatch):
    root = tmp_path / "skills"
    root.mkdir()
    url = os.environ.get("PRISMOS_SKILL_TEST_DB_URL", "sqlite+aiosqlite://")
    parsed = make_url(url)
    if parsed.get_backend_name() == "postgresql":
        assert parsed.host == "127.0.0.1" and parsed.database == "prismos_skill_probe", "Only the isolated probe database is supported"
    engine = create_async_engine(url, **({"poolclass": NullPool} if parsed.get_backend_name() == "postgresql" else {}))
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def setup():
        async with engine.begin() as conn:
            await conn.run_sync(SQLModel.metadata.drop_all)
            await conn.run_sync(SQLModel.metadata.create_all)

    asyncio.run(setup())
    monkeypatch.setattr(observations, "get_session_factory", lambda: factory)
    monkeypatch.setattr(user_config_service, "get_session_factory", lambda: factory)
    for module in (observations, skills, installer):
        monkeypatch.setattr(module, "get_skills_root_path", lambda: root)
    app = FastAPI()

    @app.middleware("http")
    async def identity(request: Request, call_next):
        request.state.user_id = request.headers.get("x-user-id", "user-a") or None
        request.state.tenant_id = request.headers.get("x-tenant-id", "tenant-a") or None
        request.state.tenant_role = "tenant_member"
        request.state.user_role = "user"
        from resource_test_identity import persist_fixture_identity

        await persist_fixture_identity(request, factory)
        return await call_next(request)

    app.include_router(agent_catalog.router)
    app.include_router(skills.router)
    with TestClient(app) as value:
        yield value, factory, root
    asyncio.run(engine.dispose())


def package():
    d = resource_preflight("expert:ai-coding-coach")
    r = next(r for r in d["resources"] if r["kind"] == "skill_bundle")
    return d, r, prepare_skill_package(d, r)


def write_package(folder, pkg):
    for path, data in pkg["files"].items():
        dest = folder / path
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)


def add(factory, name, path, *, tenant="tenant-a", user="user-a", enabled=True):
    async def insert():
        async with factory() as session:
            session.add(TenantSkill(tenant_id=tenant, user_id=user, name=name, category="personal", install_dir=str(path), enabled=enabled))
            await session.commit()

    asyncio.run(insert())


def check(client, headers=None):
    response = client.get("/api/agent-catalog/templates/expert:ai-coding-coach/resources?check_installation=true", headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert body["installation_checked"] and not body["permission_grants"] and not body["execution_ready"]
    return next(r for r in body["resources"] if r["kind"] == "skill_bundle")["installation"]


def test_current_source_match_does_not_create_user_config_or_cross_owner(client):
    http, factory, root = client
    _, _, pkg = package()
    folder = root / "custom/tenant-a/user-a" / pkg["name"]
    write_package(folder, pkg)
    add(factory, pkg["name"], folder)
    state = check(http)
    assert state["status"] == "source_match" and state["candidates"][0]["scope"] == "personal"
    assert check(http, {"x-user-id": "user-b"})["status"] == "not_installed"
    assert check(http, {"x-tenant-id": "tenant-b"})["status"] == "not_installed"

    async def configs():
        async with factory() as session:
            result = await session.exec(select(UserConfig))
            return len(result.scalars().all())

    assert asyncio.run(configs()) == 0


@pytest.mark.parametrize("case,expected", [("modified", "modified"), ("missing", "files_missing"), ("disabled", "disabled"), ("foreign_path", "location_unverified"), ("symlink", "location_unverified")])
def test_record_name_never_blesses_wrong_missing_disabled_or_foreign_files(client, case, expected):
    http, factory, root = client
    _, _, pkg = package()
    folder = root / "custom/tenant-a/user-a" / pkg["name"]
    if case != "missing":
        write_package(folder, pkg)
    recorded = folder
    if case == "modified":
        (folder / "SKILL.md").write_text("changed")
    elif case == "foreign_path":
        recorded = root / "custom/tenant-b/user-z" / pkg["name"]
    elif case == "symlink":
        file = folder / "SKILL.md"
        data = file.read_bytes()
        file.unlink()
        external = root.parent / "external-source"
        external.write_bytes(data)
        file.symlink_to(external)
    add(factory, pkg["name"], recorded, enabled=case != "disabled")
    state = check(http)
    assert state["status"] == expected
    assert "install_dir" not in str(state) and str(root) not in str(state)


def test_multiple_visible_personal_and_tenant_scopes_are_explicit(client):
    http, factory, root = client
    _, _, pkg = package()
    personal = root / "custom/tenant-a/user-a" / pkg["name"]
    shared = root / "custom/tenant-a" / pkg["name"]
    write_package(personal, pkg)
    write_package(shared, pkg)
    add(factory, pkg["name"], personal)
    add(factory, pkg["name"], shared, user="__tenant_shared_skill__:tenant-a")
    state = check(http)
    assert state["status"] == "multiple_visible_records"
    assert {c["scope"] for c in state["candidates"]} == {"personal", "tenant"}
    assert check(http, {"x-user-id": "user-b"})["status"] == "source_match"


def test_real_personal_import_accepts_native_signature_and_preserves_scoped_path(client):
    http, factory, root = client
    _, _, pkg = package()
    archive = skill_archive(pkg)
    response = http.post("/api/skills/personal/import", files={"archive": ("source.zip", archive, "application/zip")})
    assert response.status_code == 201, response.text
    assert (root / "custom/tenant-a/user-a" / pkg["name"] / "SKILL.md").is_file()
    assert check(http)["status"] == "source_match"
    assert http.post("/api/skills/personal/import", files={"archive": ("source.zip", archive)}).status_code == 409
    assert http.post("/api/skills/personal/import", headers={"x-tenant-id": "tenant-b"}, files={"archive": ("source.zip", archive)}).status_code == 201
    assert (root / "custom/tenant-b/user-a" / pkg["name"] / "SKILL.md").is_file()


def test_archive_endpoint_is_only_pinned_global_source_and_requires_identity(client):
    http, _, _ = client
    d, r, pkg = package()
    url = f"/api/agent-catalog/templates/{d['template_id']}/resources/{r['id']}/archive"
    assert http.get(url, headers={"x-user-id": ""}).status_code == 401
    assert http.get(url, headers={"x-tenant-id": ""}).status_code == 400
    response = http.get(url)
    assert response.status_code == 200 and response.content == skill_archive(pkg)
    assert response.headers["content-type"] == "application/zip"
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        assert all(name.startswith(pkg["name"] + "/") for name in archive.namelist())
    assert http.get(url.replace(r["id"], "resource:unknown")).status_code == 404


def test_public_raw_source_match_respects_only_current_tenant_disable_override(client):
    http, factory, root = client
    _, _, pkg = package()
    assert not pkg["adapted"]
    folder = root / "public" / pkg["name"]
    write_package(folder, pkg)
    (folder / "PRISMOS_ORIGIN.json").unlink()
    (folder / "LICENSE.octop").unlink()
    assert check(http)["candidates"] == [{"scope": "global", "enabled": True, "content_status": "source_match"}]
    add(factory, pkg["name"], folder, user="__tenant_shared_skill__:tenant-a", enabled=False)
    assert check(http)["status"] == "disabled"
    assert check(http, {"x-user-id": "user-b"})["status"] == "disabled"
    assert check(http, {"x-tenant-id": "tenant-b"})["status"] == "source_match"
