"""Payload-free references for noncritical legacy audit projection."""

from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.governance import PlatformLegacyAuditDeliveryRecord
from app.platform.contracts import AuditEvent, stable_platform_id

DESTINATIONS = ("gateway_jsonl", "incident_action")


class LegacyAuditDeliveryOutbox:
    @staticmethod
    def stage(session: AsyncSession, event: AuditEvent) -> None:
        if event.event_type != "action.submitted" or event.action != "ticket.create":
            raise ValueError("only governed ticket result events have legacy projections")
        for destination in DESTINATIONS:
            session.add(PlatformLegacyAuditDeliveryRecord(
                id=stable_platform_id("event", f"legacy-{destination}", event.event_id),
                tenant_id=event.tenant_id, event_id=event.event_id,
                destination=destination, status="pending", attempts=0,
                created_at=event.recorded_at, updated_at=event.recorded_at,
            ))
