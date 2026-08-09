from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from app.gateway.routers import tenants


def _create_app() -> FastAPI:
    app = FastAPI()

    @app.middleware("http")
    async def inject_user(request: Request, call_next):
        request.state.user_id = request.headers.get("x-user-id", "user-a")
        request.state.user_role = request.headers.get("x-user-role", "member")
        request.state.tenant_id = request.headers.get("x-tenant-id", "tenant-a")
        request.state.tenant_role = request.headers.get("x-tenant-role", "tenant_admin")
        return await call_next(request)

    app.include_router(tenants.router)
    return app


def test_list_tenants_returns_memberships(monkeypatch):
    app = _create_app()

    class _Tenant:
        def __init__(self, tenant_id: str, name: str, slug: str):
            self.id = tenant_id
            self.name = name
            self.slug = slug

    class _Membership:
        def __init__(self, role: str):
            self.role = role

    async def _fake_list_user_tenants(user_id: str):
        return [(_Tenant("tenant-a", "Tenant A", "tenant-a"), _Membership("admin"))]

    monkeypatch.setattr(tenants, "list_user_tenants", _fake_list_user_tenants)

    with TestClient(app) as client:
        resp = client.get("/api/tenants")

    assert resp.status_code == 200
    assert resp.json() == {
        "tenants": [
            {
                "id": "tenant-a",
                "name": "Tenant A",
                "slug": "tenant-a",
                "role": "tenant_admin",
                "tenant_type": "general",
            }
        ]
    }


def test_get_current_tenant_falls_back_to_first_when_not_persisted(monkeypatch):
    app = _create_app()

    class _Tenant:
        def __init__(self, tenant_id: str, name: str, slug: str):
            self.id = tenant_id
            self.name = name
            self.slug = slug

    class _Membership:
        def __init__(self, role: str):
            self.role = role

    called = {}

    async def _fake_list_user_tenants(user_id: str):
        return [(_Tenant("tenant-a", "Tenant A", "tenant-a"), _Membership("member"))]

    async def _fake_get_current_tenant_id(user_id: str):
        return None

    async def _fake_set_current_tenant_id(user_id: str, tenant_id: str):
        called["tenant_id"] = tenant_id

    monkeypatch.setattr(tenants, "list_user_tenants", _fake_list_user_tenants)
    monkeypatch.setattr(tenants, "get_current_tenant_id", _fake_get_current_tenant_id)
    monkeypatch.setattr(tenants, "set_current_tenant_id", _fake_set_current_tenant_id)

    with TestClient(app) as client:
        resp = client.get("/api/tenants/current")

    assert resp.status_code == 200
    assert resp.json() == {"tenant_id": "tenant-a", "role": "tenant_member", "tenant_type": "general"}
    assert called["tenant_id"] == "tenant-a"


def test_switch_tenant_denies_non_members(monkeypatch):
    app = _create_app()

    async def _fake_get_membership(user_id: str, tenant_id: str):
        return None

    monkeypatch.setattr(tenants, "get_membership", _fake_get_membership)

    with TestClient(app) as client:
        resp = client.post("/api/tenants/switch", json={"tenant_id": "tenant-b"})

    assert resp.status_code == 403
    assert resp.json()["detail"] == "Tenant access denied"


def test_get_current_tenant_without_membership_returns_403(monkeypatch):
    app = _create_app()

    async def _fake_list_user_tenants(user_id: str):
        return []

    monkeypatch.setattr(tenants, "list_user_tenants", _fake_list_user_tenants)

    with TestClient(app) as client:
        resp = client.get("/api/tenants/current")

    assert resp.status_code == 403
    assert "未加入任何租户" in resp.json()["detail"]


def test_switch_tenant_persists_and_returns_role(monkeypatch):
    app = _create_app()

    class _Membership:
        def __init__(self, role: str):
            self.role = role

    calls = {}

    async def _fake_get_membership(user_id: str, tenant_id: str):
        return _Membership("admin")

    async def _fake_set_current_tenant_id(user_id: str, tenant_id: str):
        calls["user_id"] = user_id
        calls["tenant_id"] = tenant_id

    class _Tenant:
        tenant_type = "general"

    async def _fake_get_tenant(tenant_id: str):
        assert tenant_id == "tenant-b"
        return _Tenant()

    monkeypatch.setattr(tenants, "get_membership", _fake_get_membership)
    monkeypatch.setattr(tenants, "set_current_tenant_id", _fake_set_current_tenant_id)
    monkeypatch.setattr(tenants, "get_tenant", _fake_get_tenant)

    with TestClient(app) as client:
        resp = client.post("/api/tenants/switch", json={"tenant_id": "tenant-b"})

    assert resp.status_code == 200
    assert resp.json() == {"tenant_id": "tenant-b", "role": "tenant_admin", "tenant_type": "general"}
    assert calls == {"user_id": "user-a", "tenant_id": "tenant-b"}


def test_create_tenant_self_service_is_disabled() -> None:
    app = _create_app()

    with TestClient(app) as client:
        resp = client.post("/api/tenants", json={"name": "Tenant B", "slug": "tenant-b"})

    assert resp.status_code == 403
    assert "Self-service tenant creation is disabled" in resp.json()["detail"]


