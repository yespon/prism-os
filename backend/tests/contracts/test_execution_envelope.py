from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.platform.contracts.execution import ExecutionEnvelope
from app.platform.contracts.resources import DefinitionRef, EnvironmentRef, IdentityRef


def _payload() -> dict:
    return {
        "schema_version": "prismos.platform/v1",
        "tenant_id": "tenant-a",
        "task_id": "task_0123456789abcdef0123456789abcdef",
        "run_id": "run_0123456789abcdef0123456789abcdef",
        "correlation_id": "alert-delivery-42",
        "workload": IdentityRef(kind="workload", id="agent-7", tenant_id="tenant-a"),
        "actor": IdentityRef(kind="user", id="user-9", tenant_id="tenant-a"),
        "definition": DefinitionRef(kind="agent", id="definition-4", version="3", tenant_id="tenant-a"),
        "environment": EnvironmentRef(kind="production", id="prod-cn", tenant_id="tenant-a"),
        "occurred_at": datetime(2026, 8, 8, 8, 30, tzinfo=UTC),
        "attributes": {"source": "contract-test"},
    }


def test_execution_envelope_round_trips_as_v1() -> None:
    envelope = ExecutionEnvelope.model_validate(_payload())
    restored = ExecutionEnvelope.model_validate_json(envelope.model_dump_json())
    assert restored == envelope
    assert restored.schema_version == "prismos.platform/v1"


@pytest.mark.parametrize("field", ["tenant_id", "task_id", "run_id", "correlation_id"])
def test_execution_envelope_requires_stable_context(field: str) -> None:
    payload = _payload()
    payload.pop(field)
    with pytest.raises(ValidationError):
        ExecutionEnvelope.model_validate(payload)


def test_execution_envelope_rejects_cross_tenant_refs() -> None:
    payload = _payload()
    payload["workload"] = IdentityRef(kind="workload", id="agent-7", tenant_id="tenant-b")
    with pytest.raises(ValidationError, match="same tenant"):
        ExecutionEnvelope.model_validate(payload)


def test_execution_envelope_has_no_m2_lifecycle_fields() -> None:
    required = set(ExecutionEnvelope.model_json_schema()["required"])
    forbidden = {"status", "attempt", "retry_count", "cancelled_at", "workflow_id"}
    assert required.isdisjoint(forbidden)
    with pytest.raises(ValidationError):
        ExecutionEnvelope.model_validate({**_payload(), "status": "running"})
