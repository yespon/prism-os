"""Durable at-most-once automatic submission reservation for M1 tickets."""

from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256

from sqlalchemy import update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.governance import PlatformActionSubmissionRecord, PlatformApprovalRecord, PlatformAuditEventRecord, PlatformPolicyDecisionRecord
from app.platform.contracts import Approval, AuditEvent, PolicyDecision
from deerflow.database.session import get_session_factory


class SubmissionConflict(ValueError):
    """The submission is not eligible or its durable state changed."""


@dataclass(frozen=True)
class SubmissionFact:
    idempotency_key: str
    tenant_id: str
    decision_id: str
    approval_id: str | None
    action: str
    status: str
    ticket_id: str | None
    ticket_url: str | None
    provider: str | None


class ActionSubmissionRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession] | None = None) -> None:
        self._session_factory = session_factory or get_session_factory()

    @staticmethod
    def _at(value: datetime | None) -> datetime:
        instant = value or datetime.now(UTC)
        if instant.tzinfo is None or instant.utcoffset() is None:
            raise ValueError("submission time must be timezone aware")
        return instant.astimezone(UTC)

    @staticmethod
    def _fact(row: PlatformActionSubmissionRecord) -> SubmissionFact:
        return SubmissionFact(
            idempotency_key=row.idempotency_key, tenant_id=row.tenant_id,
            decision_id=row.decision_id, approval_id=row.approval_id,
            action=row.action, status=row.status, ticket_id=row.ticket_id,
            ticket_url=row.ticket_url, provider=row.provider,
        )

    @staticmethod
    def _key(decision: PolicyDecision) -> str:
        digest = sha256(f"{decision.tenant_id}:{decision.decision_id}:ticket.create".encode()).hexdigest()
        return f"prismos-ticket-{digest}"

    @staticmethod
    async def _verify_decision(
        session: AsyncSession, decision: PolicyDecision, approval_id: str | None,
    ) -> None:
        row = await session.get(PlatformPolicyDecisionRecord, decision.decision_id)
        if row is None or row.tenant_id != decision.tenant_id or row.decision_json != decision.model_dump(mode="json"):
            raise SubmissionConflict("persisted Policy Decision is missing or changed")
        statement = select(PlatformAuditEventRecord).where(
            PlatformAuditEventRecord.tenant_id == decision.tenant_id,
            PlatformAuditEventRecord.policy_decision_id == decision.decision_id,
            PlatformAuditEventRecord.event_type == "action.policy_evaluated",
        )
        events = (await session.exec(statement)).all()
        if len(events) != 1:
            raise SubmissionConflict("critical Policy AuditEvent is missing or ambiguous")
        event = AuditEvent.model_validate(events[0].event_json)
        if (
            event.execution != decision.execution or event.action != decision.action
            or event.resource_id != decision.resource_id or event.approval_id != approval_id
            or event.payload.get("verdict") != decision.verdict
            or event.payload.get("policy_version") != decision.policy_version
        ):
            raise SubmissionConflict("critical Policy AuditEvent changed")

    @staticmethod
    async def _verify_approval(
        session: AsyncSession, decision: PolicyDecision, approval_id: str | None, at: datetime,
    ) -> None:
        if decision.verdict != "require_approval":
            if approval_id is not None:
                raise SubmissionConflict("allow Decision cannot use Approval")
            return
        if approval_id is None:
            raise SubmissionConflict("consumed Approval required")
        row = await session.get(PlatformApprovalRecord, approval_id)
        if row is None or row.tenant_id != decision.tenant_id:
            raise SubmissionConflict("consumed Approval required")
        approval = Approval.model_validate(row.approval_json)
        if approval.status != "consumed" or not approval.binds(decision) or at >= approval.expires_at:
            raise SubmissionConflict("consumed Approval required and must be valid")

    async def get(self, tenant_id: str, decision_id: str) -> SubmissionFact | None:
        async with self._session_factory() as session:
            statement = select(PlatformActionSubmissionRecord).where(
                PlatformActionSubmissionRecord.tenant_id == tenant_id,
                PlatformActionSubmissionRecord.decision_id == decision_id,
            )
            row = (await session.exec(statement)).one_or_none()
            return None if row is None else self._fact(row)

    async def prepare(
        self, decision: PolicyDecision, approval_id: str | None = None, *, at: datetime | None = None,
    ) -> SubmissionFact:
        instant = self._at(at)
        if decision.action != "ticket.create" or decision.risk_class != "side_effect" or decision.verdict == "deny":
            raise SubmissionConflict("only allowed ticket.create Decision can submit")
        try:
            async with self._session_factory() as session, session.begin():
                await self._verify_decision(session, decision, approval_id)
                statement = select(PlatformActionSubmissionRecord).where(
                    PlatformActionSubmissionRecord.tenant_id == decision.tenant_id,
                    PlatformActionSubmissionRecord.decision_id == decision.decision_id,
                )
                existing = (await session.exec(statement)).one_or_none()
                if existing is not None:
                    if existing.approval_id != approval_id or existing.action != decision.action:
                        raise SubmissionConflict("existing submission context changed")
                    return self._fact(existing)
                if instant >= decision.expires_at:
                    raise SubmissionConflict("Policy Decision expired")
                await self._verify_approval(session, decision, approval_id, instant)
                row = PlatformActionSubmissionRecord(
                    idempotency_key=self._key(decision), tenant_id=decision.tenant_id,
                    decision_id=decision.decision_id, approval_id=approval_id,
                    action=decision.action, status="not_submitted", created_at=instant,
                )
                session.add(row)
                await session.flush()
                return self._fact(row)
        except IntegrityError:
            existing = await self.get(decision.tenant_id, decision.decision_id)
            if existing is not None and existing.idempotency_key == self._key(decision) and existing.approval_id == approval_id:
                return existing
            raise

    async def claim(self, tenant_id: str, decision_id: str, *, at: datetime | None = None) -> bool:
        instant = self._at(at)
        async with self._session_factory() as session, session.begin():
            statement = select(PlatformActionSubmissionRecord).where(
                PlatformActionSubmissionRecord.tenant_id == tenant_id,
                PlatformActionSubmissionRecord.decision_id == decision_id,
            )
            row = (await session.exec(statement)).one_or_none()
            if row is None or row.status != "not_submitted":
                return False
            decision_row = await session.get(PlatformPolicyDecisionRecord, decision_id)
            if decision_row is None or decision_row.tenant_id != tenant_id:
                raise SubmissionConflict("persisted Policy Decision missing")
            decision = PolicyDecision.model_validate(decision_row.decision_json)
            if instant >= decision.expires_at:
                raise SubmissionConflict("Policy Decision expired")
            await self._verify_approval(session, decision, row.approval_id, instant)
            result = await session.exec(
                update(PlatformActionSubmissionRecord)
                .where(
                    PlatformActionSubmissionRecord.idempotency_key == row.idempotency_key,
                    PlatformActionSubmissionRecord.tenant_id == tenant_id,
                    PlatformActionSubmissionRecord.status == "not_submitted",
                )
                .values(status="unknown", claimed_at=instant)
            )
            return result.rowcount == 1

    async def mark_submitted(
        self, tenant_id: str, decision_id: str, *, ticket_id: str,
        provider: str, ticket_url: str | None = None, at: datetime | None = None,
    ) -> SubmissionFact:
        instant = self._at(at)
        if not ticket_id.strip() or not provider.strip():
            raise SubmissionConflict("ticket_id and provider are required")
        async with self._session_factory() as session, session.begin():
            statement = select(PlatformActionSubmissionRecord).where(
                PlatformActionSubmissionRecord.tenant_id == tenant_id,
                PlatformActionSubmissionRecord.decision_id == decision_id,
            )
            row = (await session.exec(statement)).one_or_none()
            if row is None or row.status != "unknown":
                raise SubmissionConflict("submission was not claimed or already completed")
            result = await session.exec(
                update(PlatformActionSubmissionRecord)
                .where(
                    PlatformActionSubmissionRecord.idempotency_key == row.idempotency_key,
                    PlatformActionSubmissionRecord.tenant_id == tenant_id,
                    PlatformActionSubmissionRecord.status == "unknown",
                )
                .values(
                    status="submitted", ticket_id=ticket_id, ticket_url=ticket_url,
                    provider=provider, submitted_at=instant,
                )
            )
            if result.rowcount != 1:
                raise SubmissionConflict("submission changed during completion")
            return SubmissionFact(
                idempotency_key=row.idempotency_key, tenant_id=tenant_id,
                decision_id=decision_id, approval_id=row.approval_id,
                action=row.action, status="submitted", ticket_id=ticket_id,
                ticket_url=ticket_url, provider=provider,
            )
