"""R3 cron worker contracts: boot recovery and exactly-once triggers."""

from datetime import UTC, datetime

import pytest
from apscheduler.triggers.date import DateTrigger
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models import scheduling as _scheduling_models  # noqa: F401
from app.scheduling import ScheduleService
from app.scheduling.worker import CronWorker


@pytest.fixture
async def env(tmp_path, monkeypatch):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'worker.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(SQLModel.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    from deerflow.database import session as session_module

    monkeypatch.setattr(session_module, "get_session_factory", lambda: factory)
    service = ScheduleService(factory)
    yield service, factory
    await engine.dispose()


@pytest.mark.anyio
async def test_boot_recovers_enabled_definitions(env):
    service, _factory = env
    kept = await service.create_definition("t1", "owner-1", name="kept", trigger_kind="cron",
                                          cron_expr="0 3 * * *", agent_name="default", prompt="nightly")
    await service.create_definition("t1", "owner-1", name="disabled", trigger_kind="cron",
                                    cron_expr="0 4 * * *", agent_name="default", prompt="other")
    await service.set_enabled("t1", (await service.list_definitions("t1"))[-1].id, "owner-1", False)

    worker = CronWorker(service)
    count = await worker.boot()
    try:
        assert count == 1
        job = worker._scheduler.get_job(kept.id)
        assert job is not None
        disabled_job = worker._scheduler.get_job((await service.list_definitions("t1"))[-1].id)
        assert disabled_job is None
    finally:
        await worker.shutdown()


@pytest.mark.anyio
async def test_fire_claims_once_and_marks_finished(env):
    service, _factory = env
    definition = await service.create_definition("t1", "owner-1", name="manual", trigger_kind="date",
                                                 run_at=datetime.now(UTC), agent_name="default", prompt="once")
    worker = CronWorker(service)

    # First fire claims and completes; second fire for the same slot is a no-op.
    await worker._fire("t1", definition.id)
    await worker._fire("t1", definition.id)

    occurrences = await service.list_occurrences("t1", definition.id)
    assert len(occurrences) == 1
    assert occurrences[0].state == "completed"


@pytest.mark.anyio
async def test_date_trigger_registration(env):
    service, _factory = env
    run_at = datetime(2030, 1, 1, 0, 0, tzinfo=UTC)
    definition = await service.create_definition("t1", "owner-1", name="future", trigger_kind="date",
                                                 run_at=run_at, agent_name="default", prompt="future")
    worker = CronWorker(service)
    count = await worker.boot()
    try:
        assert count == 1
        job = worker._scheduler.get_job(definition.id)
        assert job is not None and isinstance(job.trigger, DateTrigger)
    finally:
        await worker.shutdown()


@pytest.mark.anyio
async def test_fire_with_execute_callback_records_run_and_delivery(env):
    service, _factory = env
    definition = await service.create_definition("t1", "owner-1", name="wired", trigger_kind="date",
                                                 run_at=datetime.now(UTC), agent_name="default", prompt="once")
    executed: list[tuple] = []

    async def execute(tenant_id, definition_arg, occurrence_arg):
        executed.append((tenant_id, definition_arg.id, occurrence_arg.id))
        return "run_scheduled_1"

    worker = CronWorker(service, execute=execute)
    await worker._fire("t1", definition.id)

    occurrences = await service.list_occurrences("t1", definition.id)
    assert len(occurrences) == 1
    occurrence = occurrences[0]
    assert occurrence.state == "completed" and occurrence.run_id == "run_scheduled_1"
    assert executed == [("t1", definition.id, occurrence.id)]

    records = await service.list_delivery_attempts("t1", occurrence.id)
    assert records and records[0].status == "delivered" and records[0].provider_message_id == "run_scheduled_1"


@pytest.mark.anyio
async def test_fire_execute_failure_marks_failed_and_records_delivery_error(env):
    service, _factory = env
    definition = await service.create_definition("t1", "owner-1", name="broken", trigger_kind="date",
                                                 run_at=datetime.now(UTC), agent_name="default", prompt="once")

    async def execute(tenant_id, definition_arg, occurrence_arg):
        raise RuntimeError("backend down")

    worker = CronWorker(service, execute=execute)
    await worker._fire("t1", definition.id)  # must not raise

    occurrences = await service.list_occurrences("t1", definition.id)
    assert occurrences[0].state == "failed"
    records = await service.list_delivery_attempts("t1", occurrences[0].id)
    assert records and records[0].status == "failed" and records[0].last_error == "execution_failed"
