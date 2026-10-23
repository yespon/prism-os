"""R5 evaluation gate contracts."""

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from app.evaluation import EvaluationError, EvaluationService
from app.models import evaluation as _e  # noqa: F401
from app.models import versioning as _v  # noqa: F401


class _FakeAgent:
    def __init__(self, tenant_id="t1", agent_id="agent-1"):
        self.tenant_id = tenant_id
        self.id = agent_id
        self.name = "assistant"
        self.description = ""
        self.model = "m"
        self.tool_groups = []
        self.system_prompt = "prompt"
        self.skills = []
        self.tags = []
        self.meta_info = {}
        self.created_by = "user-1"


@pytest.fixture
async def env(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'eval.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(SQLModel.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    from app.versioning import VersioningService

    yield VersioningService(factory), EvaluationService(factory)
    await engine.dispose()


@pytest.mark.anyio
async def test_gate_requires_evaluation_before_deploy(env):
    versioning, evaluation = env
    version = await versioning.publish(_FakeAgent())
    with pytest.raises(EvaluationError, match="no evaluation"):
        await evaluation.enforce_gate("t1", version.id)


@pytest.mark.anyio
async def test_gate_rejects_low_score_and_allows_pass(env):
    versioning, evaluation = env
    version = await versioning.publish(_FakeAgent())

    low = await evaluation.record("t1", version.id, dataset="golden-aiops", score=0.5)
    assert low.passed is False
    with pytest.raises(EvaluationError, match="gate failed"):
        await evaluation.enforce_gate("t1", version.id)

    high = await evaluation.record("t1", version.id, dataset="golden-aiops", score=0.9)
    assert high.passed is True
    passed = await evaluation.enforce_gate("t1", version.id)
    assert passed.score == 0.9  # latest evaluation wins


@pytest.mark.anyio
async def test_score_validation_and_tenant_isolation(env):
    versioning, evaluation = env
    version = await versioning.publish(_FakeAgent())
    with pytest.raises(EvaluationError):
        await evaluation.record("t1", version.id, dataset="x", score=1.5)
    with pytest.raises(EvaluationError):
        await evaluation.record("t2", version.id, dataset="x", score=0.9)
    assert await evaluation.latest("t2", version.id) is None
