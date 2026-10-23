from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from app.platform.contracts.execution import ExecutionEnvelope
from app.platform.contracts.policy import PolicyDecision, PolicyRequest
from app.platform.contracts.resources import IdentityRef

NOW = datetime(2026, 9, 24, 9, 0, tzinfo=UTC)
HASH = "a" * 64


def _execution(tenant_id: str = "tenant-a") -> ExecutionEnvelope:
    return ExecutionEnvelope(
        tenant_id=tenant_id,
        task_id="task-1",
        run_id="run-1",
        correlation_id="alert-1",
        workload=IdentityRef(kind="workload", id="diagnosis-agent", tenant_id=tenant_id),
        actor=IdentityRef(kind="user", id="operator-1", tenant_id=tenant_id),
        occurred_at=NOW,
    )


def _request(**changes) -> PolicyRequest:
    fields = {
        "tenant_id": "tenant-a",
        "request_id": "policy-request-1",
        "execution": _execution(),
        "action": "terminal.execute",
        "risk_class": "side_effect",
        "resource_id": "asset-1",
        "context_hash": HASH,
        "requested_at": NOW,
    }
    fields.update(changes)
    return PolicyRequest(**fields)


def _decision(**changes) -> PolicyDecision:
    fields = {
        "tenant_id": "tenant-a",
        "decision_id": "decision-1",
        "request_id": "policy-request-1",
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
        "expires_at": NOW + timedelta(minutes=5),
    }
    fields.update(changes)
    return PolicyDecision(**fields)


@pytest.mark.parametrize("verdict", ["allow", "deny", "require_approval"])
def test_policy_decision_three_branches_round_trip(verdict: str) -> None:
    decision = _decision(verdict=verdict)
    assert PolicyDecision.model_validate_json(decision.model_dump_json()) == decision
    assert decision.schema_version == "prismos.platform/v1"
    assert decision.binds(_request())


def test_policy_request_rejects_cross_tenant_and_unknown_fields() -> None:
    with pytest.raises(ValidationError, match="same tenant"):
        _request(tenant_id="tenant-b")
    with pytest.raises(ValidationError):
        _request(incident_id="incident-1")


def test_policy_decision_rejects_cross_tenant_and_unknown_verdict() -> None:
    with pytest.raises(ValidationError, match="same tenant"):
        _decision(tenant_id="tenant-b")
    with pytest.raises(ValidationError):
        _decision(verdict="ask")


def test_policy_contract_rejects_invalid_hash_and_naive_time() -> None:
    with pytest.raises(ValidationError):
        _request(context_hash="not-a-sha256")
    with pytest.raises(ValidationError):
        _decision(decided_at=NOW.replace(tzinfo=None))
    with pytest.raises(ValidationError):
        _decision(expires_at=NOW)


def test_decision_does_not_bind_changed_action_or_context() -> None:
    decision = _decision()
    assert not decision.binds(_request(action="terminal.write_file"))
    assert not decision.binds(_request(context_hash="b" * 64))
    assert not decision.binds(_request(resource_id="asset-2"))
    assert not decision.binds(_request(execution=_execution("tenant-b"), tenant_id="tenant-b"))


def test_policy_contract_has_no_domain_required_fields_or_run_lifecycle() -> None:
    for contract in (PolicyRequest, PolicyDecision):
        required = set(contract.model_json_schema()["required"])
        assert required.isdisjoint({"incident_id", "alert_id", "host_id", "command", "status", "attempt"})
