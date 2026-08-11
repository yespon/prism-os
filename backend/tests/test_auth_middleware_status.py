import asyncio

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from app.gateway.auth import AuthMiddleware
from app.gateway.authorization import require_tenant_context


class _FakeResponse:
    def __init__(self, status_code: int, payload: dict | None = None):
        self.status_code = status_code
        self._payload = payload or {}

    def json(self):
        return self._payload


class _FakeAsyncClient:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def get(self, *args, **kwargs):
        return _FakeResponse(500)


def _create_app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(AuthMiddleware)

    @app.get("/secure")
    async def secure_endpoint():
        return JSONResponse({"ok": True})

    @app.get("/secure-context")
    async def secure_context_endpoint(request: Request):
        return JSONResponse({"tenant_id": getattr(request.state, "tenant_id", None)})

    @app.get("/secure-context-role")
    async def secure_context_role_endpoint(request: Request):
        return JSONResponse({"tenant_role": getattr(request.state, "tenant_role", None)})

    @app.get("/api/admin/ping")
    async def admin_ping(request: Request):
        return JSONResponse({"tenant_id": getattr(request.state, "tenant_id", None)})

    @app.get("/api/tenant-business/ping")
    async def tenant_business_ping(request: Request):
        tenant_id = require_tenant_context(request)
        return JSONResponse({"tenant_id": tenant_id})

    return app


def test_auth_middleware_blocks_suspended_user(monkeypatch):
    app = _create_app()

    import app.gateway.auth as auth_module

    monkeypatch.setattr(auth_module, "_resolve_user_from_auth_db", lambda token: ("u-1", "user", False))
    monkeypatch.setattr(auth_module, "_resolve_user_status_from_auth_db", lambda user_id: "suspended")

    with TestClient(app) as client:
        response = client.get("/secure", headers={"Authorization": "Bearer token"})

    assert response.status_code == 403
    assert response.json()["detail"] == "User account suspended"


def test_auth_middleware_allows_user_without_status(monkeypatch):
    app = _create_app()

    import app.gateway.auth as auth_module

    monkeypatch.setattr(auth_module, "_resolve_user_from_auth_db", lambda token: ("u-1", "user", False))
    monkeypatch.setattr(auth_module, "_resolve_user_status_from_auth_db", lambda user_id: None)

    with TestClient(app) as client:
        response = client.get("/secure", headers={"Authorization": "Bearer token"})

    assert response.status_code == 200
    assert response.json() == {"ok": True}


def test_auth_middleware_injects_tenant_id_from_header(monkeypatch):
    app = _create_app()

    import app.gateway.auth as auth_module

    class _Membership:
        role = "member"

    monkeypatch.setattr(auth_module, "_resolve_user_from_auth_db", lambda token: ("u-1", "user", False))
    monkeypatch.setattr(auth_module, "_resolve_user_status_from_auth_db", lambda user_id: None)

    async def _fake_get_membership(user_id: str, tenant_id: str):
        return _Membership()

    monkeypatch.setattr(auth_module, "get_membership", _fake_get_membership)

    with TestClient(app) as client:
        response = client.get(
            "/secure",
            headers={
                "Authorization": "Bearer token",
                "X-Tenant-Id": "tenant-a",
            },
        )

    assert response.status_code == 200


def test_auth_middleware_allows_missing_tenant_id_for_now(monkeypatch):
    app = _create_app()

    import app.gateway.auth as auth_module

    monkeypatch.setattr(auth_module, "_resolve_user_from_auth_db", lambda token: ("u-1", "user", False))
    monkeypatch.setattr(auth_module, "_resolve_user_status_from_auth_db", lambda user_id: None)

    with TestClient(app) as client:
        response = client.get(
            "/secure",
            headers={
                "Authorization": "Bearer token",
            },
        )

    assert response.status_code == 200


def test_auth_middleware_sets_resolved_tenant_id(monkeypatch):
    app = _create_app()

    import app.gateway.auth as auth_module

    monkeypatch.setattr(auth_module, "_resolve_user_from_auth_db", lambda token: ("u-1", "user", False))
    monkeypatch.setattr(auth_module, "_resolve_user_status_from_auth_db", lambda user_id: None)

    async def _fake_resolve_tenant_id(user_id: str, requested_tenant_id: str | None) -> str:
        assert user_id == "u-1"
        assert requested_tenant_id == "tenant-a"
        return "tenant-resolved"

    monkeypatch.setattr(auth_module, "_resolve_tenant_id", _fake_resolve_tenant_id)

    with TestClient(app) as client:
        response = client.get(
            "/secure-context",
            headers={
                "Authorization": "Bearer token",
                "X-Tenant-Id": "tenant-a",
            },
        )

    assert response.status_code == 200
    assert response.json() == {"tenant_id": "tenant-resolved"}


