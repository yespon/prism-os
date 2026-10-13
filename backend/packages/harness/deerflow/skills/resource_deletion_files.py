"""Owned resource quarantine/reclamation using original scoped operation receipts."""

import hashlib
import json
import os
import re
import stat
from pathlib import Path, PurePosixPath

from deerflow.skills.install_receipts import InvalidSkillReceipt, publish_no_replace

DELETE_STATES = {"delete_prepared", "delete_quarantined", "delete_withdrawn", "delete_reclaiming", "delete_reclaimed"}


def identity(info):
    return [info.st_dev, info.st_ino]


def validate_delete_receipt(record, relative, operation_id):
    if record.get("schema_version") != "prismos.skill-install.v1" or record.get("operation_id") != operation_id or record.get("scope") != relative.as_posix():
        raise InvalidSkillReceipt("Deletion receipt scope is unavailable")
    if not isinstance(record.get("skill_name"), str) or not re.fullmatch(r"[a-z0-9_-]{1,64}", record["skill_name"]):
        raise InvalidSkillReceipt("Deletion receipt name is unavailable")
    if record.get("stage_name") != ".prismos-stage-" + operation_id or (not isinstance(record.get("state"), str) or record["state"] not in DELETE_STATES):
        raise InvalidSkillReceipt("Deletion receipt phase is unavailable")
    if not isinstance(record.get("target_kind"), str) or record.get("target_kind") not in {"owned", "missing", "public_override"} or not isinstance(record.get("resource_id"), str) or not record["resource_id"].startswith("skill:"):
        raise InvalidSkillReceipt("Deletion receipt instance is unavailable")
    if not isinstance(record.get("selected_resource_id"), str):
        raise InvalidSkillReceipt("Deletion selected instance is unavailable")
    tree = record.get("tree")
    if not isinstance(tree, dict) or set(tree) != {"directories", "files"} or not isinstance(tree["directories"], dict) or not isinstance(tree["files"], dict):
        raise InvalidSkillReceipt("Deletion receipt tree is unavailable")
    for kind in ["directories", "files"]:
        for name, entry in tree[kind].items():
            if not isinstance(name, str) or not name or PurePosixPath(name).is_absolute() or ".." in PurePosixPath(name).parts or (name == "." and kind == "files"):
                raise InvalidSkillReceipt("Deletion receipt member is unavailable")
            if not isinstance(entry, dict) or not isinstance(entry.get("identity"), list) or len(entry["identity"]) != 2 or any(type(value) is not int for value in entry["identity"]):
                raise InvalidSkillReceipt("Deletion receipt member identity is unavailable")
            if kind == "files" and (not isinstance(entry.get("sha256"), str) or not re.fullmatch(r"[0-9a-f]{64}", entry["sha256"])):
                raise InvalidSkillReceipt("Deletion receipt member digest is unavailable")
    if record["target_kind"] == "owned" and ("." not in tree["directories"] or tree["directories"]["."].get("identity") != record.get("directory_identity")):
        raise InvalidSkillReceipt("Deletion directory identity is unavailable")
    if record["target_kind"] != "owned" and (tree["directories"] or tree["files"] or record.get("directory_identity") is not None):
        raise InvalidSkillReceipt("Non-owned deletion cannot contain a reclaimable tree")
    if not isinstance(record.get("source_operations"), list) or any(not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{32}", value) for value in record["source_operations"]):
        raise InvalidSkillReceipt("Deletion source operations are unavailable")


def tree_digest(tree):
    return hashlib.sha256(json.dumps(tree, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _snapshot(fd, prefix="."):
    tree = {"directories": {prefix: {"identity": identity(os.fstat(fd))}}, "files": {}}
    for name in sorted(os.listdir(fd)):
        info = os.stat(name, dir_fd=fd, follow_symlinks=False)
        relative = name if prefix == "." else prefix + "/" + name
        if stat.S_ISDIR(info.st_mode):
            child = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            try:
                if identity(os.fstat(child)) != identity(info):
                    raise ValueError("Deletion directory changed")
                part = _snapshot(child, relative)
                for kind in tree:
                    tree[kind].update(part[kind])
            finally:
                os.close(child)
        elif stat.S_ISREG(info.st_mode):
            child = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=fd)
            with os.fdopen(child, "rb") as file:
                before = os.fstat(file.fileno())
                digest = hashlib.sha256(file.read()).hexdigest()
                after = os.fstat(file.fileno())
                if identity(before) != identity(info) or (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
                    raise ValueError("Deletion file changed")
                tree["files"][relative] = {"identity": identity(before), "sha256": digest}
        else:
            raise ValueError("Deletion tree contains an alias or non-regular member")
    return tree


class OwnedRemoval:
    def __init__(self, parent: Path):
        if not hasattr(os, "O_NOFOLLOW") or os.open not in os.supports_dir_fd:
            raise ValueError("Descriptor-safe deletion is unavailable")
        self.parent = parent
        self.fd = os.open(parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        self.parent_identity = identity(os.fstat(self.fd))
        self.check_parent()

    def check_parent(self):
        if self.parent.resolve() != self.parent or identity(self.parent.lstat()) != self.parent_identity:
            raise ValueError("Deletion scope changed; contents preserved")

    def snapshot(self, name):
        self.check_parent()
        child = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=self.fd)
        try:
            before = identity(os.fstat(child))
            tree = _snapshot(child)
            if identity(os.stat(name, dir_fd=self.fd, follow_symlinks=False)) != before:
                raise ValueError("Deletion directory was replaced")
            return tree
        finally:
            os.close(child)

    def exists(self, name):
        self.check_parent()
        try:
            os.stat(name, dir_fd=self.fd, follow_symlinks=False)
            return True
        except FileNotFoundError:
            return False

    def quarantine(self, record):
        self.check_parent()
        if self.snapshot(record["skill_name"]) != record["tree"]:
            raise ValueError("Deletion contents changed before quarantine")
        publish_no_replace(self.parent / record["skill_name"], self.parent / record["stage_name"], parent_descriptor=self.fd)
        if self.snapshot(record["stage_name"]) != record["tree"]:
            raise ValueError("Moved directory differs from deletion selection; contents preserved")

    def remaining(self, record):
        if not self.exists(record["stage_name"]):
            return None
        actual = self.snapshot(record["stage_name"])
        for kind in actual:
            if any(record["tree"][kind].get(name) != value for name, value in actual[kind].items()):
                raise ValueError("Reclamation contents or ownership changed; contents preserved")
        return actual

    def reclaim(self, record):
        actual = self.remaining(record)
        if actual is None:
            return
        child = os.open(record["stage_name"], os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=self.fd)
        try:
            if identity(os.fstat(child)) != record["directory_identity"]:
                raise ValueError("Reclamation directory changed")
            self._remove(child, ".", record["tree"])
            self.check_parent()
            if identity(os.stat(record["stage_name"], dir_fd=self.fd, follow_symlinks=False)) != record["directory_identity"]:
                raise ValueError("Reclamation root was replaced")
            os.rmdir(record["stage_name"], dir_fd=self.fd)
            os.fsync(self.fd)
        finally:
            os.close(child)

    def _remove(self, fd, prefix, expected):
        # A full remaining-tree check happens before unlinking; each member is
        # rechecked through the held directory descriptor immediately before use.
        for name in sorted(os.listdir(fd)):
            relative = name if prefix == "." else prefix + "/" + name
            info = os.stat(name, dir_fd=fd, follow_symlinks=False)
            if stat.S_ISDIR(info.st_mode):
                entry = expected["directories"].get(relative)
                if entry is None or identity(info) != entry["identity"]:
                    raise ValueError("Reclamation directory changed")
                child = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                try:
                    if identity(os.fstat(child)) != entry["identity"]:
                        raise ValueError("Reclamation directory replaced")
                    self._remove(child, relative, expected)
                    if identity(os.stat(name, dir_fd=fd, follow_symlinks=False)) != entry["identity"]:
                        raise ValueError("Reclamation directory replaced")
                    os.rmdir(name, dir_fd=fd)
                finally:
                    os.close(child)
            elif stat.S_ISREG(info.st_mode):
                entry = expected["files"].get(relative)
                if entry is None or identity(info) != entry["identity"]:
                    raise ValueError("Reclamation file changed")
                child = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=fd)
                with os.fdopen(child, "rb") as file:
                    if identity(os.fstat(file.fileno())) != entry["identity"] or hashlib.sha256(file.read()).hexdigest() != entry["sha256"]:
                        raise ValueError("Reclamation file contents changed")
                if identity(os.stat(name, dir_fd=fd, follow_symlinks=False)) != entry["identity"]:
                    raise ValueError("Reclamation file replaced")
                os.unlink(name, dir_fd=fd)
            else:
                raise ValueError("Reclamation contains an alias")
        os.fsync(fd)

    def close(self):
        os.close(self.fd)
