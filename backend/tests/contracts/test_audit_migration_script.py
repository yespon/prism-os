import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from scripts.migrate_audit_jsonl import MigrationSummary, migrate

LEGACY_EVENT = {
    "ts": "2026-08-08T08:30:00Z",
    "event_type": "tenant.member.added",
    "severity": "info",
    "tenant_id": "tenant-a",
    "metadata": {},
}


@pytest.mark.anyio
async def test_migration_dry_run_does_not_append(tmp_path) -> None:
    source = tmp_path / "events.jsonl"
    source.write_text(json.dumps(LEGACY_EVENT) + "\n", encoding="utf-8")
    repository = AsyncMock()
    summary = await migrate(source, repository, apply=False, fallback_tenant_id=None)
    assert summary == MigrationSummary(scanned=1, valid=1, written=0, invalid=0)
    repository.append.assert_not_awaited()


@pytest.mark.anyio
async def test_migration_apply_appends_valid_rows_and_counts_invalid(tmp_path) -> None:
    source = tmp_path / "events.jsonl"
    source.write_text(json.dumps(LEGACY_EVENT) + "\n{broken-json}\n", encoding="utf-8")
    repository = AsyncMock()
    summary = await migrate(source, repository, apply=True, fallback_tenant_id=None)
    assert summary == MigrationSummary(scanned=2, valid=1, written=1, invalid=1)
    repository.append.assert_awaited_once()


def test_cli_defaults_to_dry_run_without_database_config(tmp_path) -> None:
    source = tmp_path / "events.jsonl"
    source.write_text(json.dumps(LEGACY_EVENT) + "\n", encoding="utf-8")
    script = Path(__file__).resolve().parents[2] / "scripts" / "migrate_audit_jsonl.py"
    completed = subprocess.run(
        [sys.executable, str(script), "--source", str(source)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0
    assert json.loads(completed.stdout) == {
        "invalid": 0,
        "scanned": 1,
        "valid": 1,
        "written": 0,
    }
