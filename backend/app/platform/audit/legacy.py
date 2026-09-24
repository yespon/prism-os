import json
from datetime import datetime
from typing import cast

from app.platform.contracts import AuditEvent, ExecutionEnvelope, IdentityRef, stable_platform_id
from app.platform.contracts.audit import AuditSeverity

_AUDIT_SEVERITIES = {"debug", "info", "warning", "error", "critical"}


def _required_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"legacy {field} must be a non-blank string")
    return value.strip()


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError("legacy optional text fields must be non-blank strings")
    return value.strip()


def legacy_audit_to_event(
    row: dict[str, object],
    source_name: str,
    line_number: int,
    fallback_tenant_id: str | None = None,
) -> AuditEvent:
    source = _required_text(source_name, "source_name")
    if line_number <= 0:
        raise ValueError("legacy line_number must be positive")

    timestamp = _required_text(row.get("ts"), "ts")
    occurred_at = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    event_type = _required_text(row.get("event_type"), "event_type")
    tenant_id = _optional_text(row.get("tenant_id")) or fallback_tenant_id
    if tenant_id is None:
        raise ValueError("legacy tenant_id is required unless a fallback is explicit")
    tenant_id = _required_text(tenant_id, "tenant_id")

    metadata = row.get("metadata", {})
    if not isinstance(metadata, dict):
        raise ValueError("legacy metadata must be an object")

    canonical = json.dumps(row, ensure_ascii=True, separators=(",", ":"), sort_keys=True)
    source_identity = f"{tenant_id}:{source}:{line_number}:{canonical}"
    raw_severity = _optional_text(row.get("severity")) or "info"
    normalized_severity = raw_severity if raw_severity in _AUDIT_SEVERITIES else "warning"
    severity = cast(AuditSeverity, normalized_severity)

    payload: dict[str, object] = {
        "scope": row.get("scope"),
        "target_user_id": row.get("target_user_id"),
        "metadata": metadata,
    }
    if raw_severity != normalized_severity:
        payload["legacy_severity"] = raw_severity

    actor_id = _optional_text(row.get("actor_id"))
    actor = IdentityRef(kind="user", id=actor_id, tenant_id=tenant_id) if actor_id is not None else None
    execution = ExecutionEnvelope(
        tenant_id=tenant_id,
        task_id=stable_platform_id("task", "legacy-gateway-audit", source_identity),
        run_id=stable_platform_id("run", "legacy-gateway-audit", source_identity),
        correlation_id=f"legacy:{source}:{line_number}",
        workload=IdentityRef(kind="system", id="legacy-gateway-audit", tenant_id=tenant_id),
        actor=actor,
        occurred_at=occurred_at,
        attributes={"legacy_source": source, "legacy_line": line_number},
    )
    return AuditEvent(
        tenant_id=tenant_id,
        event_id=stable_platform_id("event", "legacy-gateway-audit", source_identity),
        event_type=event_type,
        action="legacy.audit",
        outcome="succeeded",
        severity=severity,
        execution=execution,
        payload=payload,
        recorded_at=occurred_at,
    )
