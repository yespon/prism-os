"""R6: extension installation migration extends the chain."""

import sqlite3
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

from alembic import command


def test_extension_migration_single_head_and_reversible(tmp_path) -> None:
    db_path = tmp_path / "extension-migration.db"
    config = Config(str(Path("alembic.ini").resolve()))
    config.set_main_option("sqlalchemy.url", f"sqlite+aiosqlite:///{db_path}")
    assert ScriptDirectory.from_config(config).get_heads() == ["u5o6p7q8r9s0"]

    command.upgrade(config, "head")
    with sqlite3.connect(db_path) as connection:
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert {"extension_installations", "evaluation_results", "agent_versions"} <= tables
        assert connection.execute("SELECT version_num FROM alembic_version").fetchone()[0] == "u5o6p7q8r9s0"

    command.downgrade(config, "t4n5o6p7q8r9")
    with sqlite3.connect(db_path) as connection:
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert "extension_installations" not in tables
        assert "evaluation_results" in tables
        assert connection.execute("SELECT version_num FROM alembic_version").fetchone()[0] == "t4n5o6p7q8r9"

    command.upgrade(config, "head")


def test_extension_downgrade_refuses_when_rows_exist(tmp_path) -> None:
    db_path = tmp_path / "extension-nonempty.db"
    config = Config(str(Path("alembic.ini").resolve()))
    config.set_main_option("sqlalchemy.url", f"sqlite+aiosqlite:///{db_path}")
    command.upgrade(config, "head")
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "INSERT INTO extension_installations (id, tenant_id, name, version, manifest_sha256,"
            " manifest_json, permissions_json, installed_by, enabled, created_at)"
            " VALUES ('ext-1', 't1', 'skill-pack', '1.0.0', 'hash', '{}', '[\"knowledge.read\"]',"
            " 'admin-1', 1, '2026-10-26T00:00:00+00:00')"
        )
        connection.commit()
    try:
        command.downgrade(config, "t4n5o6p7q8r9")
    except RuntimeError as error:
        assert "extension installations exist" in str(error)
    else:
        raise AssertionError("downgrade must refuse when installations exist")
