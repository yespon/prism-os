import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from deerflow.config.paths import get_paths


def _audit_file() -> Path:
    path = get_paths().base_dir / "audit" / "events.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def record_audit_event(
    event_type: str,
    *,
    actor_id: str | None = None,
    target_user_id: str | None = None,
    tenant_id: str | None = None,
    scope: str | None = None,
    severity: str = "info",
    metadata: dict[str, Any] | None = None,
) -> None:
    event = {
        "ts": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "event_type": event_type,
        "severity": severity,
        "actor_id": actor_id,
        "target_user_id": target_user_id,
        "tenant_id": tenant_id,
        "scope": scope,
        "metadata": metadata or {},
    }
    with _audit_file().open("a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=True) + "\n")


def read_audit_events(
    *,
    limit: int = 100,
    tenant_id: str | None = None,
    scope: str | None = None,
) -> list[dict[str, Any]]:
    path = _audit_file()
    if not path.exists():
        return []

    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue

    if tenant_id is not None:
        rows = [row for row in rows if row.get("tenant_id") == tenant_id]
    if scope is not None:
        rows = [row for row in rows if row.get("scope") == scope]

    if limit <= 0:
        return []
    return rows[-limit:][::-1]


def record_platform_audit_event(event: dict[str, Any]) -> None:
    """Append a sanitized platform projection once, including after replay or a crash."""
    import fcntl

    event_id = event["event_id"]
    row = {
        "ts": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "event_type": event["event_type"],
        "severity": event["severity"],
        "actor_id": event["actor_id"],
        "target_user_id": None,
        "tenant_id": event["tenant_id"],
        "scope": event["scope"],
        "metadata": {**event["metadata"], "platform_event_id": event_id},
    }
    with _audit_file().open("a+", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            handle.seek(0)
            for line in handle:
                try:
                    existing = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if existing.get("metadata", {}).get("platform_event_id") == event_id:
                    if existing.get("tenant_id") != event["tenant_id"]:
                        raise ValueError("platform audit event identity conflict")
                    return
            handle.seek(0, 2)
            handle.write(json.dumps(row, ensure_ascii=True) + "\n")
            handle.flush()
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
