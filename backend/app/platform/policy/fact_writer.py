"""Atomic Policy, critical Audit, and pending Approval fact recording."""

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.governance import PlatformApprovalRecord, PlatformAuditEventRecord, PlatformPolicyDecisionRecord
from app.platform.approval.repository import ApprovalRepository
from app.platform.audit.repository import AuditEventRepository
from app.platform.contracts import Approval, AuditEvent, PolicyDecision
from app.platform.policy.repository import PolicyDecisionRepository
from deerflow.database.session import get_session_factory


class PolicyFactWriter:
    """Persist a decision before any caller may consider an Action executable."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession] | None = None) -> None:
        self._session_factory = session_factory or get_session_factory()

    @staticmethod
    def _validate(decision: PolicyDecision, audit: AuditEvent, approval: Approval | None) -> None:
        if (
            audit.event_type != "action.policy_evaluated"
            or audit.tenant_id != decision.tenant_id
            or audit.execution != decision.execution
            or audit.action != decision.action
            or audit.resource_id != decision.resource_id
            or audit.policy_decision_id != decision.decision_id
            or audit.outcome != ("denied" if decision.verdict == "deny" else "pending")
            or audit.payload.get("verdict") != decision.verdict
            or audit.payload.get("policy_version") != decision.policy_version
        ):
            raise ValueError("AuditEvent does not match Policy Decision")
        if decision.verdict == "require_approval":
            if approval is None or approval.status != "pending" or not approval.binds(decision):
                raise ValueError("require_approval Decision requires a matching pending Approval")
            if audit.approval_id != approval.approval_id:
                raise ValueError("AuditEvent must reference the pending Approval")
        elif approval is not None or audit.approval_id is not None:
            raise ValueError("Approval is only valid for require_approval Decision")

    @staticmethod
    async def _existing(
        session: AsyncSession, decision: PolicyDecision, audit: AuditEvent, approval: Approval | None,
    ) -> bool:
        statement = select(PlatformPolicyDecisionRecord).where(
            PlatformPolicyDecisionRecord.tenant_id == decision.tenant_id,
            PlatformPolicyDecisionRecord.request_id == decision.request_id,
        )
        row = (await session.exec(statement)).one_or_none()
        if row is None:
            return False
        if row.decision_json != decision.model_dump(mode="json"):
            raise ValueError("request_id already has a different Policy Decision")
        audit_row = await session.get(PlatformAuditEventRecord, audit.event_id)
        if audit_row is None:
            raise ValueError("Policy Decision exists without matching critical AuditEvent")
        AuditEventRepository._assert_same_event(audit_row, audit)
        if approval is not None:
            approval_row = await session.get(PlatformApprovalRecord, approval.approval_id)
            if approval_row is None or approval_row.approval_json != approval.model_dump(mode="json"):
                raise ValueError("Policy Decision exists without matching pending Approval")
        return True

    async def record(self, decision: PolicyDecision, audit: AuditEvent, approval: Approval | None = None) -> None:
        """Commit all facts together; return no execution capability or token."""
        self._validate(decision, audit, approval)
        try:
            async with self._session_factory() as session, session.begin():
                if await self._existing(session, decision, audit, approval):
                    return
                session.add(PolicyDecisionRepository._record(decision))
                await AuditEventRepository.append_in_session(session, audit)
                if approval is not None:
                    session.add(ApprovalRepository._record(approval))
                await session.flush()
        except IntegrityError:
            # Only a complete identical fact set makes a unique-key race idempotent.
            async with self._session_factory() as session:
                if await self._existing(session, decision, audit, approval):
                    return
            raise
