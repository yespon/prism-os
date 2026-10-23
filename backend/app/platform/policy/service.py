"""Evaluate and durably record Policy facts before an Action can proceed."""

from datetime import datetime
from hashlib import sha256

from sqlalchemy.exc import IntegrityError

from app.platform.contracts import Approval, AuditEvent, PolicyDecision, PolicyRequest, stable_platform_id
from app.platform.policy.evaluator import PolicyConfiguration, PolicyEvaluator, SafetyProvider
from app.platform.policy.fact_writer import PolicyFactWriter
from app.platform.policy.repository import PolicyDecisionRepository


class PolicyService:
    def __init__(
        self,
        writer: PolicyFactWriter | None = None,
        decisions: PolicyDecisionRepository | None = None,
        evaluator: PolicyEvaluator | None = None,
    ) -> None:
        self._writer = writer or PolicyFactWriter()
        self._decisions = decisions or PolicyDecisionRepository()
        self._evaluator = evaluator or PolicyEvaluator()

    @staticmethod
    def _facts(decision: PolicyDecision) -> tuple[AuditEvent, Approval | None]:
        approval = None
        if decision.verdict == "require_approval":
            if decision.execution.actor is None:
                raise ValueError("Approval requires a trusted execution actor")
            identifier = sha256(decision.decision_id.encode()).hexdigest()[:32]
            approval = Approval(
                tenant_id=decision.tenant_id,
                approval_id=f"approval_{identifier}",
                decision_id=decision.decision_id,
                request_id=decision.request_id,
                execution=decision.execution,
                action=decision.action,
                resource_id=decision.resource_id,
                context_hash=decision.context_hash,
                policy_version=decision.policy_version,
                requester=decision.execution.actor,
                status="pending",
                created_at=decision.decided_at,
                expires_at=decision.expires_at,
            )
        event = AuditEvent(
            tenant_id=decision.tenant_id,
            event_id=stable_platform_id("event", "policy-evaluation", decision.decision_id),
            event_type="action.policy_evaluated",
            action=decision.action,
            outcome="denied" if decision.verdict == "deny" else "pending",
            execution=decision.execution,
            policy_decision_id=decision.decision_id,
            approval_id=None if approval is None else approval.approval_id,
            resource_id=decision.resource_id,
            payload={
                "verdict": decision.verdict,
                "policy_version": decision.policy_version,
                "reason_code": decision.reason_code,
            },
            recorded_at=decision.decided_at,
        )
        return event, approval

    async def _record_existing(self, request: PolicyRequest, decision: PolicyDecision) -> PolicyDecision:
        if not decision.binds(request):
            raise ValueError("request_id reused for a different Action context")
        event, approval = self._facts(decision)
        await self._writer.record(decision, event, approval)
        return decision

    async def evaluate_and_record(
        self,
        request: PolicyRequest,
        configuration: PolicyConfiguration | None,
        safety_provider: SafetyProvider | None = None,
        *,
        at: datetime | None = None,
    ) -> PolicyDecision:
        """Return the persisted decision fact, never an execution capability."""
        existing = await self._decisions.get_by_request(request.tenant_id, request.request_id)
        if existing is not None:
            return await self._record_existing(request, existing)
        decision = await self._evaluator.evaluate(request, configuration, safety_provider, at=at)
        event, approval = self._facts(decision)
        try:
            await self._writer.record(decision, event, approval)
        except (IntegrityError, ValueError):
            # A concurrent writer may have won. Verify its complete fact set.
            existing = await self._decisions.get_by_request(request.tenant_id, request.request_id)
            if existing is None:
                raise
            return await self._record_existing(request, existing)
        return decision
