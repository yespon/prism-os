"""Extension package manifests and installation (R5, M7 minimal).

An extension package is a directory with a manifest.json declaring its
name, version, entry metadata, permissions and the files it ships. The
registry verifies the manifest digest before an install is recorded;
untrusted code is never loaded into the gateway process (red line) -
this slice only records and validates manifests.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from uuid import uuid4


class ExtensionError(Exception):
    """User-presentable extension package error."""


@dataclass(frozen=True)
class ExtensionManifest:
    name: str
    version: str
    permissions: tuple[str, ...] = ()
    description: str = ""
    entry: str | None = None


@dataclass
class ExtensionInstallation:
    id: str
    manifest: ExtensionManifest
    manifest_sha256: str
    installed_by: str
    enabled: bool = True


_REQUIRED_KEYS = {"name", "version", "permissions"}


def load_manifest(path: Path) -> tuple[ExtensionManifest, str]:
    """Load and validate a manifest.json; returns (manifest, sha256 of the file).

    Accepts either the manifest file itself or its containing directory.
    """
    if path.is_dir():
        path = path / "manifest.json"
    if not path.is_file():
        raise ExtensionError("manifest.json not found")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ExtensionError(f"invalid manifest JSON: {error}") from error
    if not isinstance(data, dict) or not _REQUIRED_KEYS <= set(data):
        raise ExtensionError("manifest must be an object with name, version, permissions")
    if not isinstance(data["permissions"], list) or not all(isinstance(p, str) for p in data["permissions"]):
        raise ExtensionError("permissions must be a list of strings")
    manifest = ExtensionManifest(
        name=str(data["name"]), version=str(data["version"]),
        permissions=tuple(data["permissions"]),
        description=str(data.get("description", "")),
        entry=data.get("entry"),
    )
    digest = sha256(path.read_bytes()).hexdigest()
    return manifest, digest


class ExtensionRegistry:
    """Records extension installations after manifest validation.

    Minimal slice: installations live in memory (the R5 real-deployment
    rehearsal exercises the API path; persistence lands with the R6 data
    work package). Permissions are recorded and exposed for the caller's
    policy decisions; the registry never executes package code.
    """

    def __init__(self) -> None:
        self._installations: dict[str, ExtensionInstallation] = {}

    def install(self, package_dir: Path, *, installed_by: str) -> ExtensionInstallation:
        manifest, digest = load_manifest(package_dir / "manifest.json")
        if manifest.entry and not (package_dir / manifest.entry).is_file():
            raise ExtensionError(f"declared entry {manifest.entry!r} missing from package")
        installation = ExtensionInstallation(
            id=f"ext_{uuid4().hex}", manifest=manifest, manifest_sha256=digest,
            installed_by=installed_by, enabled=True,
        )
        self._installations[installation.id] = installation
        return installation

    def get(self, installation_id: str) -> ExtensionInstallation:
        record = self._installations.get(installation_id)
        if record is None:
            raise ExtensionError("installation not found")
        return record

    def list(self) -> list[ExtensionInstallation]:
        return list(self._installations.values())

    def set_enabled(self, installation_id: str, *, enabled: bool, by: str) -> ExtensionInstallation:
        record = self.get(installation_id)
        record.enabled = enabled
        return record

    def remove(self, installation_id: str, *, by: str) -> None:
        self.get(installation_id)  # raises when unknown
        del self._installations[installation_id]
