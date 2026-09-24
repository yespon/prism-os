import json
from pathlib import Path

from app.platform.contracts import AuditEvent, ExecutionEnvelope

FIXTURE = Path(__file__).parent / "fixtures" / "aio_ops_action_v1.json"


def test_aio_ops_fixture_validates_and_round_trips() -> None:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    event = AuditEvent.model_validate(payload)
    assert AuditEvent.model_validate_json(event.model_dump_json()) == event
    assert event.execution.attributes["external_incident_id"] == "incident-42"


def test_core_required_fields_are_not_aio_ops_specific() -> None:
    audit_required = set(AuditEvent.model_json_schema()["required"])
    execution_required = set(ExecutionEnvelope.model_json_schema()["required"])
    domain_fields = {"incident_id", "alert_id", "asset_id", "command", "diagnosis", "severity_label"}
    assert audit_required.isdisjoint(domain_fields)
    assert execution_required.isdisjoint(domain_fields)
