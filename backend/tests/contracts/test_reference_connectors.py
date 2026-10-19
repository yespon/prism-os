"""R2 reference connector contracts: unified invocation, errors, refusal paths."""

import sqlite3
from dataclasses import dataclass

import pytest

from app.connectors import ConnectorError, SqliteAnalyticsConnector, WebhookConnector
from app.connectors.service import (
    SQLITE_ANALYTICS_CATALOG_ID,
    WEBHOOK_CATALOG_ID,
    ConnectorService,
)


@dataclass
class Material:
    webhook_url: str
    headers: dict


def test_webhook_rejects_inline_credentials_and_http():
    with pytest.raises(ConnectorError) as exc:
        WebhookConnector("http://target.example/hook", {})
    assert exc.value.code == "invalid_target"
    with pytest.raises(ConnectorError):
        WebhookConnector("https://user:pass@target.example/hook", {})
    with pytest.raises(ConnectorError):
        WebhookConnector("https://target.example/hook?token=secret", {})


@pytest.mark.anyio
async def test_webhook_standard_error_mapping(monkeypatch):
    import httpx

    class FakeTransport(httpx.AsyncHTTPTransport):
        def __init__(self, status=None, raise_error=None):
            self.status = status
            self.raise_error = raise_error
            super().__init__()

        async def handle_async_request(self, request):
            if self.raise_error:
                raise self.raise_error
            return httpx.Response(self.status, json={"ok": True})

    def invoke_with(status=None, raise_error=None):
        transport = FakeTransport(status, raise_error)
        connector = WebhookConnector(
            "https://target.example/hook", {"Authorization": "Bearer k"},
            client_factory=lambda **kwargs: httpx.AsyncClient(transport=transport),
        )
        return connector.invoke({"a": 1})

    assert (await invoke_with(200)).ok is True
    assert (await invoke_with(400)).error_code == "rejected"
    assert (await invoke_with(503)).error_code == "upstream"
    assert (await invoke_with(raise_error=httpx.ConnectError("boom"))).error_code == "network"
    assert (await invoke_with(raise_error=httpx.ReadTimeout("slow"))).error_code == "timeout"


def test_sqlite_read_only_aggregation(tmp_path):
    database = tmp_path / "analytics.db"
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE events (kind TEXT, value INTEGER)")
        connection.executemany("INSERT INTO events VALUES (?, ?)", [("a", 1), ("b", 2), ("a", 3)])

    connector = SqliteAnalyticsConnector(database)
    result = connector.invoke("SELECT kind, SUM(value) AS total FROM events GROUP BY kind ORDER BY kind")
    assert result.ok and result.data["rows"] == [{"kind": "a", "total": 4}, {"kind": "b", "total": 2}]

    # Writes are forbidden at both the statement gate and the SQLite layer.
    assert connector.invoke("DELETE FROM events").error_code == "forbidden_sql"
    assert connector.invoke("SELECT 1; DROP TABLE events").error_code == "forbidden_sql"
    assert connector.invoke("SELECT * FROM missing").error_code == "bad_sql"


@pytest.mark.anyio
async def test_connector_service_lifecycle_and_refusal(tmp_path):
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from sqlmodel import SQLModel
    from sqlmodel.ext.asyncio.session import AsyncSession

    from app.models import knowledge as _knowledge_models  # noqa: F401

    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'connectors.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(SQLModel.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    service = ConnectorService(factory)

    instance = await service.create_instance("t1", "owner-1", WEBHOOK_CATALOG_ID, "pager")
    listed = await service.list_instances("t1", "owner-1")
    assert [row.id for row in listed] == [instance.id]

    # Cross-tenant invisible; unknown-catalog refused; wrong kind refused.
    assert await service.list_instances("t2", "owner-1") == []
    with pytest.raises(ConnectorError):
        await service.create_instance("t1", "owner-1", "catalog_unknown", "x")
    analytics = await service.create_instance("t1", "owner-1", SQLITE_ANALYTICS_CATALOG_ID, "analytics")
    with pytest.raises(ConnectorError) as wrong:
        await service.invoke_webhook("t1", "owner-1", analytics.id, {}, Material("https://x.example", {}))
    assert wrong.value.code == "wrong_kind"

    # Disabled instances refuse invocation.
    await service.disable("t1", instance.id, "owner-1")
    with pytest.raises(ConnectorError) as disabled:
        await service.invoke_webhook("t1", "owner-1", instance.id, {}, Material("https://x.example", {}))
    assert disabled.value.code == "disabled"

    # Only the owner can disable.
    with pytest.raises(ConnectorError) as forbidden:
        await service.disable("t1", analytics.id, "stranger")
    assert forbidden.value.code == "forbidden"
    await engine.dispose()
