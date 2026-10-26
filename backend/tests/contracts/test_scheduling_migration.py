"""R3 scheduling migration extends the platform chain."""

import sqlite3
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

from alembic import command


def test_scheduling_migration_single_head_and_reversible(tmp_path) -> None:
    db_path = tmp_path / "scheduling-migration.db"
    config = Config(str(Path("alembic.ini").resolve()))
    config.set_main_option("sqlalchemy.url", f"sqlite+aiosqlite:///{db_path}")
    assert ScriptDirectory.from_config(config).get_heads() == ["u5o6p7q8r9s0"]

    command.upgrade(config, "head")
    with sqlite3.connect(db_path) as connection:
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert {
            "schedule_definitions", "schedule_occurrences", "delivery_attempts",
            "knowledge_bases", "platform_run_facts",
        } <= tables
        assert connection.execute("SELECT version_num FROM alembic_version").fetchone()[0] == "u5o6p7q8r9s0"

    command.downgrade(config, "p0j1k2l3m4n5")
    with sqlite3.connect(db_path) as connection:
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert "schedule_definitions" not in tables
        assert "knowledge_bases" in tables
        assert connection.execute("SELECT version_num FROM alembic_version").fetchone()[0] == "p0j1k2l3m4n5"

    command.upgrade(config, "head")
    with sqlite3.connect(db_path) as connection:
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert "schedule_definitions" in tables


def test_occurrence_idempotency_unique_constraint(tmp_path) -> None:
    db_path = tmp_path / "occurrence-idempotency.db"
    config = Config(str(Path("alembic.ini").resolve()))
    config.set_main_option("sqlalchemy.url", f"sqlite+aiosqlite:///{db_path}")
    command.upgrade(config, "head")
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "INSERT INTO schedule_occurrences (id, tenant_id, schedule_id, scheduled_at,"
            " idempotency_key, state, created_at) VALUES ('o1', 't1', 's1', '2026-10-19T00:00:00+00:00',"
            " 't1:s1:20261019T0000', 'pending', '2026-10-19T00:00:00+00:00')"
        )
        connection.commit()
        try:
            connection.execute(
                "INSERT INTO schedule_occurrences (id, tenant_id, schedule_id, scheduled_at,"
                " idempotency_key, state, created_at) VALUES ('o2', 't1', 's1', '2026-10-19T00:00:00+00:00',"
                " 't1:s1:20261019T0000', 'pending', '2026-10-19T00:00:00+00:00')"
            )
        except sqlite3.IntegrityError:
            pass
        else:
            raise AssertionError("duplicate idempotency key must be rejected")
        # Different tenants may share the key text.
        connection.execute(
            "INSERT INTO schedule_occurrences (id, tenant_id, schedule_id, scheduled_at,"
            " idempotency_key, state, created_at) VALUES ('o3', 't2', 's1', '2026-10-19T00:00:00+00:00',"
            " 't1:s1:20261019T0000', 'pending', '2026-10-19T00:00:00+00:00')"
        )
        connection.commit()


def test_scheduling_downgrade_refuses_when_rows_exist(tmp_path) -> None:
    db_path = tmp_path / "scheduling-nonempty.db"
    config = Config(str(Path("alembic.ini").resolve()))
    config.set_main_option("sqlalchemy.url", f"sqlite+aiosqlite:///{db_path}")
    command.upgrade(config, "head")
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "INSERT INTO schedule_definitions (id, tenant_id, owner_user_id, name, trigger_kind,"
            " timezone, agent_name, prompt, delivery_channel, enabled, created_at, updated_at)"
            " VALUES ('s1', 't1', 'u1', 'check', 'cron', 'Asia/Shanghai', 'default', 'do it', 'web', 1,"
            " '2026-10-19T00:00:00+00:00', '2026-10-19T00:00:00+00:00')"
        )
        connection.commit()
    try:
        command.downgrade(config, "p0j1k2l3m4n5")
    except RuntimeError as error:
        assert "schedule_definitions rows exist" in str(error)
    else:
        raise AssertionError("downgrade must refuse when schedule rows exist")
