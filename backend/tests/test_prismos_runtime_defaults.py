import os
from pathlib import Path

from deerflow.config.app_config import AppConfig
from deerflow.config.database_config import DatabaseConfig
from deerflow.config.paths import Paths
from deerflow.storage.local import _load_storage_config
from deerflow.storage.provider import StorageProviderConfig


def test_new_install_defaults_use_prismos(monkeypatch, tmp_path: Path) -> None:
    for name in list(os.environ):
        if name.startswith(("PRISMOS_", "OPSINTECH_")):
            monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    assert Paths().base_dir == tmp_path / ".prismos"
    assert DatabaseConfig().url.endswith("/.prismos/tenant.db")
    assert StorageProviderConfig().s3_bucket_name == "prismos-files"
    assert StorageProviderConfig().juicefs_subdir == "prismos-files"


def test_legacy_config_path_is_read_only_through_adapter(monkeypatch, tmp_path: Path) -> None:
    config = tmp_path / "legacy.yaml"
    config.write_text("sandbox:\n  use: local\n", encoding="utf-8")
    monkeypatch.delenv("PRISMOS_CONFIG_PATH", raising=False)
    monkeypatch.setenv("OPSINTECH_CONFIG_PATH", str(config))
    assert AppConfig.resolve_config_path() == config


def test_storage_new_variable_wins(monkeypatch) -> None:
    monkeypatch.setenv("PRISMOS_STORAGE_BACKEND", "local")
    monkeypatch.setenv("OPSINTECH_STORAGE_BACKEND", "s3")
    assert _load_storage_config().backend == "local"


def test_existing_legacy_home_is_reported_but_not_selected(monkeypatch, tmp_path, caplog) -> None:
    legacy = tmp_path / ".opsintech"
    legacy.mkdir()
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("PRISMOS_HOME", raising=False)
    monkeypatch.delenv("OPSINTECH_HOME", raising=False)
    assert Paths().base_dir == tmp_path / ".prismos"
    assert str(legacy) in caplog.text
