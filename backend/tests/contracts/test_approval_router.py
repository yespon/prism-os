from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.gateway import auth
from app.gateway.routers import approvals as routes

from .test_policy_persistence import _approval


class FakeApprovalService:
    def __init__(self):
        self.calls = []

    async def get_for_user(self, tenant_id, approval_id, user_id):
        self.calls.append(("get", tenant_id, approval_id, user_id))
        return _approval()

    async def review(self, tenant_id, approval_id, user_id, action):
        self.calls.append((action, tenant_id, approval_id, user_id))
        return _approval()


def _client(monkeypatch, service):
    monkeypatch.setattr(auth, "_resolve_user_from_auth_db", lambda token: ("admin-1", "user", False) if token == "valid" else None)
    monkeypatch.setattr(auth, "_resolve_user_status_from_auth_db", lambda _user: "active")

    async def resolve_tenant(user_id, requested_tenant_id):
        if requested_tenant_id and requested_tenant_id != "tenant-a":
            raise PermissionError("not a tenant member")
        return "tenant-a"

    async def resolve_role(user_id, tenant_id):
        return "tenant_admin"

    monkeypatch.setattr(auth, "_resolve_tenant_id", resolve_tenant)
    monkeypatch.setattr(auth, "_resolve_tenant_role", resolve_role)
    app = FastAPI()
    app.add_middleware(auth.AuthMiddleware)
    app.include_router(routes.router)
    app.dependency_overrides[routes.get_approval_service] = lambda: service
    return TestClient(app)


def test_approval_api_requires_authenticated_session(monkeypatch) -> None:
    service = FakeApprovalService()
    with _client(monkeypatch, service) as client:
        assert client.post("/api/approvals/approval-1/approve").status_code == 401
        assert client.post("/api/approvals/approval-1/approve", headers={"Authorization": "Bearer invalid"}).status_code == 401
    assert service.calls == []


def test_browser_identity_fields_cannot_select_tenant_or_approver(monkeypatch) -> None:
    service = FakeApprovalService()
    with _client(monkeypatch, service) as client:
        result = client.post(
            "/api/approvals/approval-1/approve",
            headers={"Authorization": "Bearer valid", "X-Tenant-Id": "tenant-a"},
            json={"tenant_id": "tenant-b", "approver_id": "attacker", "status": "approved"},
        )
        assert result.status_code == 200
        assert service.calls == [("approve", "tenant-a", "approval-1", "admin-1")]
        denied = client.post(
            "/api/approvals/approval-1/reject",
            headers={"Authorization": "Bearer valid", "X-Tenant-Id": "tenant-b"},
        )
        assert denied.status_code == 403
    assert len(service.calls) == 1


def test_approval_read_uses_session_identity(monkeypatch) -> None:
    service = FakeApprovalService()
    with _client(monkeypatch, service) as client:
        result = client.get("/api/approvals/approval-1", headers={"Authorization": "Bearer valid"})
        assert result.status_code == 200
    assert service.calls == [("get", "tenant-a", "approval-1", "admin-1")]
