"""Tenant-scoped, idempotent Policy Decision persistence."""

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.governance import PlatformPolicyDecisionRecord
from app.platform.contracts import PolicyDecision
from deerflow.database.session import get_session_factory


class PolicyDecisionRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession] | None = None) -> None:
        self._session_factory = session_factory or get_session_factory()

    @staticmethod
    def _record(decision: PolicyDecision) -> PlatformPolicyDecisionRecord:
        return PlatformPolicyDecisionRecord(
            id=decision.decision_id,
            tenant_id=decision.tenant_id,
            request_id=decision.request_id,
            run_id=decision.execution.run_id,
            verdict=decision.verdict,
            policy_id=decision.policy_id,
            policy_version=decision.policy_version,
            context_hash=decision.context_hash,
            decision_json=decision.model_dump(mode="json"),
            decided_at=decision.decided_at,
            expires_at=decision.expires_at,
        )

    @staticmethod
    def _assert_same(row: PlatformPolicyDecisionRecord, decision: PolicyDecision) -> None:
        if row.decision_json != decision.model_dump(mode="json"):
            raise ValueError("decision_id already exists with different payload")

    @staticmethod
    async def _by_request(session: AsyncSession, tenant_id: str, request_id: str) -> PlatformPolicyDecisionRecord | None:
        statement = select(PlatformPolicyDecisionRecord).where(
            PlatformPolicyDecisionRecord.tenant_id == tenant_id,
            PlatformPolicyDecisionRecord.request_id == request_id,
        )
        return (await session.exec(statement)).one_or_none()

    async def append(self, decision: PolicyDecision) -> None:
        async with self._session_factory() as session:
            existing = await session.get(PlatformPolicyDecisionRecord, decision.decision_id)
            if existing is not None:
                self._assert_same(existing, decision)
                return
            if await self._by_request(session, decision.tenant_id, decision.request_id) is not None:
                raise ValueError("request_id already has a Policy Decision")
            session.add(self._record(decision))
            try:
                await session.commit()
            except IntegrityError:
                await session.rollback()
                existing = await session.get(PlatformPolicyDecisionRecord, decision.decision_id)
                if existing is not None:
                    self._assert_same(existing, decision)
                    return
                if await self._by_request(session, decision.tenant_id, decision.request_id) is not None:
                    raise ValueError("request_id already has a Policy Decision") from None
                raise

    async def get(self, tenant_id: str, decision_id: str) -> PolicyDecision | None:
        async with self._session_factory() as session:
            statement = select(PlatformPolicyDecisionRecord).where(
                PlatformPolicyDecisionRecord.tenant_id == tenant_id,
                PlatformPolicyDecisionRecord.id == decision_id,
            )
            row = (await session.exec(statement)).one_or_none()
            return None if row is None else PolicyDecision.model_validate(row.decision_json)

    async def get_by_request(self, tenant_id: str, request_id: str) -> PolicyDecision | None:
        async with self._session_factory() as session:
            row = await self._by_request(session, tenant_id, request_id)
            return None if row is None else PolicyDecision.model_validate(row.decision_json)
