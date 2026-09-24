from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models import governance as _governance_models  # noqa: F401
from app.platform.approval.repository import ApprovalRepository
from app.platform.audit.repository import AuditEventRepository
from app.platform.contracts import Approval, AuditEvent, ExecutionEnvelope, IdentityRef, PolicyDecision
from app.platform.policy.fact_writer import PolicyFactWriter
from app.platform.policy.repository import PolicyDecisionRepository

NOW = datetime(2026, 9, 24, 9, 0, tzinfo=UTC)


@pytest.fixture
async def stores(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'facts.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(SQLModel.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    yield PolicyFactWriter(factory), PolicyDecisionRepository(factory), AuditEventRepository(factory), ApprovalRepository(factory)
    await engine.dispose()


def _facts(*, verdict: str = "require_approval", suffix: str = "1"):
    actor = IdentityRef(kind="user", id="user-1", tenant_id="tenant-a")
    execution = ExecutionEnvelope(
        tenant_id="tenant-a",
        task_id="task-1",
        run_id="run-1",
        correlation_id=f"alert-{suffix}",
        workload=IdentityRef(kind="workload", id="agent-1", tenant_id="tenant-a"),
        actor=actor,
        occurred_at=NOW,
    )
    decision = PolicyDecision(
        tenant_id="tenant-a",
        decision_id=f"decision-{suffix}",
        request_id=f"request-{suffix}",
        execution=execution,
        action="ticket.create",
        risk_class="side_effect",
        resource_id="incident-1",
        context_hash="a" * 64,
        verdict=verdict,
        policy_id="ticket-policy",
        policy_version="v1",
        reason_code=f"policy.{verdict}",
        decided_at=NOW,
        expires_at=NOW + timedelta(minutes=10),
    )
    approval = None
    if verdict == "require_approval":
        approval = Approval(
            tenant_id=decision.tenant_id,
            approval_id=f"approval-{suffix}",
            decision_id=decision.decision_id,
            request_id=decision.request_id,
            execution=execution,
            action=decision.action,
            resource_id=decision.resource_id,
            context_hash=decision.context_hash,
            policy_version=decision.policy_version,
            requester=actor,
            status="pending",
            created_at=NOW,
            expires_at=NOW + timedelta(minutes=5),
        )
    event = AuditEvent(
        tenant_id=decision.tenant_id,
        event_id=f"event-{suffix}",
        event_type="action.policy_evaluated",
        action=decision.action,
        outcome="denied" if verdict == "deny" else "pending",
        execution=execution,
        policy_decision_id=decision.decision_id,
        approval_id=None if approval is None else approval.approval_id,
        resource_id=decision.resource_id,
        payload={"verdict": verdict, "policy_version": decision.policy_version},
        recorded_at=NOW + timedelta(seconds=1),
    )
    return decision, event, approval


@pytest.mark.anyio
@pytest.mark.parametrize("verdict", ["allow", "deny", "require_approval"])
async def test_writer_commits_matching_facts_atomically(stores, verdict) -> None:
    writer, decisions, audits, approvals = stores
    decision, event, approval = _facts(verdict=verdict)
    await writer.record(decision, event, approval)
    await writer.record(decision, event, approval)
    assert await decisions.get("tenant-a", decision.decision_id) == decision
    assert await audits.get(event.event_id, "tenant-a") == event
    if approval is not None:
        assert await approvals.get("tenant-a", approval.approval_id) == (approval, 0)
    assert await decisions.get("tenant-b", decision.decision_id) is None


@pytest.mark.anyio
async def test_writer_rejects_unbound_audit_or_missing_approval(stores) -> None:
    writer, decisions, audits, _ = stores
    decision, event, approval = _facts()
    with pytest.raises(ValueError, match="Approval"):
        await writer.record(decision, event, None)
    with pytest.raises(ValueError, match="Audit"):
        await writer.record(decision, event.model_copy(update={"action": "other.action"}), approval)
    assert await decisions.get("tenant-a", decision.decision_id) is None
    assert await audits.get(event.event_id, "tenant-a") is None


@pytest.mark.anyio
async def test_audit_insert_failure_rolls_back_decision(stores) -> None:
    writer, decisions, audits, _ = stores
    prior_decision, prior_event, _ = _facts(verdict="deny", suffix="prior")
    await writer.record(prior_decision, prior_event)
    decision, event, _ = _facts(verdict="allow")
    with pytest.raises(ValueError, match="different payload"):
        await writer.record(decision, event.model_copy(update={"event_id": prior_event.event_id}))
    assert await decisions.get("tenant-a", decision.decision_id) is None
    assert await audits.get(prior_event.event_id, "tenant-a") == prior_event


@pytest.mark.anyio
async def test_approval_insert_failure_rolls_back_decision_and_audit(stores) -> None:
    writer, decisions, audits, _ = stores
    prior_decision, prior_event, prior_approval = _facts(suffix="prior")
    await writer.record(prior_decision, prior_event, prior_approval)
    decision, event, approval = _facts()
    conflicting_approval = approval.model_copy(update={"approval_id": prior_approval.approval_id})
    linked_event = event.model_copy(update={"approval_id": conflicting_approval.approval_id})
    with pytest.raises(IntegrityError):
        await writer.record(decision, linked_event, conflicting_approval)
    assert await decisions.get("tenant-a", decision.decision_id) is None
    assert await audits.get(event.event_id, "tenant-a") is None


@pytest.mark.anyio
async def test_request_reuse_with_different_decision_is_conflict(stores) -> None:
    writer, decisions, audits, _ = stores
    decision, event, _ = _facts(verdict="allow")
    await writer.record(decision, event)
    changed = decision.model_copy(update={"decision_id": "decision-2"})
    changed_event = event.model_copy(update={"event_id": "event-2", "policy_decision_id": "decision-2"})
    with pytest.raises(ValueError, match="request_id"):
        await writer.record(changed, changed_event)
    assert await decisions.get_by_request("tenant-a", decision.request_id) == decision
    assert await audits.get("event-2", "tenant-a") is None


@pytest.mark.anyio
async def test_existing_decision_without_audit_fails_closed(stores) -> None:
    writer, decisions, audits, _ = stores
    decision, event, _ = _facts(verdict="allow")
    await decisions.append(decision)
    with pytest.raises(ValueError, match="Audit"):
        await writer.record(decision, event)
    assert await audits.get(event.event_id, "tenant-a") is None


@pytest.mark.anyio
async def test_decision_insert_failure_rolls_back_audit(stores) -> None:
    writer, decisions, audits, _ = stores
    prior_decision, prior_event, _ = _facts(verdict="deny", suffix="prior")
    await writer.record(prior_decision, prior_event)
    decision, event, _ = _facts(verdict="allow")
    changed = decision.model_copy(update={"decision_id": prior_decision.decision_id})
    changed_event = event.model_copy(update={"policy_decision_id": changed.decision_id})
    with pytest.raises(IntegrityError):
        await writer.record(changed, changed_event)
    assert await decisions.get_by_request("tenant-a", decision.request_id) is None
    assert await audits.get(event.event_id, "tenant-a") is None
