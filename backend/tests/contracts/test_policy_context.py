"""Only stable, nonsecret Action facts may influence the M1 context digest."""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.platform.contracts.execution import ExecutionEnvelope
from app.platform.contracts.policy import ActionContextInput, hash_action_context
from app.platform.contracts.resources import IdentityRef


def _execution(tenant_id: str = "tenant-a") -> ExecutionEnvelope:
    return ExecutionEnvelope(
        tenant_id=tenant_id,
        task_id="task-1",
        run_id="run-1",
        correlation_id="alert-1",
        workload=IdentityRef(kind="workload", id="diagnosis-agent", tenant_id=tenant_id),
        occurred_at=datetime(2026, 9, 24, 9, 0, tzinfo=UTC),
    )


def _context(**changes) -> ActionContextInput:
    values = {
        "tenant_id": "tenant-a",
        "execution": _execution(),
        "action": "ticket.create",
        "risk_class": "side_effect",
        "resource_id": "incident-1",
        "parameters": {"ticket": {"severity": "high", "labels": ["api", "production"]}},
    }
    values.update(changes)
    return ActionContextInput(**values)


def test_context_hash_is_canonical_and_changes_with_action_semantics() -> None:
    left = _context(parameters={"b": [1, True, None], "a": {"x": "é"}})
    right = _context(parameters={"a": {"x": "é"}, "b": [1, True, None]})
    assert hash_action_context(left) == hash_action_context(right)
    assert len(hash_action_context(left)) == 64
    assert hash_action_context(left) != hash_action_context(_context(resource_id="incident-2"))
    assert hash_action_context(left) != hash_action_context(_context(action="ticket.update"))
    assert hash_action_context(left) != hash_action_context(_context(parameters={"b": [2]}))
    assert hash_action_context(left) != hash_action_context(_context(execution=_execution("tenant-b"), tenant_id="tenant-b"))


def test_context_input_is_transient_and_rejects_cross_tenant() -> None:
    context = _context()
    dumped = context.model_dump(mode="json")
    assert "parameters" not in dumped
    assert "severity" not in str(dumped)
    with pytest.raises(ValidationError, match="same tenant"):
        _context(tenant_id="tenant-b")
    with pytest.raises(ValidationError):
        _context(command="curl https://example.com")


@pytest.mark.parametrize("key", ["password", "api_key", "Authorization", "access-token", "private_key", "clientSecret"])
def test_context_rejects_sensitive_nested_keys(key: str) -> None:
    with pytest.raises(ValidationError, match="sensitive"):
        _context(parameters={"ticket": {key: "example"}})


@pytest.mark.parametrize("value", [float("nan"), float("inf"), {1, 2}, b"raw-bytes", {1: "bad-key"}])
def test_context_rejects_noncanonical_json(value) -> None:
    with pytest.raises(ValidationError):
        _context(parameters={"value": value})


def test_context_hash_revalidates_mutated_parameters() -> None:
    context = _context()
    context.parameters["ticket"]["access_token"] = "hidden"
    with pytest.raises(ValueError, match="sensitive"):
        hash_action_context(context)


def test_context_rejects_oversized_parameters() -> None:
    with pytest.raises(ValidationError, match="too large"):
        _context(parameters={"description": "x" * 70000})
