"""R3 scheduling service contracts: idempotency, ownership, delivery."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models import governance as _governance_models  # noqa: F401
from app.models import scheduling as _scheduling_models  # noqa: F401
from app.scheduling import ScheduleService, SchedulingError, occurrence_idempotency_key

SLOT = datetime(2026, 10, 19, 12, 0, tzinfo=UTC)


@pytest.fixture
async def service(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'scheduling.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(SQLModel.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    yield ScheduleService(factory)
    await engine.dispose()


async def _definition(service, tenant="t1", owner="owner-1"):
    return await service.create_definition(
        tenant, owner, name="nightly check", trigger_kind="cron", cron_expr="0 3 * * *",
        agent_name="default", prompt="Run the nightly health check and summarize.",
    )


@pytest.mark.anyio
async def test_definition_validation(service):
    with pytest.raises(SchedulingError):
        await service.create_definition("t1", "u1", name="x", trigger_kind="weekly", agent_name="a", prompt="p")
    with pytest.raises(SchedulingError):
        await service.create_definition("t1", "u1", name="x", trigger_kind="cron", agent_name="a", prompt="p")
    with pytest.raises(SchedulingError):
        await service.create_definition("t1", "u1", name="x", trigger_kind="date", agent_name="a", prompt="p")
    created = await _definition(service)
    assert created.trigger_kind == "cron" and created.enabled


@pytest.mark.anyio
async def test_occurrence_claim_is_idempotent(service):
    await _definition(service)
    # First claim creates; the replay of the same slot returns existing, created=False.
    occurrence, created = await service.claim_occurrence("t1", "sched-x", SLOT)
    assert created is True
    replay, created_again = await service.claim_occurrence("t1", "sched-x", SLOT)
    assert created_again is False and replay.id == occurrence.id
    # run-now for the same slot collides through the same key.
    run_now, created_now = await service.claim_occurrence("t1", "sched-x", SLOT)
    assert created_now is False and run_now.id == occurrence.id
    # A different slot claims fresh.
    other, created_other = await service.claim_occurrence("t1", "sched-x", SLOT + timedelta(minutes=1))
    assert created_other is True and other.id != occurrence.id


@pytest.mark.anyio
async def test_cross_tenant_occurrences_are_independent(service):
    await service.claim_occurrence("t1", "sched-x", SLOT)
    occurrence_b, created_b = await service.claim_occurrence("t2", "sched-x", SLOT)
    assert created_b is True  # same key text, different tenant


@pytest.mark.anyio
async def test_occurrence_state_machine(service):
    occurrence, _ = await service.claim_occurrence("t1", "sched-x", SLOT)
    await service.mark_running("t1", occurrence.id, "run_123")
    await service.mark_finished("t1", occurrence.id)
    listed = await service.list_occurrences("t1", "sched-x")
    assert listed[0].state == "completed" and listed[0].run_id == "run_123"
    with pytest.raises(SchedulingError):
        await service.mark_running("t2", occurrence.id, "run_x")  # cross-tenant refused


@pytest.mark.anyio
async def test_delivery_retry_increments_without_new_row(service):
    occurrence, _ = await service.claim_occurrence("t1", "sched-x", SLOT)
    first = await service.record_delivery_attempt("t1", occurrence.id, "web:thread-1", delivered=False, error="timeout")
    second = await service.record_delivery_attempt("t1", occurrence.id, "web:thread-1", delivered=True, provider_message_id="m-1")
    assert first.id == second.id
    assert second.attempts == 2 and second.status == "delivered"
    # Occurrence state untouched by delivery retries.
    assert (await service.list_occurrences("t1", "sched-x"))[0].state == "pending"


@pytest.mark.anyio
async def test_definition_ownership(service):
    created = await _definition(service)
    with pytest.raises(SchedulingError):
        await service.set_enabled("t1", created.id, "stranger", False)
    with pytest.raises(SchedulingError):
        await service.delete_definition("t1", created.id, "stranger")
    with pytest.raises(SchedulingError):
        await service.set_enabled("t2", created.id, "owner-1", False)
    await service.set_enabled("t1", created.id, "owner-1", False)
    assert (await service.list_definitions("t1", enabled_only=True)) == []


def test_idempotency_key_shape():
    key = occurrence_idempotency_key("t1", "sched-x", SLOT)
    assert key.startswith("sched-x:20261019T1200")
    # Same instant expressed in another timezone produces the same key.
    from zoneinfo import ZoneInfo

    shanghai = SLOT.astimezone(ZoneInfo("Asia/Shanghai"))
    assert occurrence_idempotency_key("t1", "sched-x", shanghai) == key
