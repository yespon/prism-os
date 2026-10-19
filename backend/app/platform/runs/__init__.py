"""Tenant-scoped, idempotent run fact persistence with frozen snapshots."""

from datetime import UTC, datetime

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.governance import PlatformRunFactRecord
from app.platform.contracts import (
    RUN_COMPLETED,
    RUN_FAILED,
    RunFact,
    run_fact_from_envelope,
)
from app.platform.contracts.execution import ExecutionEnvelope
from deerflow.database.session import get_session_factory


def _ensure_utc(value: datetime | None) -> datetime | None:
    """SQLite returns naive datetimes; contracts require timezone-aware ones."""
    if value is None or value.tzinfo is not None:
        return value
    return value.replace(tzinfo=UTC)


class RunFactRepository:
    """Records durable run facts.

    Rules (R1-A):
    - Recording the same (tenant, run_id) twice is idempotent and must not
      mutate the frozen snapshot or timestamps of the first record.
    - A re-record with a *different* payload for the same run_id is refused:
      the fact is the source of truth once written.
    - Completion updates state/finished_at only; the snapshot is immutable.
    """

    def __init__(self, session_factory: async_sessionmaker[AsyncSession] | None = None) -> None:
        self._session_factory = session_factory or get_session_factory()

    @staticmethod
    def _record(fact: RunFact) -> PlatformRunFactRecord:
        return PlatformRunFactRecord(
            run_id=fact.run_id,
            tenant_id=fact.tenant_id,
            task_id=fact.task_id,
            correlation_id=fact.correlation_id,
            thread_id=fact.thread_id,
            workload_id=fact.workload.id,
            actor_id=fact.actor.id if fact.actor else None,
            state=fact.state,
            snapshot_json=fact.snapshot.model_dump_json(),
            started_at=fact.started_at,
            finished_at=fact.finished_at,
        )

    @staticmethod
    def _fact(row: PlatformRunFactRecord) -> RunFact:
        from app.platform.contracts import ExecutionSnapshot, IdentityRef

        snapshot = ExecutionSnapshot.model_validate_json(row.snapshot_json)
        return RunFact(
            tenant_id=row.tenant_id,
            run_id=row.run_id,
            task_id=row.task_id,
            correlation_id=row.correlation_id,
            thread_id=row.thread_id,
            workload=IdentityRef(kind="workload", id=row.workload_id, tenant_id=row.tenant_id),
            actor=IdentityRef(kind="user", id=row.actor_id, tenant_id=row.tenant_id)
            if row.actor_id
            else None,
            state=row.state,
            snapshot=snapshot,
            started_at=_ensure_utc(row.started_at) or row.started_at,
            finished_at=_ensure_utc(row.finished_at),
        )

    @staticmethod
    def _assert_same(row: PlatformRunFactRecord, fact: RunFact) -> None:
        same = (
            row.tenant_id == fact.tenant_id
            and row.task_id == fact.task_id
            and row.correlation_id == fact.correlation_id
            and row.thread_id == fact.thread_id
            and row.workload_id == fact.workload.id
            and row.actor_id == (fact.actor.id if fact.actor else None)
            and row.snapshot_json == fact.snapshot.model_dump_json()
        )
        if not same:
            raise ValueError("run_id already exists with a different payload")

    async def record(self, fact: RunFact) -> None:
        async with self._session_factory() as session:
            existing = await session.get(PlatformRunFactRecord, fact.run_id)
            if existing is not None:
                self._assert_same(existing, fact)
                return
            session.add(self._record(fact))
            try:
                await session.commit()
            except IntegrityError:
                await session.rollback()
                existing = await session.get(PlatformRunFactRecord, fact.run_id)
                if existing is not None:
                    self._assert_same(existing, fact)
                    return
                raise

    async def record_from_envelope(
        self,
        envelope: ExecutionEnvelope,
        snapshot=None,
    ) -> RunFact:
        from app.platform.contracts import ExecutionSnapshot

        fact = run_fact_from_envelope(
            envelope, snapshot if snapshot is not None else ExecutionSnapshot()
        )
        await self.record(fact)
        return fact

    async def get(self, tenant_id: str, run_id: str) -> RunFact | None:
        async with self._session_factory() as session:
            row = await session.get(PlatformRunFactRecord, run_id)
            if row is None or row.tenant_id != tenant_id:
                return None
            return self._fact(row)

    async def complete(self, tenant_id: str, run_id: str, *, failed: bool = False) -> RunFact:
        async with self._session_factory() as session:
            row = await session.get(PlatformRunFactRecord, run_id)
            if row is None or row.tenant_id != tenant_id:
                raise KeyError("run fact not found for tenant")
            if row.state not in ("created",):
                # Terminal states are immutable; idempotent re-complete is a no-op.
                return self._fact(row)
            row.state = RUN_FAILED if failed else RUN_COMPLETED
            row.finished_at = datetime.now(UTC)
            session.add(row)
            await session.commit()
            return self._fact(row)

    async def by_thread(self, tenant_id: str, thread_id: str) -> list[RunFact]:
        async with self._session_factory() as session:
            statement = (
                select(PlatformRunFactRecord)
                .where(
                    PlatformRunFactRecord.tenant_id == tenant_id,
                    PlatformRunFactRecord.thread_id == thread_id,
                )
                .order_by(PlatformRunFactRecord.started_at)
            )
            return [self._fact(row) for row in (await session.exec(statement)).all()]
