"""Tenant-scoped schedule service: definitions, occurrences, delivery (R3).

Core invariants from the R3 spec:
- occurrence creation is idempotent per (tenant, schedule, scheduled_at):
  a second trigger for the same slot returns the existing occurrence and
  never starts a second business execution;
- run-now collides with a scheduled slot through the same key;
- delivery retries update DeliveryAttempt only;
- every read path filters by tenant.
"""

from datetime import UTC, datetime
from hashlib import sha256
from uuid import uuid4

from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.scheduling import (
    DeliveryAttemptRecord,
    ScheduleDefinitionRecord,
    ScheduleOccurrenceRecord,
)
from deerflow.database.session import get_session_factory

TRIGGER_KINDS = ("cron", "date", "interval")


class SchedulingError(Exception):
    """Domain error with a user-presentable message."""


def occurrence_idempotency_key(tenant_id: str, schedule_id: str, scheduled_at: datetime) -> str:
    stamp = scheduled_at.astimezone(UTC).strftime("%Y%m%dT%H%M%S")
    digest = sha256(f"{tenant_id}:{schedule_id}:{stamp}".encode()).hexdigest()[:16]
    return f"{schedule_id}:{stamp}:{digest}"


class ScheduleService:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession] | None = None) -> None:
        self._session_factory = session_factory or get_session_factory()

    # ---- definitions ----

    async def create_definition(self, tenant_id: str, owner_user_id: str, *, name: str,
                                trigger_kind: str, cron_expr: str | None = None,
                                run_at: datetime | None = None, interval_seconds: int | None = None,
                                timezone: str = "Asia/Shanghai", agent_name: str,
                                agent_id: str | None = None, prompt: str,
                                delivery_channel: str = "web", delivery_target: str | None = None,
                                enabled: bool = True) -> ScheduleDefinitionRecord:
        if trigger_kind not in TRIGGER_KINDS:
            raise SchedulingError("trigger_kind must be cron, date or interval")
        if trigger_kind == "cron" and not cron_expr:
            raise SchedulingError("cron trigger requires cron_expr")
        if trigger_kind == "date" and run_at is None:
            raise SchedulingError("date trigger requires run_at")
        if trigger_kind == "interval" and not (interval_seconds and interval_seconds > 0):
            raise SchedulingError("interval trigger requires positive interval_seconds")
        if not name.strip() or not prompt.strip() or not agent_name.strip():
            raise SchedulingError("name, prompt and agent_name must not be blank")
        now = datetime.now(UTC)
        record = ScheduleDefinitionRecord(
            id=f"sched_{uuid4().hex}", tenant_id=tenant_id, owner_user_id=owner_user_id,
            name=name.strip(), trigger_kind=trigger_kind, cron_expr=cron_expr, run_at=run_at,
            interval_seconds=interval_seconds, timezone=timezone, agent_name=agent_name.strip(),
            agent_id=agent_id, prompt=prompt.strip(), delivery_channel=delivery_channel,
            delivery_target=delivery_target, enabled=enabled, created_at=now, updated_at=now,
        )
        async with self._session_factory() as session, session.begin():
            session.add(record)
        return record

    async def list_definitions(self, tenant_id: str, *, enabled_only: bool = False) -> list[ScheduleDefinitionRecord]:
        async with self._session_factory() as session:
            statement = select(ScheduleDefinitionRecord).where(ScheduleDefinitionRecord.tenant_id == tenant_id)
            if enabled_only:
                statement = statement.where(ScheduleDefinitionRecord.enabled == 1)
            return list((await session.exec(statement.order_by(ScheduleDefinitionRecord.created_at))).all())

    async def set_enabled(self, tenant_id: str, schedule_id: str, owner_user_id: str, enabled: bool) -> ScheduleDefinitionRecord:
        async with self._session_factory() as session, session.begin():
            record = await session.get(ScheduleDefinitionRecord, schedule_id)
            if record is None or record.tenant_id != tenant_id:
                raise SchedulingError("schedule not found")
            if record.owner_user_id != owner_user_id:
                raise SchedulingError("only the owner can change a schedule")
            record.enabled = enabled
            record.updated_at = datetime.now(UTC)
            session.add(record)
            return record

    async def delete_definition(self, tenant_id: str, schedule_id: str, owner_user_id: str) -> None:
        async with self._session_factory() as session, session.begin():
            record = await session.get(ScheduleDefinitionRecord, schedule_id)
            if record is None or record.tenant_id != tenant_id:
                raise SchedulingError("schedule not found")
            if record.owner_user_id != owner_user_id:
                raise SchedulingError("only the owner can delete a schedule")
            await session.delete(record)

    # ---- occurrences ----

    async def claim_occurrence(self, tenant_id: str, schedule_id: str, scheduled_at: datetime) -> tuple[ScheduleOccurrenceRecord, bool]:
        """Idempotently create-and-claim the occurrence for a trigger slot.

        Returns (occurrence, created): created=False means the slot already had
        an occurrence (restart replay, run-now collision) and must not execute
        again.
        """
        key = occurrence_idempotency_key(tenant_id, schedule_id, scheduled_at)
        async with self._session_factory() as session, session.begin():
            existing = (await session.exec(
                select(ScheduleOccurrenceRecord).where(
                    ScheduleOccurrenceRecord.tenant_id == tenant_id,
                    ScheduleOccurrenceRecord.idempotency_key == key,
                )
            )).first()
            if existing is not None:
                return existing, False
            record = ScheduleOccurrenceRecord(
                id=f"occ_{uuid4().hex}", tenant_id=tenant_id, schedule_id=schedule_id,
                scheduled_at=scheduled_at, idempotency_key=key, state="pending",
                created_at=datetime.now(UTC),
            )
            session.add(record)
            try:
                await session.commit()
            except Exception:
                await session.rollback()
                existing = (await session.exec(
                    select(ScheduleOccurrenceRecord).where(
                        ScheduleOccurrenceRecord.tenant_id == tenant_id,
                        ScheduleOccurrenceRecord.idempotency_key == key,
                    )
                )).first()
                if existing is not None:
                    return existing, False
                raise
            return record, True

    async def mark_running(self, tenant_id: str, occurrence_id: str, run_id: str) -> None:
        async with self._session_factory() as session, session.begin():
            record = await session.get(ScheduleOccurrenceRecord, occurrence_id)
            if record is None or record.tenant_id != tenant_id:
                raise SchedulingError("occurrence not found")
            record.state = "running"
            record.run_id = run_id
            record.started_at = datetime.now(UTC)
            session.add(record)

    async def mark_finished(self, tenant_id: str, occurrence_id: str, *, failed: bool = False) -> None:
        async with self._session_factory() as session, session.begin():
            record = await session.get(ScheduleOccurrenceRecord, occurrence_id)
            if record is None or record.tenant_id != tenant_id:
                raise SchedulingError("occurrence not found")
            record.state = "failed" if failed else "completed"
            record.finished_at = datetime.now(UTC)
            session.add(record)

    async def list_occurrences(self, tenant_id: str, schedule_id: str, *, limit: int = 50) -> list[ScheduleOccurrenceRecord]:
        async with self._session_factory() as session:
            statement = (
                select(ScheduleOccurrenceRecord)
                .where(ScheduleOccurrenceRecord.tenant_id == tenant_id,
                       ScheduleOccurrenceRecord.schedule_id == schedule_id)
                .order_by(ScheduleOccurrenceRecord.scheduled_at.desc())
                .limit(limit)
            )
            return list((await session.exec(statement)).all())

    # ---- delivery ----

    async def record_delivery_attempt(self, tenant_id: str, occurrence_id: str, destination: str,
                                      *, delivered: bool, error: str | None = None,
                                      provider_message_id: str | None = None) -> DeliveryAttemptRecord:
        async with self._session_factory() as session, session.begin():
            existing = (await session.exec(
                select(DeliveryAttemptRecord).where(
                    DeliveryAttemptRecord.tenant_id == tenant_id,
                    DeliveryAttemptRecord.occurrence_id == occurrence_id,
                    DeliveryAttemptRecord.destination == destination,
                )
            )).first()
            if existing is not None:
                existing.attempts += 1
                existing.status = "delivered" if delivered else "failed"
                existing.last_error = error
                existing.provider_message_id = provider_message_id or existing.provider_message_id
                session.add(existing)
                return existing
            record = DeliveryAttemptRecord(
                id=f"del_{uuid4().hex}", tenant_id=tenant_id, occurrence_id=occurrence_id,
                destination=destination, status="delivered" if delivered else "failed",
                attempts=1, last_error=error, provider_message_id=provider_message_id,
                created_at=datetime.now(UTC),
            )
            session.add(record)
            return record
