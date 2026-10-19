"""R1-A run fact contracts: durable, idempotent, snapshot-frozen."""

from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models import governance as _governance_models  # noqa: F401
from app.platform.contracts import (
    RUN_COMPLETED,
    RUN_CREATED,
    RUN_FAILED,
    ExecutionEnvelope,
    ExecutionSnapshot,
    IdentityRef,
    RunFact,
    run_fact_from_envelope,
)
from app.platform.runs import RunFactRepository

NOW = datetime(2026, 10, 19, 10, 0, tzinfo=UTC)


@pytest.fixture
async def repository(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'run-facts.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(SQLModel.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    yield RunFactRepository(factory)
    await engine.dispose()


def _envelope(run_id="run-1", agent="diagnosis-agent:default", model="gpt-5.6-luna") -> ExecutionEnvelope:
    return ExecutionEnvelope(
        tenant_id="tenant-a",
        task_id=f"task-for-{run_id}",
        run_id=run_id,
        correlation_id="incident-1",
        workload=IdentityRef(kind="workload", id=agent, tenant_id="tenant-a"),
        actor=IdentityRef(kind="user", id="user-1", tenant_id="tenant-a"),
        occurred_at=NOW,
        attributes={"thread_id": "thread-1", "model_name": model},
    )


def test_run_fact_projection_from_envelope():
    fact = run_fact_from_envelope(
        _envelope(),
        ExecutionSnapshot(agent_name="default", model_name="gpt-5.6-luna", source="diagnosis"),
    )
    assert fact.run_id == "run-1"
    assert fact.state == RUN_CREATED
    assert fact.thread_id == "thread-1"
    assert fact.snapshot.model_name == "gpt-5.6-luna"


def test_run_fact_rejects_cross_tenant_reference():
    with pytest.raises(ValueError):
        RunFact(
            tenant_id="tenant-a",
            run_id="run-x",
            task_id="task-x",
            workload=IdentityRef(kind="workload", id="agent-1", tenant_id="tenant-b"),
            started_at=NOW,
        )


@pytest.mark.anyio
async def test_record_is_idempotent_and_freezes_snapshot(repository):
    fact = run_fact_from_envelope(_envelope(), ExecutionSnapshot(model_name="gpt-5.6-luna"))
    await repository.record(fact)

    # Same run recorded again: no error, snapshot untouched.
    await repository.record(fact)

    stored = await repository.get("tenant-a", "run-1")
    assert stored is not None
    assert stored.snapshot.model_name == "gpt-5.6-luna"
    assert stored.state == RUN_CREATED

    # Same run_id with a different payload is refused.
    mutated = run_fact_from_envelope(_envelope(), ExecutionSnapshot(model_name="other-model"))
    with pytest.raises(ValueError):
        await repository.record(mutated)


@pytest.mark.anyio
async def test_complete_is_idempotent_and_snapshot_immutable(repository):
    await repository.record(run_fact_from_envelope(_envelope()))
    completed = await repository.complete("tenant-a", "run-1")
    assert completed.state == RUN_COMPLETED
    assert completed.finished_at is not None

    # Re-complete is a no-op, not an error or timestamp drift.
    again = await repository.complete("tenant-a", "run-1")
    assert again.finished_at == completed.finished_at

    # Failure path from a fresh run.
    await repository.record(run_fact_from_envelope(_envelope(run_id="run-2")))
    failed = await repository.complete("tenant-a", "run-2", failed=True)
    assert failed.state == RUN_FAILED


@pytest.mark.anyio
async def test_tenant_isolation_on_read(repository):
    await repository.record(run_fact_from_envelope(_envelope()))
    assert await repository.get("tenant-b", "run-1") is None
    with pytest.raises(KeyError):
        await repository.complete("tenant-b", "run-1")


@pytest.mark.anyio
async def test_by_thread_scopes_tenant(repository):
    await repository.record(run_fact_from_envelope(_envelope(run_id="run-1")))
    await repository.record(run_fact_from_envelope(_envelope(run_id="run-2")))
    facts = await repository.by_thread("tenant-a", "thread-1")
    assert [fact.run_id for fact in facts] == ["run-1", "run-2"]
    assert await repository.by_thread("tenant-b", "thread-1") == []


@pytest.mark.anyio
async def test_record_from_envelope_helper(repository):
    fact = await repository.record_from_envelope(
        _envelope(run_id="run-9"),
        ExecutionSnapshot(agent_name="default", model_name="gpt-5.6-luna"),
    )
    assert fact.run_id == "run-9"
    stored = await repository.get("tenant-a", "run-9")
    assert stored.snapshot.agent_name == "default"
