"""The submission migration can roll back without dropping earlier M1 facts."""

import sqlite3
from pathlib import Path

from alembic.config import Config

from alembic import command


def test_submission_migration_round_trip(tmp_path) -> None:
    db_path = tmp_path / "submission-migration.db"
    config = Config(str(Path("alembic.ini").resolve()))
    config.set_main_option("sqlalchemy.url", f"sqlite+aiosqlite:///{db_path}")
    command.upgrade(config, "head")
    with sqlite3.connect(db_path) as connection:
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert "platform_action_submissions" in tables
        assert "platform_policy_decisions" in tables
        assert connection.execute("SELECT version_num FROM alembic_version").fetchone()[0] == "k5e6f7g8h9i0"
    command.downgrade(config, "i3c4d5e6f7g8")
    with sqlite3.connect(db_path) as connection:
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert "platform_action_submissions" not in tables
        assert "platform_policy_decisions" in tables
        assert "platform_approvals" in tables
        assert "platform_audit_events" in tables
    command.upgrade(config, "head")
    with sqlite3.connect(db_path) as connection:
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert "platform_action_submissions" in tables
