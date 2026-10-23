from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.governance import PlatformAuditEventRecord
from app.platform.contracts import AuditEvent
from deerflow.database.session import get_session_factory


class AuditEventRepository:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession] | None = None,
    ) -> None:
        self._session_factory = session_factory or get_session_factory()

    @staticmethod
    def _record(event: AuditEvent) -> PlatformAuditEventRecord:
        return PlatformAuditEventRecord(
            id=event.event_id,
            schema_version=event.schema_version,
            tenant_id=event.tenant_id,
            event_type=event.event_type,
            action=event.action,
            outcome=event.outcome,
            severity=event.severity,
            task_id=event.task_id,
            run_id=event.run_id,
            correlation_id=event.execution.correlation_id,
            policy_decision_id=event.policy_decision_id,
            approval_id=event.approval_id,
            resource_id=event.resource_id,
            event_json=event.model_dump(mode="json"),
            occurred_at=event.execution.occurred_at,
            recorded_at=event.recorded_at,
        )

    @staticmethod
    def _assert_same_event(record: PlatformAuditEventRecord, event: AuditEvent) -> None:
        if record.event_json != event.model_dump(mode="json"):
            raise ValueError("event_id already exists with different payload")

    @classmethod
    async def append_in_session(cls, session: AsyncSession, event: AuditEvent) -> None:
        """Stage an event in the caller's transaction without committing it."""
        existing = await session.get(PlatformAuditEventRecord, event.event_id)
        if existing is not None:
            cls._assert_same_event(existing, event)
            return
        session.add(cls._record(event))

    async def append(self, event: AuditEvent) -> None:
        async with self._session_factory() as session:
            existing = await session.get(PlatformAuditEventRecord, event.event_id)
            if existing is not None:
                self._assert_same_event(existing, event)
                return
            session.add(self._record(event))
            try:
                await session.commit()
            except IntegrityError:
                await session.rollback()
                existing = await session.get(PlatformAuditEventRecord, event.event_id)
                if existing is None:
                    raise
                self._assert_same_event(existing, event)

    async def get(self, event_id: str, tenant_id: str) -> AuditEvent | None:
        async with self._session_factory() as session:
            statement = select(PlatformAuditEventRecord).where(
                PlatformAuditEventRecord.id == event_id,
                PlatformAuditEventRecord.tenant_id == tenant_id,
            )
            row = (await session.exec(statement)).one_or_none()
            return None if row is None else AuditEvent.model_validate(row.event_json)

    async def list_recent(self, tenant_id: str, limit: int = 100) -> list[AuditEvent]:
        if limit <= 0:
            return []
        async with self._session_factory() as session:
            statement = (
                select(PlatformAuditEventRecord)
                .where(PlatformAuditEventRecord.tenant_id == tenant_id)
                .order_by(PlatformAuditEventRecord.recorded_at.desc())
                .limit(min(limit, 1000))
            )
            rows = (await session.exec(statement)).all()
            return [AuditEvent.model_validate(row.event_json) for row in rows]
