#!/usr/bin/env python3
"""Dry-run or explicitly apply the legacy PrismOS home migration."""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

from deerflow.config.home_migration import (
    _MINIMUM_SAFETY_MARGIN,
    _available_bytes,
    _open_files_under,
    apply_home_migration,
    plan_home_migration,
)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Plan or explicitly apply an .opsintech to .prismos home migration."
    )
    parser.add_argument(
        "--source",
        type=Path,
        default=Path.home() / ".opsintech",
        help="source directory (default: ~/.opsintech)",
    )
    parser.add_argument(
        "--target",
        type=Path,
        default=Path.home() / ".prismos",
        help="target directory (default: ~/.prismos)",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="copy, verify, and atomically activate the target",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        help="optional external copy of the verified manifest (must be outside both directories)",
    )
    return parser.parse_args()


def _ensure_external_manifest(path: Path, source: Path, target: Path) -> Path:
    resolved = path.expanduser().resolve()
    for root in (source.resolve(), target.resolve()):
        try:
            resolved.relative_to(root)
        except ValueError:
            continue
        raise ValueError("--manifest must be outside both source and target directories")
    if resolved.exists():
        raise FileExistsError(f"Manifest destination already exists: {resolved}")
    return resolved


def main() -> int:
    args = _parse_args()
    try:
        source = args.source.expanduser()
        target = args.target.expanduser()
        external_manifest = (
            _ensure_external_manifest(args.manifest, source, target)
            if args.manifest is not None
            else None
        )
        plan = plan_home_migration(source, target)
        required = plan.total_bytes + max(plan.total_bytes // 10, _MINIMUM_SAFETY_MARGIN)
        available = _available_bytes(plan.target.parent)
        open_files = _open_files_under(plan.source)
        print(f"Source: {plan.source}")
        print(f"Target: {plan.target}")
        print(f"Files: {plan.file_count}")
        print(f"Total bytes: {plan.total_bytes}")
        print(f"Required bytes: {required}")
        print(f"Available bytes: {available}")
        print(f"Open files: {len(open_files)}")
        print(f"Manifest: {external_manifest or plan.manifest_path}")
        if not args.apply:
            print("Dry-run only: no files or directories were created.")
            return 0

        result = apply_home_migration(plan)
        if external_manifest is not None:
            external_manifest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(result.manifest_path, external_manifest)
        print(f"Verified manifest: {result.manifest_path}")
        print(
            "Rollback: set PRISMOS_HOME to the preserved source directory; "
            "neither copy is deleted automatically."
        )
        return 0
    except (FileExistsError, FileNotFoundError, OSError, RuntimeError, ValueError) as exc:
        print(f"Migration aborted: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
