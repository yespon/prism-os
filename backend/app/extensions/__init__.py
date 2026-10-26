"""Extension package manifests and installation (R5 leftover -> R6 persistence).

An extension package is a directory with a manifest.json declaring its
name, version, entry metadata, permissions and the files it ships. The
registry verifies the manifest digest before an install is recorded;
untrusted code is never loaded into the gateway process (red line) -
this module only records and validates manifests.

Installations persist in the extension_installations table (one row per
install, with the manifest and its digest); enable/disable and remove
mutate the row. Reads are tenant-scoped.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from uuid import uuid4

from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from deerflow.database.session import get_session_factory


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
    tenant_id: str
    manifest: ExtensionManifest
    manifest_sha256: str
    installed_by: str
    enabled: bool = True


_REQUIRED_KEYS = {"name", "version", "permissions"}


def load_manifest(path: Path) -> tuple[ExtensionManifest, str, dict]:
    """Load and validate a manifest.json.

    Returns (manifest, sha256 of the file, parsed json) - the raw json is
    persisted alongside so the row is self-describing.
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
    return manifest, digest, data


def _to_installation(row) -> ExtensionInstallation:
    return ExtensionInstallation(
        id=row.id, tenant_id=row.tenant_id,
        manifest=ExtensionManifest(
            name=row.name, version=row.version,
            permissions=tuple(json.loads(row.permissions_json)),
        ),
        manifest_sha256=row.manifest_sha256,
        installed_by=row.installed_by,
        enabled=row.enabled,
    )


class ExtensionRegistry:
    """Records extension installations after manifest validation.

    Installations persist in the extension_installations table; the
    registry never executes package code (gateway-process red line).
    """

    def __init__(self, session_factory: async_sessionmaker[AsyncSession] | None = None,
                 tenant_id: str = "") -> None:
        self._session_factory = session_factory or get_session_factory()
        self._tenant_id = tenant_id

    async def install(self, package_dir: Path, *, installed_by: str) -> ExtensionInstallation:
        manifest, digest, raw = load_manifest(package_dir / "manifest.json")
        if manifest.entry and not (package_dir / manifest.entry).is_file():
            raise ExtensionError(f"declared entry {manifest.entry!r} missing from package")
        from app.models.extensions import ExtensionInstallationRecord

        installation = ExtensionInstallation(
            id=f"ext_{uuid4().hex}", tenant_id=self._tenant_id,
            manifest=manifest, manifest_sha256=digest,
            installed_by=installed_by, enabled=True,
        )
        record = ExtensionInstallationRecord(
            id=installation.id, tenant_id=self._tenant_id,
            name=manifest.name, version=manifest.version,
            manifest_sha256=digest,
            manifest_json=json.dumps(raw, sort_keys=True, ensure_ascii=False),
            permissions_json=json.dumps(list(manifest.permissions)),
            installed_by=installed_by, enabled=True,
            created_at=datetime.now(UTC),
        )
        async with self._session_factory() as session, session.begin():
            session.add(record)
        return installation

    async def get(self, installation_id: str) -> ExtensionInstallation:
        from app.models.extensions import ExtensionInstallationRecord

        async with self._session_factory() as session:
            row = await session.get(ExtensionInstallationRecord, installation_id)
        if row is None or row.tenant_id != self._tenant_id:
            raise ExtensionError("installation not found")
        return _to_installation(row)

    async def list(self) -> list[ExtensionInstallation]:
        from app.models.extensions import ExtensionInstallationRecord

        async with self._session_factory() as session:
            rows = (await session.exec(
                select(ExtensionInstallationRecord).where(
                    ExtensionInstallationRecord.tenant_id == self._tenant_id)
            )).all()
        return [_to_installation(row) for row in rows]

    async def set_enabled(self, installation_id: str, *, enabled: bool, by: str) -> ExtensionInstallation:
        from app.models.extensions import ExtensionInstallationRecord

        async with self._session_factory() as session, session.begin():
            row = await session.get(ExtensionInstallationRecord, installation_id)
        if row is None or row.tenant_id != self._tenant_id:
            raise ExtensionError("installation not found")
        row.enabled = enabled
        async with self._session_factory() as session, session.begin():
            session.add(row)
        return _to_installation(row)

    async def remove(self, installation_id: str, *, by: str) -> None:
        from app.models.extensions import ExtensionInstallationRecord

        async with self._session_factory() as session, session.begin():
            row = await session.get(ExtensionInstallationRecord, installation_id)
            if row is None or row.tenant_id != self._tenant_id:
                raise ExtensionError("installation not found")
            await session.delete(row)
