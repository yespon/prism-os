"""Replayable, sanitized compatibility projections for governed ticket results."""

import asyncio
from collections.abc import Callable
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.gateway.audit import record_platform_audit_event
from app.models.alerting import IncidentAction
from app.models.governance import (
    PlatformActionSubmissionRecord,
    PlatformAuditEventRecord,
    PlatformLegacyAuditDeliveryRecord,
)
from app.platform.contracts import AuditEvent
from deerflow.database.session import get_session_factory

class LegacyAuditDeliveryService:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession] | None = None,
        gateway_writer: Callable[[dict], None] = record_platform_audit_event,
    ) -> None:
        self._session_factory = session_factory or get_session_factory()
        self._gateway_writer = gateway_writer

    async def list_undelivered(self, tenant_id: str) -> list[PlatformLegacyAuditDeliveryRecord]:
        async with self._session_factory() as session:
            statement = select(PlatformLegacyAuditDeliveryRecord).where(
                PlatformLegacyAuditDeliveryRecord.tenant_id == tenant_id,
                PlatformLegacyAuditDeliveryRecord.status != "delivered",
            ).order_by(PlatformLegacyAuditDeliveryRecord.created_at, PlatformLegacyAuditDeliveryRecord.id)
            return list((await session.exec(statement)).all())

    async def counts(self, tenant_id: str) -> dict[str, int]:
        async with self._session_factory() as session:
            rows = (await session.exec(select(PlatformLegacyAuditDeliveryRecord).where(
                PlatformLegacyAuditDeliveryRecord.tenant_id == tenant_id,
            ))).all()
            return {status: sum(row.status == status for row in rows) for status in ("pending", "failed", "delivered")}

    async def deliver(self, tenant_id: str, delivery_id: str) -> bool:
        async with self._session_factory() as session:
            row = await session.get(PlatformLegacyAuditDeliveryRecord, delivery_id)
            if row is None or row.tenant_id != tenant_id:
                raise ValueError("legacy audit delivery unavailable")
            if row.status == "delivered":
                return True
            event_row = await session.get(PlatformAuditEventRecord, row.event_id)
            if event_row is None or event_row.tenant_id != tenant_id:
                raise ValueError("platform AuditEvent unavailable")
            event = AuditEvent.model_validate(event_row.event_json)
            submission = (await session.exec(select(PlatformActionSubmissionRecord).where(
                PlatformActionSubmissionRecord.tenant_id == tenant_id,
                PlatformActionSubmissionRecord.decision_id == event.policy_decision_id,
                PlatformActionSubmissionRecord.status == "submitted",
            ))).one_or_none()
            if submission is None or submission.ticket_id != event.payload.get("ticket_id"):
                raise ValueError("submitted ticket fact unavailable or changed")
            destination = row.destination
        try:
            if destination == "gateway_jsonl":
                await asyncio.to_thread(self._gateway_writer, {
                    "event_id": event.event_id, "event_type": event.event_type,
                    "actor_id": event.execution.actor.id if event.execution.actor else None,
                    "tenant_id": tenant_id, "scope": "ticket.create", "severity": event.severity,
                    "metadata": {"decision_id": event.policy_decision_id,
                                 "approval_id": event.approval_id,
                                 "run_id": event.run_id, "incident_id": event.resource_id,
                                 "ticket_id": submission.ticket_id, "provider": submission.provider},
                })
            elif destination == "incident_action":
                async with self._session_factory() as session, session.begin():
                    existing = await session.get(IncidentAction, event.event_id)
                    if existing is None:
                        session.add(IncidentAction(
                            id=event.event_id, tenant_id=tenant_id,
                            incident_id=event.resource_id,
                            actor_id=event.execution.actor.id if event.execution.actor else None,
                            action_type="ticket_created",
                            action_payload={"ticket_id": submission.ticket_id,
                                            "provider": submission.provider,
                                            "platform_event_id": event.event_id},
                            created_at=event.recorded_at,
                        ))
                    elif existing.tenant_id != tenant_id or existing.incident_id != event.resource_id or existing.action_payload.get("platform_event_id") != event.event_id:
                        raise ValueError("legacy IncidentAction identity conflict")
            else:
                raise ValueError("unknown legacy audit destination")
        except Exception as exc:
            await self._settle(tenant_id, delivery_id, False, type(exc).__name__)
            return False
        await self._settle(tenant_id, delivery_id, True, None)
        return True

    async def _settle(self, tenant_id: str, delivery_id: str, delivered: bool, category: str | None) -> None:
        async with self._session_factory() as session, session.begin():
            row = await session.get(PlatformLegacyAuditDeliveryRecord, delivery_id)
            if row is None or row.tenant_id != tenant_id:
                raise ValueError("legacy audit delivery unavailable")
            if row.status == "delivered":
                return
            row.attempts += 1
            row.status = "delivered" if delivered else "failed"
            row.error_category = category
            row.updated_at = datetime.now(UTC)
            session.add(row)

    async def deliver_event(self, tenant_id: str, event_id: str) -> None:
        async with self._session_factory() as session:
            rows = (await session.exec(select(PlatformLegacyAuditDeliveryRecord).where(
                PlatformLegacyAuditDeliveryRecord.tenant_id == tenant_id,
                PlatformLegacyAuditDeliveryRecord.event_id == event_id,
            ))).all()
        for row in rows:
            await self.deliver(tenant_id, row.id)

    async def replay(self, tenant_id: str, *, limit: int = 100) -> int:
        if limit <= 0:
            return 0
        pending = (await self.list_undelivered(tenant_id))[:min(limit, 1000)]
        return sum([await self.deliver(tenant_id, row.id) for row in pending])
