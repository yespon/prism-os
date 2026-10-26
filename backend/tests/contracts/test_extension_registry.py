"""R6: extension registry persistence contracts."""

import json

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from app.extensions import ExtensionError, ExtensionRegistry, load_manifest
from app.models import extensions as _extension_models  # noqa: F401


def _package(tmp_path, *, name="skill-pack", version="1.0.0", permissions=None, entry=None):
    directory = tmp_path / "pkg"
    directory.mkdir(parents=True, exist_ok=True)
    manifest = {"name": name, "version": version,
                "permissions": permissions if permissions is not None else ["knowledge.read"]}
    if entry is not None:
        manifest["entry"] = entry
        (directory / entry).write_text("# entry")
    (directory / "manifest.json").write_text(json.dumps(manifest))
    return directory


@pytest.fixture
async def registry(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'extensions.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(SQLModel.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    yield ExtensionRegistry(factory, tenant_id="t1"), factory
    await engine.dispose()


def test_manifest_validation(tmp_path):
    manifest, digest, raw = load_manifest(_package(tmp_path))
    assert manifest.name == "skill-pack" and manifest.version == "1.0.0"
    assert manifest.permissions == ("knowledge.read",)
    assert len(digest) == 64 and raw["version"] == "1.0.0"

    bad = _package(tmp_path / "x")
    (bad / "manifest.json").write_text('{"name": "only-name"}')
    with pytest.raises(ExtensionError, match="name, version, permissions"):
        load_manifest(bad / "manifest.json")


@pytest.mark.anyio
async def test_install_persists_and_rereads(registry, tmp_path):
    registry, factory = registry
    installed = await registry.install(
        _package(tmp_path, permissions=["knowledge.read", "files.read"]),
        installed_by="admin-1")
    assert installed.manifest.permissions == ("knowledge.read", "files.read")

    fresh = ExtensionRegistry(factory, tenant_id="t1")
    rows = await fresh.list()
    assert [r.id for r in rows] == [installed.id]
    assert rows[0].manifest.permissions == ("knowledge.read", "files.read")
    assert rows[0].enabled is True


@pytest.mark.anyio
async def test_declared_entry_must_exist(registry, tmp_path):
    registry, _factory = registry
    directory = _package(tmp_path, entry="main.js")
    (directory / "main.js").unlink()
    with pytest.raises(ExtensionError, match="entry"):
        await registry.install(directory, installed_by="admin-1")


@pytest.mark.anyio
async def test_enable_disable_and_remove(registry, tmp_path):
    registry, _factory = registry
    installed = await registry.install(_package(tmp_path), installed_by="admin-1")

    disabled = await registry.set_enabled(installed.id, enabled=False, by="admin-1")
    assert disabled.enabled is False

    await registry.remove(installed.id, by="admin-1")
    with pytest.raises(ExtensionError):
        await registry.get(installed.id)


@pytest.mark.anyio
async def test_tenant_isolation(registry, tmp_path):
    registry, factory = registry
    installed = await registry.install(_package(tmp_path), installed_by="admin-1")

    other = ExtensionRegistry(factory, tenant_id="t2")
    assert await other.list() == []
    with pytest.raises(ExtensionError):
        await other.get(installed.id)
    with pytest.raises(ExtensionError):
        await other.set_enabled(installed.id, enabled=False, by="x")