def test_add_member_records_audit_event(monkeypatch):
    app = _create_app()

    class _Membership:
        user_id = "user-b"
        role = "tenant_member"
        status = "active"

    class _Repo:
        def __init__(self):
            pass

        def get_user_by_id(self, user_id: str):
            return {"id": user_id, "email": "u@example.com", "name": "User B"}

    captured = {}

    async def _fake_add_tenant_member(tenant_id: str, user_id: str, role: str):
        return _Membership()

    def _fake_record_audit_event(event_type: str, **kwargs):
        captured["event_type"] = event_type
        captured.update(kwargs)

    monkeypatch.setattr(tenants, "AuthUserRepository", _Repo)
    monkeypatch.setattr(tenants, "add_tenant_member", _fake_add_tenant_member)
    monkeypatch.setattr(tenants, "record_audit_event", _fake_record_audit_event)

    with TestClient(app) as client:
        resp = client.post(
            "/api/tenants/members",
            headers={"x-tenant-id": "tenant-a", "x-user-id": "admin-u", "x-tenant-role": "tenant_admin"},
            json={"user_id": "user-b", "role": "tenant_member"},
        )

    assert resp.status_code == 200
    assert captured["event_type"] == "tenant.member.added"
    assert captured["actor_id"] == "admin-u"
    assert captured["target_user_id"] == "user-b"
    assert captured["tenant_id"] == "tenant-a"
    assert captured["scope"] == "tenant"


def test_remove_member_records_audit_event(monkeypatch):
    app = _create_app()

    captured = {}

    async def _fake_remove_tenant_member(tenant_id: str, user_id: str):
        return True

    def _fake_record_audit_event(event_type: str, **kwargs):
        captured["event_type"] = event_type
        captured.update(kwargs)

    monkeypatch.setattr(tenants, "remove_tenant_member", _fake_remove_tenant_member)
    monkeypatch.setattr(tenants, "record_audit_event", _fake_record_audit_event)

    with TestClient(app) as client:
        resp = client.delete(
            "/api/tenants/members/user-b",
            headers={"x-tenant-id": "tenant-a", "x-user-id": "admin-u", "x-tenant-role": "tenant_admin"},
        )

    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
    assert captured["event_type"] == "tenant.member.removed"
    assert captured["actor_id"] == "admin-u"
    assert captured["target_user_id"] == "user-b"
    assert captured["tenant_id"] == "tenant-a"
    assert captured["scope"] == "tenant"


def test_update_member_role_records_audit_event(monkeypatch):
    app = _create_app()

    class _Membership:
        user_id = "user-b"
        role = "tenant_admin"
        status = "active"

    class _Repo:
        def __init__(self):
            pass

        def get_user_by_id(self, user_id: str):
            return {"id": user_id, "email": "u@example.com", "name": "User B"}

    captured = {}

    async def _fake_update_tenant_member_role(tenant_id: str, user_id: str, role: str):
        return _Membership()

    def _fake_record_audit_event(event_type: str, **kwargs):
        captured["event_type"] = event_type
        captured.update(kwargs)

    monkeypatch.setattr(tenants, "AuthUserRepository", _Repo)
    monkeypatch.setattr(tenants, "update_tenant_member_role", _fake_update_tenant_member_role)
    monkeypatch.setattr(tenants, "record_audit_event", _fake_record_audit_event)

    with TestClient(app) as client:
        resp = client.put(
            "/api/tenants/members/user-b",
            headers={"x-tenant-id": "tenant-a", "x-user-id": "admin-u", "x-tenant-role": "tenant_admin"},
            json={"role": "tenant_admin"},
        )

    assert resp.status_code == 200
    assert captured["event_type"] == "tenant.member.role_updated"
    assert captured["actor_id"] == "admin-u"
    assert captured["target_user_id"] == "user-b"
    assert captured["tenant_id"] == "tenant-a"
    assert captured["scope"] == "tenant"


def test_update_member_status_records_audit_event(monkeypatch):
    app = _create_app()

    class _Membership:
        user_id = "user-b"
        role = "tenant_member"
        status = "inactive"

    class _Repo:
        def __init__(self):
            pass

        def get_user_by_id(self, user_id: str):
            return {"id": user_id, "email": "u@example.com", "name": "User B"}

    captured = {}

    async def _fake_set_tenant_member_status(tenant_id: str, user_id: str, status: str):
        return _Membership()

    def _fake_record_audit_event(event_type: str, **kwargs):
        captured["event_type"] = event_type
        captured.update(kwargs)

    monkeypatch.setattr(tenants, "AuthUserRepository", _Repo)
    monkeypatch.setattr(tenants, "set_tenant_member_status", _fake_set_tenant_member_status)
    monkeypatch.setattr(tenants, "record_audit_event", _fake_record_audit_event)

    with TestClient(app) as client:
        resp = client.patch(
            "/api/tenants/members/user-b/status",
            headers={"x-tenant-id": "tenant-a", "x-user-id": "admin-u", "x-tenant-role": "tenant_admin"},
            json={"status": "inactive"},
        )

    assert resp.status_code == 200
    assert captured["event_type"] == "tenant.member.status_updated"
    assert captured["actor_id"] == "admin-u"
    assert captured["target_user_id"] == "user-b"
    assert captured["tenant_id"] == "tenant-a"
    assert captured["scope"] == "tenant"
