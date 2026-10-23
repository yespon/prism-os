import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models import governance as _governance_models  # noqa: F401
from app.platform.execution.trust import (
    ExecutionCapabilityRepository,
    ExecutionTrustError,
    ThreadBindingRepository,
)

NOW = datetime(2026, 9, 25, 9, 0, tzinfo=UTC)


@pytest.fixture
async def trust_repositories(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'execution-trust.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(SQLModel.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    yield ThreadBindingRepository(factory), ExecutionCapabilityRepository(factory)
    await engine.dispose()


@pytest.mark.anyio
async def test_thread_owner_and_agent_are_immutable(trust_repositories) -> None:
    threads, _ = trust_repositories
    await threads.create("thread-1", "tenant-a", "user-1")
    with pytest.raises(ExecutionTrustError):
        await threads.get("thread-1", "tenant-b", "user-1")
    with pytest.raises(ExecutionTrustError):
        await threads.get("thread-1", "tenant-a", "user-2")
    bound = await threads.bind_agent("thread-1", "tenant-a", "user-1", "diagnosis")
    assert bound.agent_name == "diagnosis"
    with pytest.raises(ExecutionTrustError, match="cannot change"):
        await threads.bind_agent("thread-1", "tenant-a", "user-1", "other-agent")
    with pytest.raises(ExecutionTrustError):
        await threads.create("thread-1", "tenant-a", "user-2")


@pytest.mark.anyio
async def test_capability_rejects_forgery_replay_and_expiry(trust_repositories) -> None:
    _, capabilities = trust_repositories
    token = await capabilities.issue("tenant-a", "user-1", "thread-1", "diagnosis", at=NOW)
    with pytest.raises(ExecutionTrustError):
        await capabilities.consume(token, "tenant-b", "user-1", "thread-1", "diagnosis", at=NOW)
    with pytest.raises(ExecutionTrustError):
        await capabilities.consume(token, "tenant-a", "user-1", "thread-1", "other", at=NOW)
    with pytest.raises(ExecutionTrustError):
        await capabilities.consume("browser-supplied-context", "tenant-a", "user-1", "thread-1", "diagnosis", at=NOW)
    await capabilities.consume(token, "tenant-a", "user-1", "thread-1", "diagnosis", at=NOW)
    with pytest.raises(ExecutionTrustError, match="replay"):
        await capabilities.consume(token, "tenant-a", "user-1", "thread-1", "diagnosis", at=NOW)
    expired = await capabilities.issue("tenant-a", "user-1", "thread-1", None, at=NOW)
    with pytest.raises(ExecutionTrustError, match="expired"):
        await capabilities.consume(expired, "tenant-a", "user-1", "thread-1", None, at=NOW + timedelta(seconds=61))


@pytest.mark.anyio
async def test_capability_is_consumed_once_under_concurrency(trust_repositories) -> None:
    _, capabilities = trust_repositories
    token = await capabilities.issue("tenant-a", "user-1", "thread-1", None, at=NOW)
    results = await asyncio.gather(*(
        capabilities.consume(token, "tenant-a", "user-1", "thread-1", None, at=NOW)
        for _ in range(2)
    ), return_exceptions=True)
    assert sum(result is None for result in results) == 1
    assert sum(isinstance(result, ExecutionTrustError) for result in results) == 1

@pytest.mark.anyio
async def test_server_scoped_capability_carries_incident_only_once(trust_repositories) -> None:
    _, capabilities = trust_repositories
    token = await capabilities.issue("tenant-a", "user-1", "thread-1", "diagnosis",
                                     action_incident_id="incident-1", at=NOW)
    assert await capabilities.consume(token, "tenant-a", "user-1", "thread-1", "diagnosis", at=NOW) == "incident-1"
    with pytest.raises(ExecutionTrustError, match="replay"):
        await capabilities.consume(token, "tenant-a", "user-1", "thread-1", "diagnosis", at=NOW)
