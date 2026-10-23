"""R3 schedule API contracts."""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.gateway import auth
from app.gateway.routers import schedules as routes
from app.scheduling import ScheduleService


def _client(monkeypatch, tmp_path):
    import asyncio

    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from sqlmodel import SQLModel
    from sqlmodel.ext.asyncio.session import AsyncSession

    from app.models import scheduling as _scheduling_models  # noqa: F401

    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'schedule-api.db'}")

    async def setup():
        async with engine.begin() as connection:
            await connection.run_sync(SQLModel.metadata.create_all)

    asyncio.run(setup())
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    service = ScheduleService(factory)
    monkeypatch.setattr(routes, "_service", lambda: service)

    monkeypatch.setattr(auth, "_resolve_user_from_auth_db", lambda token: ("user-1", "user", False) if token == "valid" else None)
    monkeypatch.setattr(auth, "_resolve_user_status_from_auth_db", lambda _user: "active")

    async def resolve_tenant(user_id=None, requested_tenant_id=None):
        return requested_tenant_id or "t1"

    monkeypatch.setattr(auth, "_resolve_tenant_id", resolve_tenant)

    async def resolve_role(*, user_id, tenant_id):
        return "user"

    monkeypatch.setattr(auth, "_resolve_tenant_role", resolve_role)

    app = FastAPI()
    app.add_middleware(auth.AuthMiddleware)
    app.include_router(routes.router)
    return TestClient(app), service


def _auth(client):
    client.headers.update({"Authorization": "Bearer valid", "x-tenant-id": "t1"})
    return client


def test_schedule_crud_and_ownership(monkeypatch, tmp_path):
    client, _service = _client(monkeypatch, tmp_path)
    with client:
        _auth(client)
        created = client.post("/api/schedules", json={
            "name": "nightly", "trigger_kind": "cron", "cron_expr": "0 3 * * *",
            "agent_name": "default", "prompt": "Run the nightly check.",
        })
        assert created.status_code == 201, created.text
        schedule_id = created.json()["id"]

        listed = client.get("/api/schedules")
        assert [s["id"] for s in listed.json()["schedules"]] == [schedule_id]

        invalid = client.post("/api/schedules", json={"name": "x", "trigger_kind": "cron", "agent_name": "a", "prompt": "p"})
        assert invalid.status_code == 400

        disabled = client.post(f"/api/schedules/{schedule_id}/enabled", json={"enabled": False})
        assert disabled.status_code == 200 and disabled.json()["enabled"] is False

        deleted = client.delete(f"/api/schedules/{schedule_id}")
        assert deleted.status_code == 204
        assert client.get("/api/schedules").json()["schedules"] == []


def test_run_now_and_occurrence_listing(monkeypatch, tmp_path):
    client, service = _client(monkeypatch, tmp_path)
    with client:
        _auth(client)
        created = client.post("/api/schedules", json={
            "name": "manual", "trigger_kind": "interval", "interval_seconds": 3600,
            "agent_name": "default", "prompt": "Summarize the queue.",
        })
        schedule_id = created.json()["id"]

        first = client.post(f"/api/schedules/{schedule_id}/run-now")
        assert first.status_code == 202 and first.json()["will_execute"] is True

        # Same-second collision: the second run-now for the same slot must not re-execute.
        second = client.post(f"/api/schedules/{schedule_id}/run-now")
        assert second.status_code == 202 and second.json()["will_execute"] is False

        occurrences = client.get(f"/api/schedules/{schedule_id}/occurrences")
        assert len(occurrences.json()["occurrences"]) == 1


def test_cross_tenant_isolation(monkeypatch, tmp_path):
    client, _service = _client(monkeypatch, tmp_path)
    with client:
        _auth(client)
        created = client.post("/api/schedules", json={
            "name": "private", "trigger_kind": "cron", "cron_expr": "* * * * *",
            "agent_name": "default", "prompt": "Check.",
        })
        schedule_id = created.json()["id"]

        client.headers.update({"x-tenant-id": "t2"})
        assert client.get("/api/schedules").json()["schedules"] == []
        assert client.post(f"/api/schedules/{schedule_id}/run-now").status_code == 404
        assert client.get(f"/api/schedules/{schedule_id}/occurrences").status_code == 200
        assert client.get(f"/api/schedules/{schedule_id}/occurrences").json()["occurrences"] == []
