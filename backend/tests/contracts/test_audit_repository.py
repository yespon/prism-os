from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.governance import PlatformAuditEventRecord  # noqa: F401
from app.platform.audit.repository import AuditEventRepository
from app.platform.contracts import AuditEvent, ExecutionEnvelope, IdentityRef


@pytest.fixture
async def audit_repository(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'audit.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(SQLModel.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    yield AuditEventRepository(factory)
    await engine.dispose()


def _event(event_id: str = "event_0123456789abcdef0123456789abcdef") -> AuditEvent:
    execution = ExecutionEnvelope(
        tenant_id="tenant-a",
        task_id="task_0123456789abcdef0123456789abcdef",
        run_id="run_0123456789abcdef0123456789abcdef",
        correlation_id="correlation-7",
        workload=IdentityRef(kind="workload", id="agent-7", tenant_id="tenant-a"),
        occurred_at=datetime(2026, 8, 8, 8, 30, tzinfo=UTC),
    )
    return AuditEvent(
        tenant_id="tenant-a",
        event_id=event_id,
        event_type="action.completed",
        action="terminal.execute",
        outcome="succeeded",
        execution=execution,
        recorded_at=datetime(2026, 8, 8, 8, 31, tzinfo=UTC),
    )


@pytest.mark.anyio
async def test_repository_round_trips_event(audit_repository) -> None:
    await audit_repository.append(_event())
    restored = await audit_repository.get(
        "event_0123456789abcdef0123456789abcdef",
        tenant_id="tenant-a",
    )
    assert restored == _event()


@pytest.mark.anyio
async def test_repository_is_tenant_scoped_and_idempotent(audit_repository) -> None:
    event = _event()
    await audit_repository.append(event)
    await audit_repository.append(event)
    assert await audit_repository.get(event.event_id, tenant_id="tenant-b") is None
    assert len(await audit_repository.list_recent("tenant-a", limit=10)) == 1


@pytest.mark.anyio
async def test_repository_rejects_reused_event_id_with_different_payload(
    audit_repository,
) -> None:
    event = _event()
    await audit_repository.append(event)
    with pytest.raises(ValueError, match="different payload"):
        await audit_repository.append(event.model_copy(update={"outcome": "failed"}))
