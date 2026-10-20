"""R5 lifecycle migration extends the platform chain."""

import sqlite3
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory


def test_lifecycle_migration_single_head_and_reversible(tmp_path) -> None:
    db_path = tmp_path / "lifecycle-migration.db"
    config = Config(str(Path("alembic.ini").resolve()))
    config.set_main_option("sqlalchemy.url", f"sqlite+aiosqlite:///{db_path}")
    assert ScriptDirectory.from_config(config).get_heads() == ["r2l3m4n5o6p7"]

    command.upgrade(config, "head")
    with sqlite3.connect(db_path) as connection:
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert {"platform_task_facts", "platform_run_attempts", "schedule_definitions"} <= tables
        assert connection.execute("SELECT version_num FROM alembic_version").fetchone()[0] == "r2l3m4n5o6p7"

    command.downgrade(config, "q1k2l3m4n5o6")
    with sqlite3.connect(db_path) as connection:
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert "platform_task_facts" not in tables
        assert "schedule_definitions" in tables

    command.upgrade(config, "head")
    with sqlite3.connect(db_path) as connection:
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert "platform_task_facts" in tables


def test_lifecycle_downgrade_refuses_when_rows_exist(tmp_path) -> None:
    db_path = tmp_path / "lifecycle-nonempty.db"
    config = Config(str(Path("alembic.ini").resolve()))
    config.set_main_option("sqlalchemy.url", f"sqlite+aiosqlite:///{db_path}")
    command.upgrade(config, "head")
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "INSERT INTO platform_task_facts (id, tenant_id, created_by, state, created_at)"
            " VALUES ('task-1', 't1', 'u1', 'pending', '2026-10-20T00:00:00+00:00')"
        )
        connection.commit()
    try:
        command.downgrade(config, "q1k2l3m4n5o6")
    except RuntimeError as error:
        assert "platform_task_facts rows exist" in str(error)
    else:
        raise AssertionError("downgrade must refuse when task rows exist")
