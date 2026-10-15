from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from test_skills_scope_router import _create_app as _create_resource_context_app
from test_skills_scope_router import current_identity_database as resource_identity_database  # noqa: F401

import app.gateway.routers.mcp as mcp_router
import app.gateway.routers.models as models_router
import app.gateway.routers.skills as skills_router


def _create_app() -> FastAPI:
    app = FastAPI()

    @app.middleware("http")
    async def inject_context(request: Request, call_next):
        request.state.user_id = request.headers.get("x-user-id", "user-a")
        request.state.user_role = request.headers.get("x-user-role", "user")
        request.state.tenant_role = request.headers.get("x-tenant-role", "tenant_member")
        tenant_id = request.headers.get("x-tenant-id")
        if tenant_id is not None:
            request.state.tenant_id = tenant_id
        return await call_next(request)

    app.include_router(models_router.router)
    app.include_router(mcp_router.router)
    app.include_router(skills_router.router)
    return app


def test_models_router_requires_tenant_context(monkeypatch):
    app = _create_app()

    async def _fake_get_user_models(user_id: str, tenant_id: str | None = None):
        return []

    monkeypatch.setattr(models_router, "get_user_models", _fake_get_user_models)

    with TestClient(app) as client:
        missing = client.get("/api/models")
        assert missing.status_code == 400

        ok = client.get("/api/models", headers={"x-tenant-id": "tenant-a"})
        assert ok.status_code == 200
        assert ok.json() == {"models": []}


def test_mcp_router_requires_tenant_context(monkeypatch):
    app = _create_app()

    async def _fake_get_user_mcp_servers(user_id: str, tenant_id: str | None = None):
        return []

    monkeypatch.setattr(mcp_router, "get_user_mcp_servers", _fake_get_user_mcp_servers)
    monkeypatch.setattr(mcp_router, "_build_default_payloads", lambda: ({}, {"mcp_servers": {}}))

    with TestClient(app) as client:
        missing = client.get("/api/mcp/config")
        assert missing.status_code == 400

        ok = client.get("/api/mcp/config", headers={"x-tenant-id": "tenant-a"})
        assert ok.status_code == 200
        assert ok.json() == {"mcp_servers": {}}


def test_skills_router_requires_tenant_context(monkeypatch):
    app = _create_resource_context_app()

    async def empty_resources(user_id, tenant_id, **kwargs):
        return []

    monkeypatch.setattr(skills_router, "get_available_skills", empty_resources)

    with TestClient(app) as client:
        missing = client.get("/api/skills")
        assert missing.status_code == 400

        ok = client.get("/api/skills", headers={"x-tenant-id": "tenant-a"})
        assert ok.status_code == 200
        assert ok.json() == {"skills": []}


def test_models_write_requires_admin_role(monkeypatch):
    app = _create_app()

    async def _fake_create_user_model(user_id: str, payload: dict, tenant_id: str | None = None):
        return type(
            "_Row",
            (),
            {
                "name": payload["name"],
                "model": payload["model"],
                "display_name": payload.get("display_name"),
                "description": payload.get("description"),
                "supports_thinking": bool(payload.get("supports_thinking", False)),
                "supports_reasoning_effort": bool(payload.get("supports_reasoning_effort", False)),
                "settings": {"enabled": True},
            },
        )()

    monkeypatch.setattr(models_router, "create_user_model", _fake_create_user_model)

    body = {"name": "m1", "model": "provider/m1"}
    with TestClient(app) as client:
        denied = client.post("/api/models", headers={"x-tenant-id": "tenant-a"}, json=body)
        assert denied.status_code == 403

        ok = client.post(
            "/api/models",
            headers={"x-tenant-id": "tenant-a", "x-tenant-role": "tenant_admin"},
            json=body,
        )
        assert ok.status_code == 201
        assert ok.json()["name"] == "m1"


def test_mcp_write_requires_admin_role(monkeypatch):
    app = _create_app()

    async def _fake_replace_user_mcp_servers(user_id: str, payload: dict, tenant_id: str | None = None):
        return None

    monkeypatch.setattr(mcp_router, "replace_user_mcp_servers", _fake_replace_user_mcp_servers)

    body = {
        "mcp_servers": {
            "demo": {
                "enabled": True,
                "type": "stdio",
                "command": "echo",
                "args": [],
                "env": {},
                "url": None,
                "headers": {},
                "oauth": None,
                "description": "demo",
                "is_builtin": False,
            }
        }
    }

    with TestClient(app) as client:
        denied = client.put("/api/mcp/config", headers={"x-tenant-id": "tenant-a"}, json=body)
        assert denied.status_code == 403

        ok = client.put(
            "/api/mcp/config",
            headers={"x-tenant-id": "tenant-a", "x-tenant-role": "tenant_admin"},
            json=body,
        )
        assert ok.status_code == 200


def test_skills_write_requires_admin_role(monkeypatch):
    app = _create_app()

    with TestClient(app) as client:
        denied = client.put(
            "/api/skills/bootstrap",
            headers={"x-tenant-id": "tenant-a"},
            json={"enabled": True},
        )
        assert denied.status_code == 405

        ok = client.put(
            "/api/skills/bootstrap",
            headers={"x-tenant-id": "tenant-a", "x-tenant-role": "tenant_admin"},
            json={"enabled": True},
        )
        assert ok.status_code == 405
