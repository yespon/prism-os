"""Evaluation gates for agent version deployment (R5, M3 minimal).

An evaluation record captures a scored run of a version against a
dataset fixture. Deployment requires a passing gate: a version whose
latest evaluation is below the tenant's threshold cannot deploy. The
gate is advisory-with-teeth in this slice: it is enforced by the
deploy path, not by a separate PDP.
"""

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.versioning import AgentVersionRecord
from deerflow.database.session import get_session_factory

DEFAULT_THRESHOLD = 0.8


class EvaluationError(Exception):
    """Domain error with a user-presentable message."""


class EvaluationRecord:
    """A stored evaluation result (persisted by the service)."""

    def __init__(self, *, evaluation_id: str, tenant_id: str, version_id: str, dataset: str,
                 score: float, passed: bool, details_json: str, created_at: datetime):
        self.evaluation_id = evaluation_id
        self.tenant_id = tenant_id
        self.version_id = version_id
        self.dataset = dataset
        self.score = score
        self.passed = passed
        self.details_json = details_json
        self.created_at = created_at


class EvaluationService:
    """Records evaluations and enforces the pre-deployment gate."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession] | None = None,
                 threshold: float = DEFAULT_THRESHOLD) -> None:
        self._session_factory = session_factory or get_session_factory()
        self._threshold = threshold

    async def record(self, tenant_id: str, version_id: str, *, dataset: str,
                     score: float, details: dict | None = None) -> EvaluationRecord:
        """Record a scored evaluation for a version."""
        async with self._session_factory() as session:
            version = await session.get(AgentVersionRecord, version_id)
            if version is None or version.tenant_id != tenant_id:
                raise EvaluationError("version not found")
        if not 0.0 <= score <= 1.0:
            raise EvaluationError("score must be within [0, 1]")
        record = EvaluationRecord(
            evaluation_id=f"eval_{uuid4().hex}", tenant_id=tenant_id, version_id=version_id,
            dataset=dataset, score=score, passed=score >= self._threshold,
            details_json=_dump(details or {}), created_at=datetime.now(UTC),
        )
        from app.models.evaluation import EvaluationResultRecord

        async with self._session_factory() as session, session.begin():
            session.add(EvaluationResultRecord(
                id=record.evaluation_id, tenant_id=tenant_id, version_id=version_id,
                dataset=dataset, score=score, passed=record.passed,
                details_json=record.details_json, created_at=record.created_at,
            ))
        return record

    async def latest(self, tenant_id: str, version_id: str) -> EvaluationRecord | None:
        from app.models.evaluation import EvaluationResultRecord

        async with self._session_factory() as session:
            row = (await session.exec(
                select(EvaluationResultRecord)
                .where(EvaluationResultRecord.tenant_id == tenant_id,
                       EvaluationResultRecord.version_id == version_id)
                .order_by(EvaluationResultRecord.created_at.desc())
                .limit(1)
            )).first()
        if row is None:
            return None
        return EvaluationRecord(
            evaluation_id=row.id, tenant_id=row.tenant_id, version_id=row.version_id,
            dataset=row.dataset, score=row.score, passed=row.passed,
            details_json=row.details_json, created_at=row.created_at,
        )

    async def enforce_gate(self, tenant_id: str, version_id: str) -> EvaluationRecord:
        """Refuse (raise) unless the version's latest evaluation passes.

        Gate rule: a version must have at least one evaluation and its
        latest must score at or above the threshold.
        """
        record = await self.latest(tenant_id, version_id)
        if record is None:
            raise EvaluationError("version has no evaluation; run an evaluation before deploying")
        if not record.passed:
            raise EvaluationError(
                f"evaluation gate failed: latest score {record.score:.2f} below threshold"
            )
        return record


def _dump(details: dict) -> str:
    from json import dumps

    return dumps(details, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
