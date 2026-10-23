"""R5 extension package registry contracts."""

import json

import pytest

from app.extensions import ExtensionError, ExtensionRegistry, load_manifest


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


def test_manifest_validation(tmp_path):
    manifest, digest = load_manifest(_package(tmp_path))
    assert manifest.name == "skill-pack" and manifest.version == "1.0.0"
    assert manifest.permissions == ("knowledge.read",)
    assert len(digest) == 64

    # Missing required keys refused.
    bad = _package(tmp_path / "x")
    (bad / "manifest.json").write_text('{"name": "only-name"}')
    with pytest.raises(ExtensionError, match="name, version, permissions"):
        load_manifest(bad / "manifest.json")


def test_install_records_permissions_and_digest(tmp_path):
    registry = ExtensionRegistry()
    installed = registry.install(_package(tmp_path, permissions=["knowledge.read", "files.read"]),
                                 installed_by="admin-1")
    assert installed.manifest.permissions == ("knowledge.read", "files.read")
    assert installed.enabled is True
    assert registry.get(installed.id).manifest_sha256 == installed.manifest_sha256


def test_declared_entry_must_exist(tmp_path):
    registry = ExtensionRegistry()
    directory = _package(tmp_path, entry="main.js")
    (directory / "main.js").unlink()  # declared but missing
    with pytest.raises(ExtensionError, match="entry"):
        registry.install(directory, installed_by="admin-1")


def test_enable_disable_and_remove(tmp_path):
    registry = ExtensionRegistry()
    installed = registry.install(_package(tmp_path), installed_by="admin-1")

    disabled = registry.set_enabled(installed.id, enabled=False, by="admin-1")
    assert disabled.enabled is False

    registry.remove(installed.id, by="admin-1")
    with pytest.raises(ExtensionError):
        registry.get(installed.id)
