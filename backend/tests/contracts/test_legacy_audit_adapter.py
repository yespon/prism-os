import pytest

from app.platform.audit.legacy import legacy_audit_to_event


def test_legacy_gateway_event_maps_to_v1_contract_deterministically() -> None:
    row = {
        "ts": "2026-08-08T08:30:00Z",
        "event_type": "tenant.member.added",
        "severity": "info",
        "actor_id": "admin-1",
        "target_user_id": "user-2",
        "tenant_id": "tenant-a",
        "scope": "tenant",
        "metadata": {"role": "member"},
    }
    first = legacy_audit_to_event(row, "audit/events.jsonl", 7)
    second = legacy_audit_to_event(row, "audit/events.jsonl", 7)
    assert first == second
    assert first.tenant_id == "tenant-a"
    assert first.execution.attributes["legacy_source"] == "audit/events.jsonl"
    assert first.payload["target_user_id"] == "user-2"


def test_legacy_event_requires_explicit_fallback_tenant() -> None:
    row = {"ts": "2026-08-08T08:30:00Z", "event_type": "platform.started"}
    event = legacy_audit_to_event(row, "audit/events.jsonl", 1, fallback_tenant_id="system-tenant")
    assert event.tenant_id == "system-tenant"


def test_legacy_event_without_tenant_or_fallback_is_rejected() -> None:
    row = {"ts": "2026-08-08T08:30:00Z", "event_type": "platform.started"}
    with pytest.raises(ValueError, match="tenant_id"):
        legacy_audit_to_event(row, "audit/events.jsonl", 1)


def test_fallback_tenant_participates_in_deterministic_identity() -> None:
    row = {"ts": "2026-08-08T08:30:00Z", "event_type": "platform.started"}
    first = legacy_audit_to_event(row, "audit/events.jsonl", 1, fallback_tenant_id="tenant-a")
    second = legacy_audit_to_event(row, "audit/events.jsonl", 1, fallback_tenant_id="tenant-b")
    assert first.event_id != second.event_id
