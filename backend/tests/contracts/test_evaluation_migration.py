"""R5 evaluation migration extends the platform chain."""

import sqlite3
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

from alembic import command


def test_evaluation_migration_single_head_and_reversible(tmp_path) -> None:
    db_path = tmp_path / "evaluation-migration.db"
    config = Config(str(Path("alembic.ini").resolve()))
    config.set_main_option("sqlalchemy.url", f"sqlite+aiosqlite:///{db_path}")
    assert ScriptDirectory.from_config(config).get_heads() == ["u5o6p7q8r9s0"]

    command.upgrade(config, "head")
    with sqlite3.connect(db_path) as connection:
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert {"evaluation_results", "agent_versions", "platform_task_facts"} <= tables
        assert connection.execute("SELECT version_num FROM alembic_version").fetchone()[0] == "u5o6p7q8r9s0"

    command.downgrade(config, "s3m4n5o6p7q8")
    with sqlite3.connect(db_path) as connection:
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert "evaluation_results" not in tables
        assert "agent_versions" in tables
        assert connection.execute("SELECT version_num FROM alembic_version").fetchone()[0] == "s3m4n5o6p7q8"

    command.upgrade(config, "head")


def test_evaluation_downgrade_refuses_when_rows_exist(tmp_path) -> None:
    db_path = tmp_path / "evaluation-nonempty.db"
    config = Config(str(Path("alembic.ini").resolve()))
    config.set_main_option("sqlalchemy.url", f"sqlite+aiosqlite:///{db_path}")
    command.upgrade(config, "head")
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "INSERT INTO evaluation_results (id, tenant_id, version_id, dataset, score, passed,"
            " details_json, created_at) VALUES ('ev-1', 't1', 'av-1', 'golden-aiops', 0.9, 1, '{}',"
            " '2026-10-20T00:00:00+00:00')"
        )
        connection.commit()
    try:
        command.downgrade(config, "s3m4n5o6p7q8")
    except RuntimeError as error:
        assert "evaluation results exist" in str(error)
    else:
        raise AssertionError("downgrade must refuse when evaluation rows exist")
