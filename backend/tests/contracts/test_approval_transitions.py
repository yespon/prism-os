from datetime import UTC, datetime, timedelta

import pytest

from app.platform.approval.transitions import approve, consume, expire, reject
from app.platform.contracts.approval import Approval
from app.platform.contracts.execution import ExecutionEnvelope
from app.platform.contracts.policy import PolicyDecision, PolicyRequest
from app.platform.contracts.resources import IdentityRef

NOW = datetime(2026, 9, 24, 9, 0, tzinfo=UTC)
HASH = "a" * 64
ACTOR = IdentityRef(kind="user", id="operator-1", tenant_id="tenant-a")
APPROVER = IdentityRef(kind="user", id="admin-1", tenant_id="tenant-a")


def _context():
    execution = ExecutionEnvelope(
        tenant_id="tenant-a",
        task_id="task-1",
        run_id="run-1",
        correlation_id="alert-1",
        workload=IdentityRef(kind="workload", id="agent-1", tenant_id="tenant-a"),
        actor=ACTOR,
        occurred_at=NOW,
    )
    request = PolicyRequest(
        tenant_id="tenant-a",
        request_id="request-1",
        execution=execution,
        action="terminal.execute",
        risk_class="side_effect",
        resource_id="asset-1",
        context_hash=HASH,
        requested_at=NOW,
    )
    decision = PolicyDecision(
        tenant_id="tenant-a",
        decision_id="decision-1",
        request_id=request.request_id,
        execution=execution,
        action=request.action,
        risk_class=request.risk_class,
        resource_id=request.resource_id,
        context_hash=HASH,
        verdict="require_approval",
        policy_id="terminal-safety",
        policy_version="v1",
        reason_code="risk.high",
        decided_at=NOW,
        expires_at=NOW + timedelta(minutes=10),
    )
    approval = Approval(
        tenant_id="tenant-a",
        approval_id="approval-1",
        decision_id=decision.decision_id,
        request_id=request.request_id,
        execution=execution,
        action=request.action,
        resource_id=request.resource_id,
        context_hash=HASH,
        policy_version="v1",
        requester=ACTOR,
        status="pending",
        created_at=NOW,
        expires_at=NOW + timedelta(minutes=5),
    )
    return request, decision, approval


def test_approve_then_consume_exact_context_once() -> None:
    request, decision, pending = _context()
    approved = approve(pending, APPROVER, at=NOW + timedelta(minutes=1))
    consumed = consume(approved, request, decision, at=NOW + timedelta(minutes=2))
    assert approved.status == "approved"
    assert consumed.status == "consumed"
    with pytest.raises(ValueError, match="already consumed"):
        consume(consumed, request, decision, at=NOW + timedelta(minutes=2))


def test_reject_and_expire_cannot_be_resumed() -> None:
    request, decision, pending = _context()
    rejected = reject(pending, APPROVER, at=NOW + timedelta(minutes=1))
    expired = expire(pending, at=NOW + timedelta(minutes=5))
    assert rejected.status == "rejected"
    assert expired.status == "expired"
    with pytest.raises(ValueError):
        consume(rejected, request, decision, at=NOW + timedelta(minutes=2))
    with pytest.raises(ValueError):
        consume(expired, request, decision, at=NOW + timedelta(minutes=5))
    with pytest.raises(ValueError):
        approve(rejected, APPROVER, at=NOW + timedelta(minutes=2))


def test_expired_or_cross_tenant_approver_cannot_approve() -> None:
    _, _, pending = _context()
    with pytest.raises(ValueError, match="expired"):
        approve(pending, APPROVER, at=NOW + timedelta(minutes=5))
    with pytest.raises(ValueError, match="tenant"):
        approve(pending, IdentityRef(kind="user", id="admin-2", tenant_id="tenant-b"), at=NOW)
    with pytest.raises(ValueError, match="before deadline"):
        expire(pending, at=NOW + timedelta(minutes=4))


def test_resume_rechecks_context_and_decision_version() -> None:
    request, decision, pending = _context()
    approved = approve(pending, APPROVER, at=NOW + timedelta(minutes=1))
    with pytest.raises(ValueError, match="context"):
        consume(approved, request.model_copy(update={"context_hash": "b" * 64}), decision, at=NOW)
    with pytest.raises(ValueError, match="context"):
        consume(approved, request, decision.model_copy(update={"policy_version": "v2"}), at=NOW)
    with pytest.raises(ValueError, match="expired"):
        consume(approved, request, decision, at=NOW + timedelta(minutes=5))


def test_transition_requires_timezone_aware_time() -> None:
    _, _, pending = _context()
    with pytest.raises(ValueError, match="timezone"):
        approve(pending, APPROVER, at=NOW.replace(tzinfo=None))
