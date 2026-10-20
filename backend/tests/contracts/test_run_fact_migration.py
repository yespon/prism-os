"""R1-A run fact migration extends the M1 chain without rewriting it."""

import sqlite3
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

from alembic import command


def test_run_fact_migration_is_single_head_and_reversible(tmp_path) -> None:
    db_path = tmp_path / "run-fact-migration.db"
    config = Config(str(Path("alembic.ini").resolve()))
    config.set_main_option("sqlalchemy.url", f"sqlite+aiosqlite:///{db_path}")
    assert ScriptDirectory.from_config(config).get_heads() == ["s3m4n5o6p7q8"]

    command.upgrade(config, "head")
    with sqlite3.connect(db_path) as connection:
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert {
            "platform_run_facts",
            "platform_policy_decisions",
            "platform_approvals",
            "platform_ticket_secrets",
        } <= tables
        assert connection.execute("SELECT version_num FROM alembic_version").fetchone()[0] == "s3m4n5o6p7q8"

    # Downgrade to the M1 head keeps all M1 governance tables.
    command.downgrade(config, "n8h9i0j1k2l3")
    with sqlite3.connect(db_path) as connection:
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert "platform_run_facts" not in tables
        assert "platform_ticket_secrets" in tables
        assert connection.execute("SELECT version_num FROM alembic_version").fetchone()[0] == "n8h9i0j1k2l3"

    command.upgrade(config, "head")
    with sqlite3.connect(db_path) as connection:
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert "platform_run_facts" in tables


def test_run_fact_downgrade_refuses_when_rows_exist(tmp_path) -> None:
    db_path = tmp_path / "run-fact-nonempty.db"
    config = Config(str(Path("alembic.ini").resolve()))
    config.set_main_option("sqlalchemy.url", f"sqlite+aiosqlite:///{db_path}")
    command.upgrade(config, "head")
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "INSERT INTO platform_run_facts (run_id, tenant_id, task_id, workload_id, state,"
            " snapshot_json, started_at) VALUES ('run_x', 't1', 'task_x', 'w1', 'created', '{}', '2026-10-19T00:00:00+00:00')"
        )
        connection.commit()
    try:
        command.downgrade(config, "n8h9i0j1k2l3")
    except RuntimeError as error:
        assert "run facts exist" in str(error)
    else:
        raise AssertionError("downgrade must refuse when run facts exist")
