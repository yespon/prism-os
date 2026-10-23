"""R5 versioning service contracts."""

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models import governance as _g  # noqa: F401
from app.models import versioning as _v  # noqa: F401
from app.versioning import VersioningError, VersioningService, snapshot_hash


class _FakeAgent:
    def __init__(self, tenant_id="t1", agent_id="agent-1", prompt="v1 prompt"):
        self.tenant_id = tenant_id
        self.id = agent_id
        self.name = "assistant"
        self.description = ""
        self.model = "m"
        self.tool_groups = []
        self.system_prompt = prompt
        self.skills = []
        self.tags = []
        self.meta_info = {}
        self.created_by = "user-1"


@pytest.fixture
async def service(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'versioning.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(SQLModel.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    yield VersioningService(factory)
    await engine.dispose()


@pytest.mark.anyio
async def test_publish_freezes_and_dedupes(service):
    agent = _FakeAgent()
    v1 = await service.publish(agent, notes="first")
    assert v1.version_no == 1 and v1.version_hash == snapshot_hash(agent)

    # Same config republish is refused (identical hash).
    with pytest.raises(VersioningError):
        await service.publish(agent)

    agent.system_prompt = "v2 prompt"
    v2 = await service.publish(agent)
    assert v2.version_no == 2 and v2.version_hash != v1.version_hash
    # v1 is frozen: its stored snapshot still carries the old prompt.
    stored_v1 = await service.get_version("t1", v1.id)
    assert "v1 prompt" in stored_v1.config_json


@pytest.mark.anyio
async def test_deploy_rollback_cycle(service):
    agent = _FakeAgent()
    v1 = await service.publish(agent)
    d1 = await service.deploy("t1", agent.id, v1.id, deployed_by="admin-1")
    assert d1.version_id == v1.id and d1.previous_version_id is None

    agent.system_prompt = "v2 prompt"
    v2 = await service.publish(agent)
    d2 = await service.deploy("t1", agent.id, v2.id, deployed_by="admin-1")
    assert d2.previous_version_id == v1.id

    with pytest.raises(VersioningError):
        await service.deploy("t1", agent.id, v2.id, deployed_by="admin-1")  # already deployed

    rolled = await service.rollback("t1", agent.id, deployed_by="admin-1")
    assert rolled.version_id == v1.id
    with pytest.raises(VersioningError):
        await service.rollback("t1", agent.id, deployed_by="admin-1")  # no previous below v1

    # History intact: both versions remain listed for run-resolution.
    versions = await service.list_versions("t1", agent.id)
    assert [v.version_no for v in versions] == [1, 2]


@pytest.mark.anyio
async def test_deploy_refuses_foreign_version(service):
    agent = _FakeAgent(tenant_id="t1", agent_id="agent-1")
    other = _FakeAgent(tenant_id="t2", agent_id="agent-2")
    v_other = await service.publish(other)
    with pytest.raises(VersioningError):
        await service.deploy("t1", agent.id, v_other.id, deployed_by="admin-1")
