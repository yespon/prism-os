"""Filesystem ownership receipts for Skill import; TenantSkill remains authoritative."""

from __future__ import annotations

import ctypes
import errno
import hashlib
import json
import os
import re
import shutil
import stat
import sys
import tempfile
import uuid
from pathlib import Path

_OPERATION = re.compile(r"^[0-9a-f]{32}$")
_NAME = re.compile(r"^[a-z0-9-]+$")
SCHEMA = "prismos.skill-install.v1"


class InvalidSkillReceipt(ValueError):
    pass


def scoped_parent(root: Path, scope: str | Path | None, *, create: bool = False) -> tuple[Path, Path]:
    relative = Path(scope) if scope is not None else Path()
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError("Skill install target must be a safe relative path")
    base = root.resolve() / "custom"
    parent = base / relative
    if parent.resolve() != parent:
        raise ValueError("Skill installation scope contains a filesystem alias")
    if create:
        missing = []
        cursor = parent
        while not cursor.exists():
            missing.append(cursor)
            cursor = cursor.parent
        parent.mkdir(parents=True, exist_ok=True)
        for directory in reversed(missing):
            sync_directory(directory.parent)
        if parent.resolve() != parent:
            raise ValueError("Skill installation scope contains a filesystem alias")
    return parent, relative


def file_hashes(folder: Path, *, sync: bool = False) -> dict[str, str]:
    values = {}
    if not folder.is_dir() or folder.is_symlink():
        raise ValueError("Skill installation directory is unavailable")
    for path in sorted(folder.rglob("*")):
        if path.is_symlink() or path.resolve() != path.absolute():
            raise ValueError("Skill installation contains a filesystem alias")
        if path.is_dir():
            continue
        if not stat.S_ISREG(path.stat().st_mode):
            raise ValueError("Skill installation contains a non-regular file")
        digest = hashlib.sha256()
        with path.open("rb") as file:
            for chunk in iter(lambda: file.read(1024 * 1024), b""):
                digest.update(chunk)
            if sync:
                os.fsync(file.fileno())
        values[path.relative_to(folder).as_posix()] = digest.hexdigest()
    if sync:
        for directory in sorted((p for p in folder.rglob("*") if p.is_dir()), reverse=True):
            sync_directory(directory)
        sync_directory(folder)
    return values


def sync_directory(path: Path) -> None:
    if os.name == "nt":
        return  # Directory fsync is not available through the Windows stdlib.
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def publish_no_replace(source: Path, target: Path, *, parent_descriptor: int | None = None) -> None:
    """Same-filesystem exclusive rename; never emulate with overwriting rename."""
    if parent_descriptor is not None:
        if not sys.platform.startswith("linux"):
            raise OSError(errno.ENOTSUP, "Descriptor-safe Skill movement is unavailable")
        libc = ctypes.CDLL(None, use_errno=True)
        if not hasattr(libc, "renameat2"):
            raise OSError(errno.ENOTSUP, "Descriptor-safe Skill movement is unavailable")
        call = libc.renameat2
        call.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
        call.restype = ctypes.c_int
        result = call(parent_descriptor, os.fsencode(source.name), parent_descriptor, os.fsencode(target.name), 1)
        if result:
            code = ctypes.get_errno()
            if code in {errno.EEXIST, errno.ENOTEMPTY}:
                raise FileExistsError(code, "Skill destination already exists")
            raise OSError(code, "Descriptor-safe Skill movement failed")
        os.fsync(parent_descriptor)
        return
    if os.name == "nt":
        os.rename(source, target)  # Windows rename refuses an existing destination.
        return
    libc = ctypes.CDLL(None, use_errno=True)
    if sys.platform.startswith("linux") and hasattr(libc, "renameat2"):
        call = libc.renameat2
        call.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
        call.restype = ctypes.c_int
        parent_fd = os.open(target.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            result = call(parent_fd, os.fsencode(source.name), parent_fd, os.fsencode(target.name), 1)  # RENAME_NOREPLACE
        finally:
            os.close(parent_fd)
    elif sys.platform == "darwin" and hasattr(libc, "renamex_np"):
        call = libc.renamex_np
        call.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_uint]
        call.restype = ctypes.c_int
        result = call(os.fsencode(source), os.fsencode(target), 4)  # RENAME_EXCL
    else:
        raise OSError(errno.ENOTSUP, "Exclusive Skill publication is unavailable")
    if result:
        code = ctypes.get_errno()
        if code in {errno.EEXIST, errno.ENOTEMPTY}:
            raise FileExistsError(code, "Skill destination already exists")
        raise OSError(code, "Exclusive Skill publication failed")
    sync_directory(target.parent)


def receipt_path(parent: Path, operation_id: str) -> Path:
    if not _OPERATION.fullmatch(operation_id):
        raise FileNotFoundError("Skill import operation not found")
    return parent / f".prismos-import-{operation_id}.json"


