from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.platform.contracts.audit import AuditEvent
from app.platform.contracts.execution import ExecutionEnvelope
from app.platform.contracts.resources import IdentityRef


def _execution() -> ExecutionEnvelope:
    return ExecutionEnvelope(
        tenant_id="tenant-a",
        task_id="task_0123456789abcdef0123456789abcdef",
        run_id="run_0123456789abcdef0123456789abcdef",
        correlation_id="correlation-7",
        workload=IdentityRef(kind="workload", id="agent-7", tenant_id="tenant-a"),
        occurred_at=datetime(2026, 8, 8, 8, 30, tzinfo=UTC),
    )


def test_audit_event_carries_complete_execution_correlation() -> None:
    event = AuditEvent(
        tenant_id="tenant-a",
        event_id="event_0123456789abcdef0123456789abcdef",
        event_type="action.policy_evaluated",
        action="terminal.execute",
        outcome="pending",
        severity="info",
        execution=_execution(),
        policy_decision_id="decision-4",
        approval_id="approval-2",
        payload={"risk": "high"},
        recorded_at=datetime(2026, 8, 8, 8, 31, tzinfo=UTC),
    )
    assert event.tenant_id == "tenant-a"
    assert event.task_id == event.execution.task_id
    assert event.run_id == event.execution.run_id


def test_audit_event_rejects_wrong_schema_and_unknown_outcome() -> None:
    common = {
        "tenant_id": "tenant-a",
        "event_id": "event_0123456789abcdef0123456789abcdef",
        "event_type": "action.completed",
        "action": "terminal.execute",
        "severity": "info",
        "execution": _execution(),
        "recorded_at": datetime.now(UTC),
    }
    with pytest.raises(ValidationError):
        AuditEvent(**common, schema_version="prismos.platform/v2", outcome="succeeded")
    with pytest.raises(ValidationError):
        AuditEvent(**common, outcome="maybe")


def test_audit_event_rejects_cross_tenant_execution() -> None:
    with pytest.raises(ValidationError, match="same tenant"):
        AuditEvent(
            tenant_id="tenant-b",
            event_id="event_0123456789abcdef0123456789abcdef",
            event_type="action.completed",
            action="terminal.execute",
            outcome="succeeded",
            execution=_execution(),
            recorded_at=datetime.now(UTC),
        )
