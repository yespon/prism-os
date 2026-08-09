"""Explicit, reversible migration of the legacy PrismOS home directory."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

_MANIFEST_NAME = ".prismos-migration-manifest.json"
_MANIFEST_SCHEMA_VERSION = 1
_MINIMUM_SAFETY_MARGIN = 1024 * 1024


@dataclass(frozen=True)
class FileRecord:
    relative_path: str
    size: int
    sha256: str


@dataclass(frozen=True)
class MigrationPlan:
    source: Path
    target: Path
    temporary_target: Path
    files: tuple[FileRecord, ...]
    total_bytes: int
    manifest_path: Path

    @property
    def file_count(self) -> int:
        return len(self.files)


@dataclass(frozen=True)
class ManifestVerification:
    valid: bool
    checked_files: int
    errors: tuple[str, ...]


@dataclass(frozen=True)
class MigrationResult:
    target: Path
    manifest_path: Path
    verification: ManifestVerification


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _is_readable(path: Path) -> bool:
    return os.access(path, os.R_OK)


def _available_bytes(path: Path) -> int:
    return shutil.disk_usage(path).free


def _nearest_existing_parent(path: Path) -> Path:
    candidate = path
    while not candidate.exists():
        parent = candidate.parent
        if parent == candidate:
            return candidate
        candidate = parent
    return candidate


def _open_files_under(source: Path) -> tuple[Path, ...]:
    """Return open paths reported by lsof, without exposing process metadata."""
    lsof = shutil.which("lsof")
    if lsof is None:
        return ()
    try:
        result = subprocess.run(
            [lsof, "-Fn", "+D", str(source)],
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError:
        return ()

    resolved_source = source.resolve()
    paths: set[Path] = set()
    for line in result.stdout.splitlines():
        if not line.startswith("n"):
            continue
        candidate = Path(line[1:])
        try:
            candidate = candidate.resolve()
            candidate.relative_to(resolved_source)
        except (OSError, ValueError):
            continue
        paths.add(candidate)
    return tuple(sorted(paths))


def _validate_location(source: Path, target: Path) -> tuple[Path, Path]:
    if source.is_symlink():
        raise ValueError(f"Source path is a symbolic link: {source}")
    if not source.exists() or not source.is_dir():
        raise FileNotFoundError(f"Migration source directory not found: {source}")
    if os.path.lexists(target):
        raise FileExistsError(f"Migration target already exists: {target}")

    resolved_source = source.resolve()
    resolved_target = target.resolve()
    try:
        resolved_target.relative_to(resolved_source)
    except ValueError:
        pass
    else:
        raise ValueError("Migration target cannot be inside the source directory")
    return resolved_source, resolved_target


def _collect_files(source: Path) -> tuple[FileRecord, ...]:
    records: list[FileRecord] = []
    for path in sorted(source.rglob("*")):
        relative = path.relative_to(source)
        if path.is_symlink():
            raise ValueError(f"Source contains a symbolic link: {relative}")
        if path.is_dir():
            if not _is_readable(path):
                raise PermissionError(f"Source directory is not readable: {relative}")
            continue
        if not path.is_file():
            raise ValueError(f"Source contains unsupported special file: {relative}")
        if not _is_readable(path):
            raise PermissionError(f"Source file is not readable: {relative}")
        stat = path.stat()
        records.append(FileRecord(str(relative), stat.st_size, _hash_file(path)))
    return tuple(records)


def plan_home_migration(source: Path, target: Path) -> MigrationPlan:
    """Validate and describe a migration without creating or changing paths."""
    resolved_source, resolved_target = _validate_location(Path(source), Path(target))
    open_files = _open_files_under(resolved_source)
    if open_files:
        names = ", ".join(str(path) for path in open_files)
        raise RuntimeError(f"Migration source has open file(s): {names}")

    records = _collect_files(resolved_source)
    total_bytes = sum(record.size for record in records)
    required_bytes = total_bytes + max(total_bytes // 10, _MINIMUM_SAFETY_MARGIN)
    available = _available_bytes(_nearest_existing_parent(resolved_target.parent))
    if available < required_bytes:
        raise OSError(
            f"Insufficient disk space: requires {required_bytes} bytes, has {available}"
        )

    temporary_target = resolved_target.parent / f".{resolved_target.name}.migrating-{uuid4().hex}"
    return MigrationPlan(
        source=resolved_source,
        target=resolved_target,
        temporary_target=temporary_target,
        files=records,
        total_bytes=total_bytes,
        manifest_path=resolved_target / _MANIFEST_NAME,
    )


def _copy_record(source: Path, temporary_target: Path, record: FileRecord) -> None:
    source_path = source / record.relative_path
    destination = temporary_target / record.relative_path
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source_path, destination)


def _manifest_payload(plan: MigrationPlan) -> dict[str, object]:
    return {
        "schema_version": _MANIFEST_SCHEMA_VERSION,
        "created_at": datetime.now(UTC).isoformat(),
        "source": str(plan.source),
        "target": str(plan.target),
        "status": "verified",
        "total_bytes": plan.total_bytes,
        "files": [
            {
                "relative_path": record.relative_path,
                "size": record.size,
                "sha256": record.sha256,
            }
            for record in plan.files
        ],
    }


def _write_manifest(path: Path, payload: dict[str, object]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())


def _fsync_directory(path: Path) -> None:
    try:
        descriptor = os.open(path, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _verify_records(root: Path, records: list[dict[str, object]]) -> ManifestVerification:
    errors: list[str] = []
    checked = 0
    for item in records:
        relative = item.get("relative_path")
        if not isinstance(relative, str) or not relative:
            errors.append("invalid: relative_path")
            continue
        candidate = (root / relative).resolve()
        try:
            candidate.relative_to(root.resolve())
        except ValueError:
            errors.append(f"escapes: {relative}")
            continue
        if not candidate.is_file():
            errors.append(f"missing: {relative}")
            continue
        checked += 1
        expected_size = item.get("size")
        expected_hash = item.get("sha256")
        actual_size = candidate.stat().st_size
        if actual_size != expected_size:
            errors.append(f"size mismatch: {relative}")
            continue
        if _hash_file(candidate) != expected_hash:
            errors.append(f"checksum mismatch: {relative}")
    return ManifestVerification(not errors, checked, tuple(errors))


def verify_manifest(manifest_path: Path) -> ManifestVerification:
    """Verify a migration manifest and every file under its target directory."""
    try:
        payload = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return ManifestVerification(False, 0, (f"manifest unreadable: {exc}",))
    if payload.get("schema_version") != _MANIFEST_SCHEMA_VERSION:
        return ManifestVerification(False, 0, ("invalid: schema_version",))
    if payload.get("status") != "verified":
        return ManifestVerification(False, 0, ("invalid: status",))
    records = payload.get("files")
    if not isinstance(records, list):
        return ManifestVerification(False, 0, ("invalid: files",))
    return _verify_records(Path(manifest_path).resolve().parent, records)


def apply_home_migration(plan: MigrationPlan) -> MigrationResult:
    """Copy, verify, and atomically activate one previously validated plan."""
    if os.path.lexists(plan.target):
        raise FileExistsError(f"Migration target already exists: {plan.target}")
    created_temporary = False
    try:
        plan.temporary_target.mkdir(parents=False)
        created_temporary = True
        for record in plan.files:
            _copy_record(plan.source, plan.temporary_target, record)
            copied = plan.temporary_target / record.relative_path
            if copied.stat().st_size != record.size or _hash_file(copied) != record.sha256:
                raise ValueError(f"checksum mismatch: {record.relative_path}")

        manifest_in_temporary = plan.temporary_target / plan.manifest_path.name
        _write_manifest(manifest_in_temporary, _manifest_payload(plan))
        _fsync_directory(plan.temporary_target)
        if os.path.lexists(plan.target):
            raise FileExistsError(f"Migration target appeared during migration: {plan.target}")
        plan.temporary_target.replace(plan.target)
        created_temporary = False
        _fsync_directory(plan.target.parent)
        verification = verify_manifest(plan.manifest_path)
        if not verification.valid:
            raise ValueError("manifest verification failed: " + "; ".join(verification.errors))
        return MigrationResult(plan.target, plan.manifest_path, verification)
    except Exception:
        if created_temporary and plan.temporary_target.exists():
            shutil.rmtree(plan.temporary_target)
        raise