def test_auth_middleware_rejects_forbidden_tenant(monkeypatch):
    app = _create_app()

    import app.gateway.auth as auth_module

    monkeypatch.setattr(auth_module, "_resolve_user_from_auth_db", lambda token: ("u-1", "user", False))
    monkeypatch.setattr(auth_module, "_resolve_user_status_from_auth_db", lambda user_id: None)

    async def _fake_resolve_tenant_id(user_id: str, requested_tenant_id: str | None) -> str:
        raise PermissionError("denied")

    monkeypatch.setattr(auth_module, "_resolve_tenant_id", _fake_resolve_tenant_id)

    with TestClient(app) as client:
        response = client.get(
            "/secure-context",
            headers={
                "Authorization": "Bearer token",
                "X-Tenant-Id": "tenant-a",
            },
        )

    assert response.status_code == 403
    assert response.json()["detail"] == "denied"


def test_auth_middleware_allows_platform_admin_route_without_tenant(monkeypatch):
    app = _create_app()

    import app.gateway.auth as auth_module

    monkeypatch.setattr(auth_module, "_resolve_user_from_auth_db", lambda token: ("u-1", "admin", False))
    monkeypatch.setattr(auth_module, "_resolve_user_status_from_auth_db", lambda user_id: None)

    async def _fake_resolve_tenant_id(user_id: str, requested_tenant_id: str | None) -> str:
        raise PermissionError("NO_TENANT_ASSIGNED")

    monkeypatch.setattr(auth_module, "_resolve_tenant_id", _fake_resolve_tenant_id)

    with TestClient(app) as client:
        response = client.get(
            "/api/admin/ping",
            headers={
                "Authorization": "Bearer token",
            },
        )

    assert response.status_code == 200
    assert response.json() == {"tenant_id": None}


def test_auth_middleware_allows_platform_admin_role_without_tenant(monkeypatch):
    app = _create_app()

    import app.gateway.auth as auth_module

    monkeypatch.setattr(auth_module, "_resolve_user_from_auth_db", lambda token: ("u-1", "platform_admin", False))
    monkeypatch.setattr(auth_module, "_resolve_user_status_from_auth_db", lambda user_id: None)

    async def _fake_resolve_tenant_id(user_id: str, requested_tenant_id: str | None) -> str:
        raise PermissionError("NO_TENANT_ASSIGNED")

    monkeypatch.setattr(auth_module, "_resolve_tenant_id", _fake_resolve_tenant_id)

    with TestClient(app) as client:
        response = client.get(
            "/api/admin/ping",
            headers={
                "Authorization": "Bearer token",
            },
        )

    assert response.status_code == 200
    assert response.json() == {"tenant_id": None}


def test_auth_middleware_denies_platform_admin_tenant_business_without_membership(monkeypatch):
    app = _create_app()

    import app.gateway.auth as auth_module

    monkeypatch.setattr(auth_module, "_resolve_user_from_auth_db", lambda token: ("u-1", "admin", False))
    monkeypatch.setattr(auth_module, "_resolve_user_status_from_auth_db", lambda user_id: None)

    async def _fake_resolve_tenant_id(user_id: str, requested_tenant_id: str | None) -> str:
        raise PermissionError("NO_TENANT_ASSIGNED")

    monkeypatch.setattr(auth_module, "_resolve_tenant_id", _fake_resolve_tenant_id)

    with TestClient(app) as client:
        response = client.get(
            "/api/tenant-business/ping",
            headers={
                "Authorization": "Bearer token",
            },
        )

    assert response.status_code == 403


