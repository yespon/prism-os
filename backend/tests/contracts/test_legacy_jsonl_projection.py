import json

from app.gateway import audit


def test_platform_jsonl_projection_is_idempotent_and_old_reader_compatible(tmp_path, monkeypatch) -> None:
    path = tmp_path / "events.jsonl"
    monkeypatch.setattr(audit, "_audit_file", lambda: path)
    event = {
        "event_id": "event-1", "event_type": "action.submitted",
        "actor_id": "user-1", "tenant_id": "tenant-a", "scope": "ticket.create",
        "severity": "info", "metadata": {"ticket_id": "T-1"},
    }
    audit.record_platform_audit_event(event)
    audit.record_platform_audit_event(event)
    assert len(path.read_text().splitlines()) == 1
    row = audit.read_audit_events(tenant_id="tenant-a")[0]
    assert row["metadata"]["platform_event_id"] == "event-1"
    assert row["metadata"]["ticket_id"] == "T-1"
    assert audit.read_audit_events(tenant_id="tenant-b") == []
    assert json.loads(path.read_text())["event_type"] == "action.submitted"