def write_receipt(parent: Path, record: dict, *, initial: bool = False) -> None:
    path = receipt_path(parent, record["operation_id"])
    data = (json.dumps(record, sort_keys=True, ensure_ascii=False, indent=2) + "\n").encode()
    if path.is_symlink() or path.resolve() != path.absolute():
        raise ValueError("Skill import receipt alias is unavailable")
    with tempfile.NamedTemporaryFile(dir=parent, prefix=".prismos-receipt-", delete=False) as file:
        temporary = Path(file.name)
        try:
            file.write(data)
            file.flush()
            os.fsync(file.fileno())
        except BaseException:
            temporary.unlink(missing_ok=True)
            raise
    try:
        if initial:
            publish_no_replace(temporary, path)
        else:
            os.replace(temporary, path)
            sync_directory(parent)
    finally:
        temporary.unlink(missing_ok=True)


def validate_manual_creation(value: dict) -> None:
    if not isinstance(value, dict) or set(value) != {"enabled", "category", "configuration_phase"}:
        raise InvalidSkillReceipt("Manual creation intent is unavailable")
    if type(value["enabled"]) is not bool or not isinstance(value["category"], str) or not value["category"].strip() or value["category"].strip().lower() == "public":
        raise InvalidSkillReceipt("Manual creation registration intent is unavailable")
    if not isinstance(value["configuration_phase"], str) or value["configuration_phase"] not in {"pending", "confirmed", "unknown"}:
        raise InvalidSkillReceipt("Manual creation configuration phase is unavailable")


def read_receipt(root: Path, scope: str | Path | None, operation_id: str) -> dict:
    parent, relative = scoped_parent(root, scope)
    path = receipt_path(parent, operation_id)
    if not path.is_file():
        raise FileNotFoundError("Skill import operation not found")
    if path.is_symlink() or path.resolve() != path.absolute():
        raise InvalidSkillReceipt("Skill import receipt alias is unavailable")
    try:
        value = json.loads(path.read_text())
    except (OSError, ValueError):
        raise InvalidSkillReceipt("Skill import receipt is unavailable") from None
    if not isinstance(value, dict):
        raise InvalidSkillReceipt("Skill import receipt is unavailable")
    name = value.get("skill_name")
    state = value.get("state")
    if value.get("kind") == "resource_delete":
        from deerflow.skills.resource_deletion_files import validate_delete_receipt

        validate_delete_receipt(value, relative, operation_id)
        return value
    if not isinstance(name, str) or not isinstance(state, str) or state not in {"allocated", "staging", "prepared", "published", "registered", "registration_observed", "registration_unknown", "aborted", "withdrawn"}:
        raise InvalidSkillReceipt("Skill import receipt state is unavailable")
    if value.get("schema_version") != SCHEMA or value.get("operation_id") != operation_id or value.get("scope") != relative.as_posix() or not _NAME.fullmatch(name):
        raise InvalidSkillReceipt("Skill import receipt scope is unavailable")
    if value.get("stage_name") != f".prismos-stage-{operation_id}":
        raise InvalidSkillReceipt("Skill import receipt stage is unavailable")
    if "manual_creation" in value:
        validate_manual_creation(value["manual_creation"])
    return value


def verified_publication(root: Path, scope: str | Path | None, operation_id: str) -> tuple[dict, Path]:
    parent, _ = scoped_parent(root, scope)
    record = read_receipt(root, scope, operation_id)
    target = parent / record["skill_name"]
    if target.resolve() != target or not target.is_dir() or target.is_symlink():
        raise ValueError("Published Skill files are unavailable")
    current = target.stat()
    if [current.st_dev, current.st_ino] != record.get("directory_identity") or file_hashes(target) != record.get("files"):
        raise ValueError("Published Skill ownership or contents changed")
    return record, target


def mark_registration(result: dict, state: str, *, row_id: int | None = None) -> None:
    operation_id = result.get("operation_id")
    if not operation_id:
        return  # Legacy/custom installation callers can still return their original contract.
    target = Path(result["install_dir"])
    path = receipt_path(target.parent, operation_id)
    record = json.loads(path.read_text())
    if record.get("operation_id") != operation_id or record.get("skill_name") != target.name or path.is_symlink():
        raise ValueError("Skill import receipt is unavailable")
    if record.get("state") in {"registered", "registration_observed"} and state == "registration_unknown":
        return
    record["state"] = state
    if row_id is not None:
        record["row_id"] = row_id
    write_receipt(target.parent, record)


