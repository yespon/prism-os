import asyncio

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from resource_test_identity import persist_fixture_identity
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from app.gateway.routers import skills
from deerflow.database import user_config_service


@pytest.fixture(autouse=True)
def current_identity_database(tmp_path, monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///" + str(tmp_path / "identity.db"))
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def initialize():
        async with engine.begin() as connection:
            await connection.run_sync(SQLModel.metadata.create_all)

    asyncio.run(initialize())
    monkeypatch.setattr(user_config_service, "get_session_factory", lambda: factory)
    yield
    asyncio.run(engine.dispose())


def _create_app() -> FastAPI:
    app = FastAPI()

    @app.middleware("http")
    async def inject_context(request: Request, call_next):
        request.state.user_id = request.headers.get("x-user-id", "u-1")
        request.state.user_role = request.headers.get("x-user-role", "user")
        tenant_role = request.headers.get("x-tenant-role", "tenant_member")
        if tenant_role in {"admin", "owner"}:
            tenant_role = "tenant_admin"
        elif tenant_role == "member":
            tenant_role = "tenant_member"
        request.state.tenant_role = tenant_role
        tenant_id = request.headers.get("x-tenant-id")
        if tenant_id is not None:
            request.state.tenant_id = tenant_id
        await persist_fixture_identity(request, user_config_service.get_session_factory())
        return await call_next(request)

    app.include_router(skills.router)
    return app


def test_available_skills_requires_tenant_context() -> None:
    app = _create_app()

    with TestClient(app) as client:
        response = client.get("/api/skills/available")

    assert response.status_code == 400
    assert response.json()["detail"] == "Tenant context is required"


def test_available_skills_returns_merged_scopes(monkeypatch) -> None:
    app = _create_app()

    async def _fake_get_available_skills(
        user_id: str,
        tenant_id: str,
        *,
        is_tenant_admin: bool,
        is_platform_admin: bool,
    ):
        assert user_id == "u-1"
        assert tenant_id == "tenant-a"
        assert is_tenant_admin is True
        assert is_platform_admin is False
        return [
            {
                "name": "global-skill",
                "description": "g",
                "license": None,
                "category": "public",
                "enabled": True,
                "scope": "global",
                "source": "platform_builtin",
                "managed_by_current_user": False,
                "effective_permissions": ["read", "use"],
            },
            {
                "name": "tenant-skill",
                "description": "t",
                "license": None,
                "category": "custom",
                "enabled": True,
                "scope": "tenant",
                "source": "tenant_shared",
                "managed_by_current_user": True,
                "effective_permissions": ["read", "use", "manage"],
            },
        ]

    monkeypatch.setattr(skills, "get_available_skills", _fake_get_available_skills)

    with TestClient(app) as client:
        response = client.get(
            "/api/skills/available",
            headers={"x-tenant-id": "tenant-a", "x-tenant-role": "tenant_admin"},
        )

    assert response.status_code == 200
    payload = response.json()
    assert [item["scope"] for item in payload["skills"]] == ["global", "tenant"]


def test_tenant_shared_skills_reject_non_tenant_admin() -> None:
    app = _create_app()

    with TestClient(app) as client:
        response = client.get(
            "/api/tenants/skills",
            headers={"x-tenant-id": "tenant-a", "x-tenant-role": "tenant_member"},
        )

    assert response.status_code == 403


def test_tenant_shared_skills_reject_platform_admin_without_membership() -> None:
    app = _create_app()

    with TestClient(app) as client:
        response = client.get(
            "/api/tenants/skills",
            headers={"x-tenant-id": "tenant-a", "x-tenant-role": "tenant_member", "x-user-role": "admin"},
        )

    assert response.status_code == 403


def test_tenant_shared_skill_update_succeeds_for_tenant_admin(monkeypatch) -> None:
    app = _create_app()

    async def toggle(root, tenant_id, actor, name, enabled, expected_resource_id):
        assert tenant_id == "tenant-a" and actor == "u-1"
        assert name == "tenant-skill" and enabled is False
        assert expected_resource_id is None
        return "tenant", "skill:fixture"

    async def detail(name, request, *, scope, resource_id):
        assert scope == "tenant" and resource_id == "skill:fixture"
        return skills.SkillDetailResponse(name=name, description="tenant skill", category="custom", enabled=False, scope=scope, resource_id=resource_id, managed_by_current_user=True)

    monkeypatch.setattr(skills.skill_mutations, "set_shared_enablement", toggle)
    monkeypatch.setattr(skills, "get_skill_detail", detail)

    with TestClient(app) as client:
        response = client.put(
            "/api/tenants/skills/tenant-skill",
            headers={"x-tenant-id": "tenant-a", "x-tenant-role": "tenant_admin"},
            json={"enabled": False},
        )

    assert response.status_code == 200
    assert response.json()["name"] == "tenant-skill"
    assert response.json()["enabled"] is False


def test_available_skills_passes_platform_admin_flag(monkeypatch) -> None:
    app = _create_app()

    async def _fake_get_available_skills(
        user_id: str,
        tenant_id: str,
        *,
        is_tenant_admin: bool,
        is_platform_admin: bool,
    ):
        assert user_id == "u-1"
        assert tenant_id == "tenant-a"
        assert is_tenant_admin is False
        assert is_platform_admin is True
        return []

    monkeypatch.setattr(skills, "get_available_skills", _fake_get_available_skills)

    with TestClient(app) as client:
        response = client.get(
            "/api/skills/available",
            headers={"x-tenant-id": "tenant-a", "x-tenant-role": "tenant_member", "x-user-role": "admin"},
        )

    assert response.status_code == 200
    assert response.json() == {"skills": []}


def test_tenant_shared_skill_delete_rejects_non_tenant_admin() -> None:
    app = _create_app()

    with TestClient(app) as client:
        response = client.delete(
            "/api/tenants/skills/tenant-skill",
            headers={"x-tenant-id": "tenant-a", "x-tenant-role": "tenant_member"},
        )

    assert response.status_code == 403


def test_tenant_shared_skill_delete_returns_404_when_missing(monkeypatch) -> None:
    app = _create_app()

    async def missing(root, tenant_id, actor, shared, name, **kwargs):
        assert tenant_id == "tenant-a" and actor == "u-1" and shared
        assert name == "missing-skill"
        raise skills.skill_mutations.SkillMutationRejected(404, "Current registered resource not found")

    monkeypatch.setattr(skills.skill_deletions, "delete_owned", missing)

    with TestClient(app) as client:
        response = client.delete(
            "/api/tenants/skills/missing-skill",
            headers={"x-tenant-id": "tenant-a", "x-tenant-role": "tenant_admin"},
        )

    assert response.status_code == 404


def test_user_skill_update_route_is_removed() -> None:
    app = _create_app()

    with TestClient(app) as client:
        response = client.put(
            "/api/skills/tenant-skill",
            headers={"x-tenant-id": "tenant-a", "x-tenant-role": "tenant_member", "x-user-role": "admin"},
            json={"enabled": True},
        )

    assert response.status_code == 405


def test_install_skill_registers_tenant_scoped_path(monkeypatch, tmp_path) -> None:
    import zipfile
    from types import SimpleNamespace

    from app.integrations import skill_imports
    from deerflow.database import user_config_service

    app = _create_app()
    calls: dict[str, object] = {}
    archive = tmp_path / "source.skill"
    root = tmp_path / "skills"
    with zipfile.ZipFile(archive, "w") as file:
        file.writestr("tenant-skill/SKILL.md", "---\nname: tenant-skill\ndescription: Scope fixture\n---\n# Skill")
    monkeypatch.setattr(skills, "get_skills_root_path", lambda: root)
    monkeypatch.setattr(skills, "resolve_thread_virtual_path", lambda *args, **kwargs: archive)

    async def no_row(*args, **kwargs):
        return None

    async def create(tenant_id, **kwargs):
        calls["tenant_id"] = tenant_id
        calls["payload"] = kwargs
        return SimpleNamespace(id=1)

    monkeypatch.setattr(skill_imports, "current_row", no_row)
    monkeypatch.setattr(user_config_service, "create_tenant_shared_skill", create)
    with TestClient(app) as client:
        response = client.post(
            "/api/skills/install",
            headers={"x-tenant-id": "tenant-a", "x-tenant-role": "tenant_admin"},
            json={"thread_id": "t-1", "path": "artifacts/demo.skill"},
        )
    assert response.status_code == 200
    assert response.json()["operation_id"]
    assert (root / "custom/tenant-a/tenant-skill/SKILL.md").is_file()
    assert calls["tenant_id"] == "tenant-a"
    assert calls["payload"] == {
        "enabled": True,
        "skill_name": "tenant-skill",
        "category": "custom",
        "relative_path": "tenant-a/tenant-skill",
        "install_dir": str(root / "custom/tenant-a/tenant-skill"),
    }
