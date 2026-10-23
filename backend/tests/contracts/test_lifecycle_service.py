"""R5 lifecycle service contracts."""

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from app.lifecycle import LifecycleError, LifecycleService
from app.models import lifecycle as _lifecycle_models  # noqa: F401


@pytest.fixture
async def service(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'lifecycle.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(SQLModel.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    yield LifecycleService(factory)
    await engine.dispose()


@pytest.mark.anyio
async def test_task_run_success_path(service):
    task = await service.create_task("t1", "user-1", title="nightly check")
    attempt, running = await service.start_run("t1", task.id)
    assert running.state == "running" and attempt.attempt_no == 1

    finished = await service.finish_attempt("t1", attempt.id, succeeded=True)
    assert finished.state == "succeeded"
    task_after = await service.get_task("t1", task.id)
    assert task_after.state == "succeeded" and task_after.finished_at is not None


@pytest.mark.anyio
async def test_retry_appends_new_attempt(service):
    task = await service.create_task("t1", "user-1")
    first, _ = await service.start_run("t1", task.id)
    await service.finish_attempt("t1", first.id, succeeded=False, error="timeout")

    second, running = await service.start_run("t1", task.id)
    assert second.attempt_no == 2 and second.id != first.id
    assert running.state == "running", "retry reopens the task"

    await service.finish_attempt("t1", second.id, succeeded=True)
    attempts = await service.list_attempts("t1", task.id)
    assert [a.state for a in attempts] == ["failed", "succeeded"]
    task_after = await service.get_task("t1", task.id)
    assert task_after.state == "succeeded"


@pytest.mark.anyio
async def test_unknown_never_auto_resolves(service):
    task = await service.create_task("t1", "user-1")
    attempt, _ = await service.start_run("t1", task.id)
    await service.mark_unknown("t1", attempt.id, error="process died")

    listed = await service.list_attempts("t1", task.id)
    assert listed[0].state == "unknown"

    # Re-finishing an unknown attempt is refused; only resolve_unknown moves it.
    with pytest.raises(LifecycleError):
        await service.finish_attempt("t1", attempt.id, succeeded=True)

    resolved = await service.resolve_unknown("t1", attempt.id, succeeded=False, resolved_by="admin-1")
    assert resolved.state == "failed" and resolved.resolved_by == "admin-1"


@pytest.mark.anyio
async def test_cancel_propagates_to_running_attempts(service):
    task = await service.create_task("t1", "user-1")
    attempt, _ = await service.start_run("t1", task.id)

    cancelled = await service.cancel_task("t1", task.id, cancelled_by="admin-1")
    assert cancelled.state == "cancelled"

    attempts = await service.list_attempts("t1", task.id)
    assert attempts[0].state == "cancelled" and attempts[0].resolved_by == "admin-1"

    # Terminal task refuses new runs and re-cancel.
    with pytest.raises(LifecycleError):
        await service.start_run("t1", task.id)
    with pytest.raises(LifecycleError):
        await service.cancel_task("t1", task.id, cancelled_by="admin-1")


@pytest.mark.anyio
async def test_cross_tenant_isolation(service):
    task = await service.create_task("t1", "user-1")
    with pytest.raises(LifecycleError):
        await service.get_task("t2", task.id)
    with pytest.raises(LifecycleError):
        await service.cancel_task("t2", task.id, cancelled_by="user-1")


@pytest.mark.anyio
async def test_attempt_adopts_platform_run_identity(service):
    """R5 linking: an attempt can adopt the governed run id so RunFact and
    lifecycle share one execution identity."""
    from app.platform.contracts import stable_platform_id

    task = await service.create_task("t1", "user-1")
    governed_run = stable_platform_id("run", "diagnosis", "thread-42")
    attempt, _ = await service.start_run("t1", task.id, run_id=governed_run)
    assert attempt.run_id == governed_run

    # The run id stays stable across retries (each attempt adopts it or a fresh one).
    await service.finish_attempt("t1", attempt.id, succeeded=False)
    second, _ = await service.start_run("t1", task.id)
    assert second.run_id != governed_run  # retry without explicit id gets a fresh identity
