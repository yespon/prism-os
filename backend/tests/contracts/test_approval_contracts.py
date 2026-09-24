from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from app.platform.contracts.approval import Approval
from app.platform.contracts.execution import ExecutionEnvelope
from app.platform.contracts.policy import PolicyDecision
from app.platform.contracts.resources import IdentityRef

NOW = datetime(2026, 9, 24, 9, 0, tzinfo=UTC)
HASH = "a" * 64


def _identity(tenant_id: str = "tenant-a") -> IdentityRef:
    return IdentityRef(kind="user", id="operator-1", tenant_id=tenant_id)


def _execution(tenant_id: str = "tenant-a") -> ExecutionEnvelope:
    return ExecutionEnvelope(
        tenant_id=tenant_id,
        task_id="task-1",
        run_id="run-1",
        correlation_id="alert-1",
        workload=IdentityRef(kind="workload", id="agent-1", tenant_id=tenant_id),
        actor=_identity(tenant_id),
        occurred_at=NOW,
    )


def _decision(**changes) -> PolicyDecision:
    fields = {
        "tenant_id": "tenant-a",
        "decision_id": "decision-1",
        "request_id": "request-1",
        "execution": _execution(),
        "action": "terminal.execute",
        "risk_class": "side_effect",
        "resource_id": "asset-1",
        "context_hash": HASH,
        "verdict": "require_approval",
        "policy_id": "terminal-safety",
        "policy_version": "v1",
        "reason_code": "risk.high",
        "decided_at": NOW,
        "expires_at": NOW + timedelta(minutes=10),
    }
    fields.update(changes)
    return PolicyDecision(**fields)


def _approval(**changes) -> Approval:
    fields = {
        "tenant_id": "tenant-a",
        "approval_id": "approval-1",
        "decision_id": "decision-1",
        "request_id": "request-1",
        "execution": _execution(),
        "action": "terminal.execute",
        "resource_id": "asset-1",
        "context_hash": HASH,
        "policy_version": "v1",
        "requester": _identity(),
        "status": "pending",
        "created_at": NOW,
        "expires_at": NOW + timedelta(minutes=5),
    }
    fields.update(changes)
    return Approval(**fields)


def test_pending_approval_round_trips_and_binds_decision() -> None:
    approval = _approval()
    assert Approval.model_validate_json(approval.model_dump_json()) == approval
    assert approval.binds(_decision())
    assert approval.schema_version == "prismos.platform/v1"


def test_approval_rejects_other_tenant_and_non_approval_decision() -> None:
    with pytest.raises(ValidationError, match="same tenant"):
        _approval(tenant_id="tenant-b")
    with pytest.raises(ValidationError, match="execution actor"):
        _approval(requester=IdentityRef(kind="user", id="different-user", tenant_id="tenant-a"))
    with pytest.raises(ValidationError, match="same tenant"):
        _approval(
            status="approved",
            approver=IdentityRef(kind="user", id="admin-1", tenant_id="tenant-b"),
            decided_at=NOW + timedelta(minutes=1),
        )
    assert not _approval().binds(_decision(verdict="allow"))
    assert not _approval().binds(_decision(policy_version="v2"))
    assert not _approval().binds(_decision(context_hash="b" * 64))


def test_approval_rejects_inconsistent_status_fields() -> None:
    with pytest.raises(ValidationError):
        _approval(status="approved")
    with pytest.raises(ValidationError):
        _approval(status="pending", approver=_identity())
    with pytest.raises(ValidationError):
        _approval(status="rejected", approver=_identity(), decided_at=NOW + timedelta(minutes=6))


def test_approval_terminal_states_require_correct_times_and_approver() -> None:
    approver = IdentityRef(kind="user", id="admin-1", tenant_id="tenant-a")
    approved = _approval(status="approved", approver=approver, decided_at=NOW + timedelta(minutes=1))
    rejected = _approval(status="rejected", approver=approver, decided_at=NOW + timedelta(minutes=1))
    expired = _approval(status="expired", decided_at=NOW + timedelta(minutes=5))
    consumed = _approval(
        status="consumed",
        approver=approver,
        decided_at=NOW + timedelta(minutes=1),
        consumed_at=NOW + timedelta(minutes=2),
    )
    assert {item.status for item in (approved, rejected, expired, consumed)} == {
        "approved", "rejected", "expired", "consumed"
    }
    with pytest.raises(ValidationError):
        _approval(status="expired", decided_at=NOW + timedelta(minutes=1))
    with pytest.raises(ValidationError):
        _approval(status="consumed", approver=approver, decided_at=NOW + timedelta(minutes=1))


def test_approval_rejects_invalid_expiry_naive_time_and_extra_fields() -> None:
    with pytest.raises(ValidationError):
        _approval(expires_at=NOW)
    with pytest.raises(ValidationError):
        _approval(created_at=NOW.replace(tzinfo=None))
    with pytest.raises(ValidationError):
        _approval(command="rm -rf /tmp/example")
