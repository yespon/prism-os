import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel import SQLModel, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.alerting.ticket_secrets import TicketSecretRepository
from app.gateway.routers import alerts, ticket_secrets
from app.models.alerting import AlertSource
from app.models.governance import PlatformAuditEventRecord, PlatformTicketSecretRecord
from app.platform.audit.repository import AuditEventRepository
from app.platform.contracts import SecretRef
from deerflow.database.session import get_session


@pytest.fixture
async def secret_api(tmp_path, monkeypatch):
    monkeypatch.setenv("DEERFLOW_SECRETS_ENCRYPTION_KEY", "test-key")
    monkeypatch.setenv("PRISMOS_TICKET_SECRET_ADMIN_TENANT", "tenant-a")
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'secret-admin.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        session.add_all([AlertSource(id="source-a", tenant_id="tenant-a", name="monitor-a", config_json={
            "ticket": {"provider": "webhook", "webhook_url": "https://tickets.example/old", "headers": {"Authorization": "old-secret"}},
            "analysis_trigger": {"enabled": False},
        }), AlertSource(id="source-a2", tenant_id="tenant-a", name="monitor-a2"),
            AlertSource(id="source-b", tenant_id="tenant-b", name="monitor-b")])
        await session.commit()
    app = FastAPI()
    app.include_router(ticket_secrets.router)
    app.include_router(alerts.router)

    @app.middleware("http")
    async def identity(request, call_next):
        request.state.tenant_id = request.headers.get("x-test-tenant", "tenant-a")
        request.state.tenant_role = request.headers.get("x-test-role", "admin")
        request.state.user_id = "admin-a"
        return await call_next(request)

    async def session_dependency():
        async with factory() as session:
            yield session

    app.dependency_overrides[get_session] = session_dependency
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client, factory
    await engine.dispose()


def credential_input():
    return {"webhook_url": "https://tickets.example/create?token=private-url-secret",
            "headers": {"Authorization": "Bearer private-header-secret"}}


@pytest.mark.anyio
async def test_admin_lifecycle_binds_config_and_does_not_return_secrets(secret_api, monkeypatch):
    client, factory = secret_api
    url = "/api/alert-sources/source-a/ticket-secret"
    created = await client.post(url, json=credential_input())
    assert created.status_code == 201, created.text
    assert "private-url-secret" not in created.text and "private-header-secret" not in created.text
    first = SecretRef.model_validate(created.json()["secret_ref"])
    async with factory() as session:
        source = await session.get(AlertSource, "source-a")
        assert source.config_json["ticket"] == {"provider": "webhook", "secret_ref": first.model_dump(mode="json")}
        assert source.config_json["analysis_trigger"] == {"enabled": False}
        assert (await TicketSecretRepository().read(session, "tenant-a", "source-a", first)).headers["Authorization"] == "Bearer private-header-secret"
        events = (await session.exec(select(PlatformAuditEventRecord))).all()
        assert len(events) == 1 and events[0].event_type == "secret.created"
        assert "private-header-secret" not in str(events[0].event_json)
        assert "private-url-secret" not in str(events[0].event_json)
    monkeypatch.delenv("DEERFLOW_SECRETS_ENCRYPTION_KEY")
    status = await client.get(url)
    assert status.status_code == 200 and status.json()["active"] is True
    monkeypatch.setenv("DEERFLOW_SECRETS_ENCRYPTION_KEY", "test-key")
    assert (await client.post(url, json=credential_input())).status_code == 409
    assert (await client.put(url, json={**credential_input(), "expected_ref_id": "stale"})).status_code == 409
    rotated = await client.put(url, json={**credential_input(), "expected_ref_id": first.id})
    assert rotated.status_code == 200, rotated.text
    second = SecretRef.model_validate(rotated.json()["secret_ref"])
    assert second.id != first.id
    async with factory() as session:
        with pytest.raises(PermissionError):
            await TicketSecretRepository().read(session, "tenant-a", "source-a", first)
    assert (await client.delete(url, params={"expected_ref_id": first.id})).status_code == 409
    disabled = await client.delete(url, params={"expected_ref_id": second.id})
    assert disabled.status_code == 200 and disabled.json()["active"] is False
    assert (await client.get(url)).json()["active"] is False
    async with factory() as session:
        with pytest.raises(PermissionError):
            await TicketSecretRepository().read(session, "tenant-a", "source-a", second)


@pytest.mark.anyio
async def test_member_and_cross_tenant_cannot_manage_secret(secret_api, monkeypatch):
    client, _ = secret_api
    url = "/api/alert-sources/source-a/ticket-secret"
    for method in ("GET", "POST", "PUT", "DELETE"):
        response = await client.request(method, url, headers={"x-test-role": "member"},
                                        params={"expected_ref_id": "ref"}, json=credential_input())
        assert response.status_code == 403
    monkeypatch.setenv("PRISMOS_TICKET_SECRET_ADMIN_TENANT", "tenant-b")
    response = await client.post(url, headers={"x-test-tenant": "tenant-b"}, json=credential_input())
    assert response.status_code == 404
    monkeypatch.delenv("PRISMOS_TICKET_SECRET_ADMIN_TENANT")
    assert (await client.get(url)).status_code == 503


