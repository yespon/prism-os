#!/usr/bin/env python3
"""Enforce the PrismOS brand boundary for tracked repository content."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

LEGACY_PATTERN = re.compile(r"opsintech(?:-platform)?|OPSINTECH", re.IGNORECASE)
REQUIRED_FIELDS = {"path", "classification", "reason", "owner", "remove_by", "max_matches"}


@dataclass(frozen=True)
class LegacyMatch:
    path: str
    line: int
    token: str
    text: str


def tracked_paths(repo_root: Path) -> list[str]:
    """Return repository-relative tracked paths, including files with spaces."""
    result = subprocess.run(
        ["git", "ls-files", "-z"], cwd=repo_root, check=True, capture_output=True
    )
    return [item.decode() for item in result.stdout.split(b"\0") if item]


def scan_paths(repo_root: Path, paths: Iterable[str]) -> list[LegacyMatch]:
    """Find legacy brand tokens in path names and UTF-8 text files."""
    matches: list[LegacyMatch] = []
    for relative in paths:
        filename_match = LEGACY_PATTERN.search(relative)
        if filename_match:
            matches.append(LegacyMatch(relative, 0, filename_match.group(0), relative))

        path = repo_root / relative
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, IsADirectoryError, FileNotFoundError):
            continue
        for line_number, line in enumerate(text.splitlines(), 1):
            for match in LEGACY_PATTERN.finditer(line):
                matches.append(LegacyMatch(relative, line_number, match.group(0), line.strip()))
    return matches


def validate_allowlist(allowlist: dict[str, Any]) -> list[str]:
    """Validate exact-path allowlist metadata before evaluating matches."""
    errors: list[str] = []
    entries = allowlist.get("entries", [])
    if not isinstance(entries, list):
        return ["allowlist entries must be a list"]
    for index, entry in enumerate(entries, 1):
        if not isinstance(entry, dict):
            errors.append(f"allowlist entry {index} must be an object")
            continue
        path = entry.get("path", "")
        if not isinstance(path, str) or any(char in path for char in "*?[]") or not path:
            errors.append(f"allowlist entry {index} path must be exact")
        for field in sorted(REQUIRED_FIELDS - entry.keys()):
            errors.append(f"allowlist entry {index} missing {field}")
    return errors


def validate_matches(
    matches: list[LegacyMatch],
    allowlist: dict[str, Any],
    *,
    repo_root: Path,
) -> list[str]:
    """Return policy violations for detected legacy matches."""
    errors = validate_allowlist(allowlist)
    entries = {
        entry.get("path"): entry
        for entry in allowlist.get("entries", [])
        if isinstance(entry, dict) and isinstance(entry.get("path"), str)
    }
    grouped: dict[str, list[LegacyMatch]] = {}
    for match in matches:
        grouped.setdefault(match.path, []).append(match)
        if match.path not in entries:
            errors.append(
                f"{match.path}:{match.line}: unallowlisted legacy token: {match.token.lower()}"
            )

    for path, entry in entries.items():
        path_matches = grouped.get(path, [])
        max_matches = entry.get("max_matches", -1)
        if isinstance(max_matches, int) and len(path_matches) > max_matches:
            errors.append(
                f"{path}: legacy matches {len(path_matches)} exceed allowed maximum {max_matches}"
            )
        if entry.get("classification") == "historical-document" and path_matches:
            try:
                document = (repo_root / path).read_text(encoding="utf-8")
            except (UnicodeDecodeError, IsADirectoryError, FileNotFoundError):
                document = ""
            if "Legacy / Historical" not in document:
                errors.append(f"{path}: historical document is missing 'Legacy / Historical' banner")
    return errors


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description="Enforce the PrismOS brand boundary")
    parser.add_argument(
        "--allowlist",
        type=Path,
        default=repo_root / "config" / "brand-legacy-allowlist.json",
    )
    args = parser.parse_args()
    allowlist = json.loads(args.allowlist.read_text(encoding="utf-8"))
    paths = tracked_paths(repo_root)
    matches = scan_paths(repo_root, paths)
    errors = validate_matches(matches, allowlist, repo_root=repo_root)
    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 1
    print(f"PrismOS brand gate passed: {len(paths)} tracked files, {len(matches)} allowlisted matches")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
