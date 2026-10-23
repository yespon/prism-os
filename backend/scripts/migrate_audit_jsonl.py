import argparse
import asyncio
import json
import sys
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Protocol

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.platform.audit.legacy import legacy_audit_to_event  # noqa: E402
from app.platform.audit.repository import AuditEventRepository  # noqa: E402
from app.platform.contracts import AuditEvent  # noqa: E402


class AuditEventAppender(Protocol):
    async def append(self, event: AuditEvent) -> None: ...


class _DryRunAppender:
    async def append(self, event: AuditEvent) -> None:
        raise AssertionError("dry-run must not append audit events")


@dataclass(frozen=True)
class MigrationSummary:
    scanned: int
    valid: int
    written: int
    invalid: int


async def migrate(
    source: Path,
    repository: AuditEventAppender,
    *,
    apply: bool,
    fallback_tenant_id: str | None,
) -> MigrationSummary:
    scanned = valid = written = invalid = 0
    with source.open(encoding="utf-8") as handle:
        for line_number, raw_line in enumerate(handle, start=1):
            stripped = raw_line.strip()
            if not stripped:
                continue
            scanned += 1
            try:
                decoded = json.loads(stripped)
                if not isinstance(decoded, dict):
                    raise ValueError("legacy audit row must be a JSON object")
                event = legacy_audit_to_event(
                    decoded,
                    str(source),
                    line_number,
                    fallback_tenant_id=fallback_tenant_id,
                )
            except (json.JSONDecodeError, TypeError, ValueError):
                invalid += 1
                print(f"invalid legacy audit line: {line_number}", file=sys.stderr)
                continue

            valid += 1
            if apply:
                await repository.append(event)
                written += 1

    return MigrationSummary(scanned=scanned, valid=valid, written=written, invalid=invalid)


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Migrate legacy JSONL audit events")
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--tenant-id", dest="fallback_tenant_id")
    args = parser.parse_args(argv)
    if not args.source.is_file():
        parser.error("--source must reference an existing file")
    return args


async def _run(args: argparse.Namespace) -> int:
    repository: AuditEventAppender = AuditEventRepository() if args.apply else _DryRunAppender()
    summary = await migrate(
        args.source,
        repository,
        apply=args.apply,
        fallback_tenant_id=args.fallback_tenant_id,
    )
    print(json.dumps(asdict(summary), sort_keys=True))
    return 2 if summary.invalid else 0


def main(argv: Sequence[str] | None = None) -> int:
    return asyncio.run(_run(_parse_args(argv)))


if __name__ == "__main__":
    raise SystemExit(main())