def test_auth_middleware_sets_tenant_role(monkeypatch):
    app = _create_app()

    import app.gateway.auth as auth_module

    class _Membership:
        role = "admin"

    monkeypatch.setattr(auth_module, "_resolve_user_from_auth_db", lambda token: ("u-1", "user", False))
    monkeypatch.setattr(auth_module, "_resolve_user_status_from_auth_db", lambda user_id: None)

    async def _fake_resolve_tenant_id(user_id: str, requested_tenant_id: str | None) -> str:
        return "tenant-a"

    async def _fake_get_membership(user_id: str, tenant_id: str):
        return _Membership()

    monkeypatch.setattr(auth_module, "_resolve_tenant_id", _fake_resolve_tenant_id)
    monkeypatch.setattr(auth_module, "get_membership", _fake_get_membership)

    with TestClient(app) as client:
        response = client.get(
            "/secure-context-role",
            headers={
                "Authorization": "Bearer token",
                "X-Tenant-Id": "tenant-a",
            },
        )

    assert response.status_code == 200
    assert response.json() == {"tenant_role": "tenant_admin"}


def test_resolve_tenant_id_prefers_persisted_tenant(monkeypatch):
    import app.gateway.auth as auth_module

    class _Membership:
        def __init__(self, tenant_id: str):
            self.tenant_id = tenant_id

    async def _fake_get_current_tenant_id(user_id: str) -> str | None:
        return "tenant-persisted"

    async def _fake_get_membership(user_id: str, tenant_id: str):
        if tenant_id == "tenant-persisted":
            return _Membership(tenant_id)
        return None

    async def _fake_ensure_default_tenant_for_user(user_id: str):
        raise AssertionError("should not fallback when persisted tenant is valid")

    monkeypatch.setattr(auth_module, "get_current_tenant_id", _fake_get_current_tenant_id)
    monkeypatch.setattr(auth_module, "get_membership", _fake_get_membership)
    monkeypatch.setattr(auth_module, "ensure_default_tenant_for_user", _fake_ensure_default_tenant_for_user)

    tenant_id = asyncio.run(auth_module._resolve_tenant_id("u-1", None))
    assert tenant_id == "tenant-persisted"


def test_resolve_tenant_id_falls_back_to_default_and_persists(monkeypatch):
    import app.gateway.auth as auth_module

    class _Membership:
        def __init__(self, tenant_id: str):
            self.tenant_id = tenant_id

    calls = {}

    async def _fake_get_current_tenant_id(user_id: str) -> str | None:
        return None

    async def _fake_get_membership(user_id: str, tenant_id: str):
        return None

    async def _fake_ensure_default_tenant_for_user(user_id: str):
        return _Membership("tenant-default")

    async def _fake_list_user_tenants(user_id: str):
        return []

    async def _fake_set_current_tenant_id(user_id: str, tenant_id: str):
        calls["user_id"] = user_id
        calls["tenant_id"] = tenant_id

    monkeypatch.setattr(auth_module, "get_current_tenant_id", _fake_get_current_tenant_id)
    monkeypatch.setattr(auth_module, "get_membership", _fake_get_membership)
    monkeypatch.setattr(auth_module, "ensure_default_tenant_for_user", _fake_ensure_default_tenant_for_user)
    monkeypatch.setattr(auth_module, "list_user_tenants", _fake_list_user_tenants)
    monkeypatch.setattr(auth_module, "set_current_tenant_id", _fake_set_current_tenant_id)

    tenant_id = asyncio.run(auth_module._resolve_tenant_id("u-1", None))
    assert tenant_id == "tenant-default"
    assert tenant_id == calls.get("tenant_id")


def test_resolve_tenant_id_rejects_requested_tenant_without_membership(monkeypatch):
    import app.gateway.auth as auth_module

    async def _fake_get_membership(user_id: str, tenant_id: str):
        return None

    monkeypatch.setattr(auth_module, "get_membership", _fake_get_membership)

    try:
        asyncio.run(auth_module._resolve_tenant_id("u-1", "tenant-other"))
    except PermissionError as exc:
        assert "not a member" in str(exc)
    else:
        raise AssertionError("Expected PermissionError for tenant without membership")


def test_resolve_tenant_role_returns_none_without_membership(monkeypatch):
    import app.gateway.auth as auth_module

    async def _fake_get_membership(user_id: str, tenant_id: str):
        return None

    monkeypatch.setattr(auth_module, "get_membership", _fake_get_membership)

    tenant_role = asyncio.run(auth_module._resolve_tenant_role("u-1", "tenant-a"))
    assert tenant_role is None
