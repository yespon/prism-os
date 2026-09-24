"""Tenant-scoped Approval facts with compare-and-swap state updates."""

from sqlalchemy import update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.governance import PlatformApprovalRecord, PlatformPolicyDecisionRecord
from app.platform.contracts import Approval, PolicyDecision
from deerflow.database.session import get_session_factory


class ApprovalConflict(ValueError):
    """The Approval is missing, already changed, or belongs to another tenant."""


class ApprovalRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession] | None = None) -> None:
        self._session_factory = session_factory or get_session_factory()

    @staticmethod
    def _record(approval: Approval) -> PlatformApprovalRecord:
        return PlatformApprovalRecord(
            id=approval.approval_id,
            tenant_id=approval.tenant_id,
            decision_id=approval.decision_id,
            request_id=approval.request_id,
            run_id=approval.execution.run_id,
            status=approval.status,
            version=0,
            approval_json=approval.model_dump(mode="json"),
            created_at=approval.created_at,
            expires_at=approval.expires_at,
            decided_at=approval.decided_at,
            consumed_at=approval.consumed_at,
        )

    @staticmethod
    async def _by_decision(session: AsyncSession, tenant_id: str, decision_id: str) -> PlatformApprovalRecord | None:
        statement = select(PlatformApprovalRecord).where(
            PlatformApprovalRecord.tenant_id == tenant_id,
            PlatformApprovalRecord.decision_id == decision_id,
        )
        return (await session.exec(statement)).one_or_none()

    async def create(self, approval: Approval) -> None:
        if approval.status != "pending":
            raise ValueError("new approval must be pending")
        async with self._session_factory() as session:
            existing = await session.get(PlatformApprovalRecord, approval.approval_id)
            if existing is not None:
                if existing.approval_json != approval.model_dump(mode="json"):
                    raise ValueError("approval_id already exists with different payload")
                return
            decision_statement = select(PlatformPolicyDecisionRecord).where(
                PlatformPolicyDecisionRecord.tenant_id == approval.tenant_id,
                PlatformPolicyDecisionRecord.id == approval.decision_id,
            )
            decision_row = (await session.exec(decision_statement)).one_or_none()
            if decision_row is None:
                raise ValueError("Approval requires a persisted Policy Decision")
            decision = PolicyDecision.model_validate(decision_row.decision_json)
            if not approval.binds(decision):
                raise ValueError("Approval requires a matching require_approval Decision")
            if await self._by_decision(session, approval.tenant_id, approval.decision_id) is not None:
                raise ValueError("decision_id already has an Approval")
            session.add(self._record(approval))
            try:
                await session.commit()
            except IntegrityError:
                await session.rollback()
                existing = await session.get(PlatformApprovalRecord, approval.approval_id)
                if existing is not None:
                    if existing.approval_json != approval.model_dump(mode="json"):
                        raise ValueError("approval_id already exists with different payload") from None
                    return
                if await self._by_decision(session, approval.tenant_id, approval.decision_id) is not None:
                    raise ValueError("decision_id already has an Approval") from None
                raise

    async def get_by_decision(self, tenant_id: str, decision_id: str) -> tuple[Approval, int] | None:
        async with self._session_factory() as session:
            row = await self._by_decision(session, tenant_id, decision_id)
            return None if row is None else (Approval.model_validate(row.approval_json), row.version)

    async def get(self, tenant_id: str, approval_id: str) -> tuple[Approval, int] | None:
        async with self._session_factory() as session:
            statement = select(PlatformApprovalRecord).where(
                PlatformApprovalRecord.tenant_id == tenant_id,
                PlatformApprovalRecord.id == approval_id,
            )
            row = (await session.exec(statement)).one_or_none()
            return None if row is None else (Approval.model_validate(row.approval_json), row.version)

    async def transition(
        self,
        tenant_id: str,
        approval_id: str,
        expected_version: int,
        updated: Approval,
    ) -> tuple[Approval, int]:
        updated = Approval.model_validate(updated.model_dump(mode="json"))
        async with self._session_factory() as session:
            statement = select(PlatformApprovalRecord).where(
                PlatformApprovalRecord.tenant_id == tenant_id,
                PlatformApprovalRecord.id == approval_id,
            )
            row = (await session.exec(statement)).one_or_none()
            if row is None or row.version != expected_version:
                raise ApprovalConflict("approval changed or is unavailable")
            previous = Approval.model_validate(row.approval_json)
            immutable = (
                "schema_version", "tenant_id", "approval_id", "decision_id", "request_id",
                "execution", "action", "resource_id", "context_hash", "policy_version",
                "requester", "created_at", "expires_at",
            )
            if any(getattr(previous, name) != getattr(updated, name) for name in immutable):
                raise ValueError("approval immutable context changed")
            allowed = {
                "pending": {"approved", "rejected", "expired"},
                "approved": {"consumed"},
            }
            if updated.status not in allowed.get(previous.status, set()):
                raise ValueError("invalid approval state transition")
            if previous.status == "approved" and (
                updated.approver != previous.approver or updated.decided_at != previous.decided_at
            ):
                raise ValueError("approval immutable decision changed")
            command = (
                update(PlatformApprovalRecord)
                .where(
                    PlatformApprovalRecord.id == approval_id,
                    PlatformApprovalRecord.tenant_id == tenant_id,
                    PlatformApprovalRecord.version == expected_version,
                )
                .values(
                    status=updated.status,
                    version=expected_version + 1,
                    approval_json=updated.model_dump(mode="json"),
                    decided_at=updated.decided_at,
                    consumed_at=updated.consumed_at,
                )
            )
            result = await session.exec(command)
            if result.rowcount != 1:
                await session.rollback()
                raise ApprovalConflict("approval changed during transition")
            await session.commit()
            return updated, expected_version + 1
