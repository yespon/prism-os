"""Task/Run lifecycle service (R5, M2 minimal).

State machines:
- task: pending -> running -> succeeded | failed | cancelled
- attempt: started -> succeeded | failed | cancelled | unknown

Unknown attempts never auto-resolve: a human resolves them to succeeded
or failed (resolved_by records who). Cancellation propagates from task
to its running attempts.
"""

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.lifecycle import PlatformRunAttemptRecord, PlatformTaskRecord
from deerflow.database.session import get_session_factory

TASK_TERMINAL = frozenset({"succeeded", "failed", "cancelled"})
ATTEMPT_TERMINAL = frozenset({"succeeded", "failed", "cancelled", "unknown"})


class LifecycleError(Exception):
    """Domain error with a user-presentable message."""


class LifecycleService:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession] | None = None) -> None:
        self._session_factory = session_factory or get_session_factory()

    async def create_task(self, tenant_id: str, created_by: str, *, title: str | None = None) -> PlatformTaskRecord:
        record = PlatformTaskRecord(
            id=f"task_{uuid4().hex}", tenant_id=tenant_id, created_by=created_by,
            title=title, state="pending", created_at=datetime.now(UTC),
        )
        async with self._session_factory() as session, session.begin():
            session.add(record)
        return record

    async def start_run(self, tenant_id: str, task_id: str) -> tuple[PlatformRunAttemptRecord, PlatformTaskRecord]:
        """Start the next attempt of a task's run; moves a pending task to running."""
        async with self._session_factory() as session, session.begin():
            task = await session.get(PlatformTaskRecord, task_id)
            if task is None or task.tenant_id != tenant_id:
                raise LifecycleError("task not found")
            if task.state in ("succeeded", "cancelled"):
                raise LifecycleError("task is terminal; start a new task instead")
            # A failed task may retry: start_run reopens it as running.
            prior = (await session.exec(
                select(PlatformRunAttemptRecord).where(
                    PlatformRunAttemptRecord.tenant_id == tenant_id,
                    PlatformRunAttemptRecord.task_id == task_id,
                )
            )).all()
            attempt_no = max((row.attempt_no for row in prior), default=0) + 1
            task.state = "running"
            session.add(task)
            attempt = PlatformRunAttemptRecord(
                id=f"att_{uuid4().hex}", tenant_id=tenant_id, task_id=task_id,
                run_id=f"run_{uuid4().hex}", attempt_no=attempt_no,
                state="started", started_at=datetime.now(UTC),
            )
            session.add(attempt)
        return attempt, task

    async def finish_attempt(self, tenant_id: str, attempt_id: str, *, succeeded: bool, error: str | None = None) -> PlatformRunAttemptRecord:
        """Finish an attempt; the task follows its last attempt's outcome."""
        async with self._session_factory() as session, session.begin():
            attempt = await session.get(PlatformRunAttemptRecord, attempt_id)
            if attempt is None or attempt.tenant_id != tenant_id:
                raise LifecycleError("attempt not found")
            if attempt.state in ATTEMPT_TERMINAL:
                raise LifecycleError("attempt already terminal")
            attempt.state = "succeeded" if succeeded else "failed"
            attempt.error = error
            attempt.finished_at = datetime.now(UTC)
            session.add(attempt)
            task = await session.get(PlatformTaskRecord, attempt.task_id)
            remaining = (await session.exec(
                select(PlatformRunAttemptRecord).where(
                    PlatformRunAttemptRecord.tenant_id == tenant_id,
                    PlatformRunAttemptRecord.task_id == attempt.task_id,
                    PlatformRunAttemptRecord.state == "started",
                )
            )).all()
            if task is not None and not remaining and task.state == "running":
                task.state = attempt.state if succeeded is False else "succeeded"
                if not succeeded:
                    task.state = "failed"
                task.finished_at = attempt.finished_at
                session.add(task)
        return attempt

    async def mark_unknown(self, tenant_id: str, attempt_id: str, error: str | None = None) -> PlatformRunAttemptRecord:
        """Mark an attempt unknown (e.g. process died mid-run); needs manual resolve."""
        async with self._session_factory() as session, session.begin():
            attempt = await session.get(PlatformRunAttemptRecord, attempt_id)
            if attempt is None or attempt.tenant_id != tenant_id:
                raise LifecycleError("attempt not found")
            if attempt.state in ATTEMPT_TERMINAL and attempt.state != "unknown":
                raise LifecycleError("attempt already terminal")
            attempt.state = "unknown"
            attempt.error = error
            attempt.finished_at = datetime.now(UTC)
            session.add(attempt)
        return attempt

    async def resolve_unknown(self, tenant_id: str, attempt_id: str, *, succeeded: bool, resolved_by: str) -> PlatformRunAttemptRecord:
        """A human resolves an unknown attempt; never automated."""
        async with self._session_factory() as session, session.begin():
            attempt = await session.get(PlatformRunAttemptRecord, attempt_id)
            if attempt is None or attempt.tenant_id != tenant_id:
                raise LifecycleError("attempt not found")
            if attempt.state != "unknown":
                raise LifecycleError("only unknown attempts can be resolved")
            attempt.state = "succeeded" if succeeded else "failed"
            attempt.resolved_by = resolved_by
            session.add(attempt)
        return attempt

    async def cancel_task(self, tenant_id: str, task_id: str, cancelled_by: str) -> PlatformTaskRecord:
        """Cancel a task; propagation reaches every started attempt."""
        async with self._session_factory() as session, session.begin():
            task = await session.get(PlatformTaskRecord, task_id)
            if task is None or task.tenant_id != tenant_id:
                raise LifecycleError("task not found")
            if task.state in TASK_TERMINAL:
                raise LifecycleError("task already terminal")
            task.state = "cancelled"
            task.finished_at = datetime.now(UTC)
            session.add(task)
            started = (await session.exec(
                select(PlatformRunAttemptRecord).where(
                    PlatformRunAttemptRecord.tenant_id == tenant_id,
                    PlatformRunAttemptRecord.task_id == task_id,
                    PlatformRunAttemptRecord.state == "started",
                )
            )).all()
            for attempt in started:
                attempt.state = "cancelled"
                attempt.finished_at = task.finished_at
                attempt.resolved_by = cancelled_by
                session.add(attempt)
        return task

    async def get_task(self, tenant_id: str, task_id: str) -> PlatformTaskRecord:
        async with self._session_factory() as session:
            task = await session.get(PlatformTaskRecord, task_id)
            if task is None or task.tenant_id != tenant_id:
                raise LifecycleError("task not found")
            return task

    async def list_attempts(self, tenant_id: str, task_id: str) -> list[PlatformRunAttemptRecord]:
        async with self._session_factory() as session:
            return list((await session.exec(
                select(PlatformRunAttemptRecord)
                .where(PlatformRunAttemptRecord.tenant_id == tenant_id,
                       PlatformRunAttemptRecord.task_id == task_id)
                .order_by(PlatformRunAttemptRecord.attempt_no)
            )).all())