@pytest.mark.anyio
@pytest.mark.parametrize("body", [{"webhook_url": {"private-secret": True}},
                                  {"webhook_url": "https://tickets.example", "headers": {"Authorization": "private-secret\r\n"}},
                                  {**credential_input(), "tenant_id": "tenant-b"}])
async def test_invalid_secret_input_errors_never_echo_values(secret_api, body):
    client, _ = secret_api
    response = await client.post("/api/alert-sources/source-a/ticket-secret", json=body)
    assert response.status_code == 400
    assert "private-secret" not in response.text and "private-header-secret" not in response.text
    assert "private-url-secret" not in response.text


@pytest.mark.anyio
async def test_missing_key_and_critical_audit_failure_roll_back_all_writes(secret_api, monkeypatch):
    client, factory = secret_api
    url = "/api/alert-sources/source-a/ticket-secret"
    monkeypatch.delenv("DEERFLOW_SECRETS_ENCRYPTION_KEY")
    assert (await client.post(url, json=credential_input())).status_code == 503
    monkeypatch.setenv("DEERFLOW_SECRETS_ENCRYPTION_KEY", "test-key")

    async def audit_failure(*_args):
        raise RuntimeError("critical audit unavailable")

    monkeypatch.setattr(AuditEventRepository, "append_in_session", audit_failure)
    assert (await client.post(url, json=credential_input())).status_code == 503
    async with factory() as session:
        assert (await session.exec(select(PlatformTicketSecretRecord))).all() == []
        source = await session.get(AlertSource, "source-a")
        assert source.config_json["ticket"]["headers"]["Authorization"] == "old-secret"


@pytest.mark.anyio
async def test_regular_source_config_cannot_replace_remove_or_forge_reference(secret_api):
    client, _ = secret_api
    created = await client.post("/api/alert-sources/source-a/ticket-secret", json=credential_input())
    assert created.status_code == 201
    ref = created.json()["secret_ref"]
    valid = {"ticket": {"provider": "webhook", "secret_ref": ref}}
    assert (await client.put("/api/alert-sources/source-a", json={"config_json": valid})).status_code == 200
    for source_id, config in [("source-a2", valid), ("source-a", {}),
                              ("source-a", {"ticket": {"secret_ref": ref, "headers": {"Authorization": "private-secret"}}})]:
        response = await client.put(f"/api/alert-sources/{source_id}", json={"config_json": config})
        assert response.status_code == 400 and "private-secret" not in response.text
    assert (await client.post("/api/alert-sources", json={"name": "forged", "config_json": valid})).status_code == 400


@pytest.mark.anyio
async def test_failed_rotation_retains_old_binding_and_active_credential(secret_api, monkeypatch):
    client, factory = secret_api
    url = "/api/alert-sources/source-a/ticket-secret"
    created = await client.post(url, json=credential_input())
    assert created.status_code == 201
    first = SecretRef.model_validate(created.json()["secret_ref"])

    async def audit_failure(*_args):
        raise RuntimeError("audit unavailable")

    monkeypatch.setattr(AuditEventRepository, "append_in_session", audit_failure)
    rotated = await client.put(url, json={**credential_input(), "expected_ref_id": first.id})
    assert rotated.status_code == 503
    async with factory() as session:
        rows = (await session.exec(select(PlatformTicketSecretRecord))).all()
        assert len(rows) == 1 and rows[0].active is True
        source = await session.get(AlertSource, "source-a")
        assert source.config_json["ticket"]["secret_ref"]["id"] == first.id
        assert (await TicketSecretRepository().read(session, "tenant-a", "source-a", first)).headers["Authorization"] == "Bearer private-header-secret"


@pytest.mark.anyio
async def test_parallel_rotation_accepts_only_one_current_binding(secret_api):
    import asyncio

    client, factory = secret_api
    url = "/api/alert-sources/source-a/ticket-secret"
    created = await client.post(url, json=credential_input())
    assert created.status_code == 201
    old_id = created.json()["secret_ref"]["id"]
    responses = await asyncio.gather(*[
        client.put(url, json={**credential_input(), "expected_ref_id": old_id}) for _ in range(2)
    ])
    assert sorted(response.status_code for response in responses) == [200, 409]
    accepted = next(response for response in responses if response.status_code == 200)
    current_id = accepted.json()["secret_ref"]["id"]
    async with factory() as session:
        rows = (await session.exec(select(PlatformTicketSecretRecord))).all()
        assert len(rows) == 2
        assert [row.id for row in rows if row.active] == [current_id]
        assert (await session.get(AlertSource, "source-a")).config_json["ticket"]["secret_ref"]["id"] == current_id
