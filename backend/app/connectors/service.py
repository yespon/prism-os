"""Connector instance service: tenant-scoped lifecycle over the reference connectors."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.connectors import (
    ConnectorError,
    ConnectorResult,
    SqliteAnalyticsConnector,
    WebhookConnector,
)
from app.models.knowledge import ConnectorInstanceRecord
from deerflow.database.session import get_session_factory

WEBHOOK_CATALOG_ID = "catalog_webhook_v1"
SQLITE_ANALYTICS_CATALOG_ID = "catalog_sqlite_analytics_v1"


class ConnectorService:
    """Owns connector instance rows and dispatches invocations with secrets injected."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession] | None = None) -> None:
        self._session_factory = session_factory or get_session_factory()

    async def create_instance(self, tenant_id: str, owner_user_id: str, catalog_id: str,
                              name: str, *, secret_ref_id: str | None = None,
                              config: dict | None = None) -> ConnectorInstanceRecord:
        if catalog_id not in (WEBHOOK_CATALOG_ID, SQLITE_ANALYTICS_CATALOG_ID):
            raise ConnectorError("unknown_catalog", "connector kind is not in the catalog")
        if not name.strip():
            raise ConnectorError("invalid_name", "name must not be blank")
        record = ConnectorInstanceRecord(
            id=f"conn_{uuid4().hex}", tenant_id=tenant_id, catalog_id=catalog_id,
            owner_user_id=owner_user_id, name=name.strip(),
            secret_ref_id=secret_ref_id, status="configured",
            last_health=None, created_at=datetime.now(UTC),
        )
        async with self._session_factory() as session, session.begin():
            session.add(record)
        return record

    async def list_instances(self, tenant_id: str, user_id: str) -> list[ConnectorInstanceRecord]:
        async with self._session_factory() as session:
            return list((await session.exec(
                select(ConnectorInstanceRecord).where(
                    ConnectorInstanceRecord.tenant_id == tenant_id,
                )
            )).all())

    async def disable(self, tenant_id: str, instance_id: str, user_id: str) -> None:
        async with self._session_factory() as session, session.begin():
            record = await session.get(ConnectorInstanceRecord, instance_id)
            if record is None or record.tenant_id != tenant_id:
                raise ConnectorError("not_found", "connector instance not found")
            if record.owner_user_id != user_id:
                raise ConnectorError("forbidden", "only the owner can disable")
            record.status = "disabled"
            session.add(record)

    async def invoke_webhook(self, tenant_id: str, user_id: str, instance_id: str,
                             payload: dict, material) -> ConnectorResult:
        """Invoke a webhook instance; material carries the resolved SecretRef credentials."""
        record = await self._enabled_instance(tenant_id, instance_id)
        if record.catalog_id != WEBHOOK_CATALOG_ID:
            raise ConnectorError("wrong_kind", "instance is not a webhook connector")
        connector = WebhookConnector(material.webhook_url, material.headers)
        return await connector.invoke(payload)

    async def invoke_sqlite(self, tenant_id: str, instance_id: str, database_path, sql: str) -> ConnectorResult:
        record = await self._enabled_instance(tenant_id, instance_id)
        if record.catalog_id != SQLITE_ANALYTICS_CATALOG_ID:
            raise ConnectorError("wrong_kind", "instance is not an analytics connector")
        return SqliteAnalyticsConnector(database_path).invoke(sql)

    async def _enabled_instance(self, tenant_id: str, instance_id: str) -> ConnectorInstanceRecord:
        async with self._session_factory() as session:
            record = await session.get(ConnectorInstanceRecord, instance_id)
        if record is None or record.tenant_id != tenant_id:
            raise ConnectorError("not_found", "connector instance not found")
        if record.status != "configured":
            raise ConnectorError("disabled", "connector instance is disabled")
        return record
