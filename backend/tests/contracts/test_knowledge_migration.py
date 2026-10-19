"""R2 knowledge/connector migration extends the platform chain."""

import sqlite3
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

from alembic import command


def test_knowledge_migration_single_head_and_reversible(tmp_path) -> None:
    db_path = tmp_path / "knowledge-migration.db"
    config = Config(str(Path("alembic.ini").resolve()))
    config.set_main_option("sqlalchemy.url", f"sqlite+aiosqlite:///{db_path}")
    assert ScriptDirectory.from_config(config).get_heads() == ["q1k2l3m4n5o6"]

    command.upgrade(config, "head")
    with sqlite3.connect(db_path) as connection:
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert {
            "knowledge_bases", "knowledge_documents", "knowledge_members",
            "connector_catalog", "connector_instances", "platform_run_facts",
        } <= tables
        assert connection.execute("SELECT version_num FROM alembic_version").fetchone()[0] == "q1k2l3m4n5o6"

    command.downgrade(config, "o9i0j1k2l3m4")
    with sqlite3.connect(db_path) as connection:
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert "knowledge_bases" not in tables
        assert "platform_run_facts" in tables
        assert connection.execute("SELECT version_num FROM alembic_version").fetchone()[0] == "o9i0j1k2l3m4"

    command.upgrade(config, "head")
    with sqlite3.connect(db_path) as connection:
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert "knowledge_bases" in tables


def test_knowledge_downgrade_refuses_when_rows_exist(tmp_path) -> None:
    db_path = tmp_path / "knowledge-nonempty.db"
    config = Config(str(Path("alembic.ini").resolve()))
    config.set_main_option("sqlalchemy.url", f"sqlite+aiosqlite:///{db_path}")
    command.upgrade(config, "head")
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "INSERT INTO knowledge_bases (id, tenant_id, owner_user_id, name, visibility, created_at)"
            " VALUES ('kb-1', 't1', 'u1', 'runbook', 'private', '2026-10-19T00:00:00+00:00')"
        )
        connection.commit()
    try:
        command.downgrade(config, "o9i0j1k2l3m4")
    except RuntimeError as error:
        assert "knowledge_bases rows exist" in str(error)
    else:
        raise AssertionError("downgrade must refuse when knowledge rows exist")