class PreparedSkill:
    """Private staged files. After publication, uncertainty never triggers deletion."""

    def __init__(self, root: Path, scope: str | Path | None, name: str, source: Path, archive: Path):
        self.parent, relative = scoped_parent(root, scope, create=True)
        self.target = self.parent / name
        self.operation_id = uuid.uuid4().hex
        self.stage = self.parent / f".prismos-stage-{self.operation_id}"
        archive_digest = hashlib.sha256()
        with archive.open("rb") as file:
            for chunk in iter(lambda: file.read(1024 * 1024), b""):
                archive_digest.update(chunk)
        self.record = {"schema_version": SCHEMA, "operation_id": self.operation_id, "scope": relative.as_posix(), "skill_name": name, "stage_name": self.stage.name, "state": "allocated", "archive_sha256": archive_digest.hexdigest()}
        self.published = False
        self.stage_identity = None
        write_receipt(self.parent, self.record, initial=True)
        try:
            if os.path.lexists(self.target):
                raise FileExistsError("Skill destination already exists")
            self.stage.mkdir(mode=0o700)
            info = self.stage.stat()
            self.stage_identity = [info.st_dev, info.st_ino]
            self.record.update(directory_identity=self.stage_identity, state="staging")
            write_receipt(self.parent, self.record)
            expected_files = file_hashes(source)
            self.record["files"] = expected_files
            write_receipt(self.parent, self.record)
            shutil.copytree(source, self.stage, dirs_exist_ok=True)
            copied_files = file_hashes(self.stage, sync=True)
            if copied_files != expected_files:
                raise ValueError("Staged Skill contents differ from the validated archive")
            from deerflow.skills.validation import _validate_skill_frontmatter

            valid, _, staged_name = _validate_skill_frontmatter(self.stage)
            if not valid or staged_name != name:
                raise ValueError("Staged Skill format differs from the validated archive")
            self.record.update(files=copied_files, state="prepared")
            write_receipt(self.parent, self.record)
        except BaseException:
            self.close()
            raise
        self.result = {
            "success": True,
            "skill_name": name,
            "category": "custom",
            "relative_path": (relative / name).as_posix(),
            "install_dir": str(self.target),
            "operation_id": self.operation_id,
            "message": f"Skill '{name}' installed successfully",
        }

    def publish(self) -> dict:
        info = self.stage.lstat()
        if self.parent.resolve() != self.parent or self.stage.is_symlink() or [info.st_dev, info.st_ino] != self.stage_identity or file_hashes(self.stage) != self.record["files"]:
            raise ValueError("Staged Skill ownership or contents changed")
        publish_no_replace(self.stage, self.target)
        self.published = True
        self.record["state"] = "published"
        write_receipt(self.parent, self.record)
        return dict(self.result)

    def publication_exists(self) -> bool:
        if self.stage_identity and self.target.is_dir() and not self.target.is_symlink():
            info = self.target.stat()
            return [info.st_dev, info.st_ino] == self.stage_identity
        return False

    def close(self) -> None:
        # Never compensate published content based only on a later Python exception.
        # A crash after rename is recognized by the moved directory identity.
        if self.publication_exists():
            self.published = True
        if self.published:
            return
        if self.stage_identity and self.stage.is_dir() and not self.stage.is_symlink():
            info = self.stage.stat()
            if [info.st_dev, info.st_ino] == self.stage_identity:
                shutil.rmtree(self.stage)
        self.record["state"] = "aborted"
        write_receipt(self.parent, self.record)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        self.close()


def verified_stage(root: Path, scope: str | Path | None, operation_id: str) -> tuple[dict, Path, Path]:
    parent, _ = scoped_parent(root, scope)
    record = read_receipt(root, scope, operation_id)
    if record["state"] not in {"prepared", "staging"}:
        raise ValueError("Skill import is not a recoverable staged publication")
    stage = parent / record["stage_name"]
    target = parent / record["skill_name"]
    if stage.resolve() != stage or not stage.is_dir() or stage.is_symlink():
        raise ValueError("Staged Skill directory is unavailable")
    info = stage.stat()
    if [info.st_dev, info.st_ino] != record.get("directory_identity") or file_hashes(stage) != record.get("files"):
        raise ValueError("Staged Skill ownership or contents changed")
    from deerflow.skills.validation import _validate_skill_frontmatter

    valid, _, name = _validate_skill_frontmatter(stage)
    if not valid or name != record["skill_name"]:
        raise ValueError("Staged Skill format is unavailable")
    return record, stage, target


def resume_publication(root: Path, scope: str | Path | None, operation_id: str) -> None:
    record, stage, target = verified_stage(root, scope, operation_id)
    publish_no_replace(stage, target)
    record["state"] = "published"
    write_receipt(target.parent, record)


def abort_staged_operation(root: Path, scope: str | Path | None, operation_id: str) -> None:
    parent, _ = scoped_parent(root, scope)
    record = read_receipt(root, scope, operation_id)
    if record["state"] not in {"allocated", "staging", "prepared", "aborted"}:
        raise ValueError("Published Skill content must use native resource management")
    target = parent / record["skill_name"]
    if target.is_dir() and not target.is_symlink():
        info = target.stat()
        if [info.st_dev, info.st_ino] == record.get("directory_identity"):
            raise ValueError("Published Skill content cannot be aborted as staged")
    stage = parent / record["stage_name"]
    if os.path.lexists(stage):
        if stage.resolve() != stage or not stage.is_dir() or stage.is_symlink():
            raise ValueError("Staged Skill ownership is unavailable")
        info = stage.stat()
        if [info.st_dev, info.st_ino] != record.get("directory_identity"):
            raise ValueError("Staged Skill ownership changed")
        shutil.rmtree(stage)
        sync_directory(parent)
    record["state"] = "aborted"
    write_receipt(parent, record)
