"""R5 versioning migration extends the platform chain."""

import sqlite3
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

from alembic import command


def test_versioning_migration_single_head_and_reversible(tmp_path) -> None:
    db_path = tmp_path / "versioning-migration.db"
    config = Config(str(Path("alembic.ini").resolve()))
    config.set_main_option("sqlalchemy.url", f"sqlite+aiosqlite:///{db_path}")
    assert ScriptDirectory.from_config(config).get_heads() == ["t4n5o6p7q8r9"]

    command.upgrade(config, "head")
    with sqlite3.connect(db_path) as connection:
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert {"agent_versions", "agent_deployments", "platform_task_facts"} <= tables
        assert connection.execute("SELECT version_num FROM alembic_version").fetchone()[0] == "t4n5o6p7q8r9"

    command.downgrade(config, "r2l3m4n5o6p7")
    with sqlite3.connect(db_path) as connection:
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert "agent_versions" not in tables
        assert "platform_task_facts" in tables
        assert connection.execute("SELECT version_num FROM alembic_version").fetchone()[0] == "r2l3m4n5o6p7"

    command.upgrade(config, "head")


def test_versioning_downgrade_refuses_when_rows_exist(tmp_path) -> None:
    db_path = tmp_path / "versioning-nonempty.db"
    config = Config(str(Path("alembic.ini").resolve()))
    config.set_main_option("sqlalchemy.url", f"sqlite+aiosqlite:///{db_path}")
    command.upgrade(config, "head")
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "INSERT INTO agent_versions (id, tenant_id, agent_id, version_hash, version_no,"
            " config_json, published_by, published_at)"
            " VALUES ('av-1', 't1', 'agent-1', 'hash-1', 1, '{}', 'user-1', '2026-10-20T00:00:00+00:00')"
        )
        connection.commit()
    try:
        command.downgrade(config, "r2l3m4n5o6p7")
    except RuntimeError as error:
        assert "agent version rows exist" in str(error)
    else:
        raise AssertionError("downgrade must refuse when version rows exist")
