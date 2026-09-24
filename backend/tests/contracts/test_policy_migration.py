"""M1 governance migration extends the P0 audit chain without rewriting it."""

import sqlite3
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

from alembic import command


def test_policy_migration_is_single_head_and_reversible(tmp_path) -> None:
    db_path = tmp_path / "governance-migration.db"
    config = Config(str(Path("alembic.ini").resolve()))
    config.set_main_option("sqlalchemy.url", f"sqlite+aiosqlite:///{db_path}")
    assert ScriptDirectory.from_config(config).get_heads() == ["i3c4d5e6f7g8"]

    command.upgrade(config, "head")
    with sqlite3.connect(db_path) as connection:
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert {"platform_audit_events", "platform_policy_decisions", "platform_approvals"} <= tables
        assert connection.execute("SELECT version_num FROM alembic_version").fetchone()[0] == "i3c4d5e6f7g8"

    command.downgrade(config, "h2b3c4d5e6f7")
    with sqlite3.connect(db_path) as connection:
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert "platform_audit_events" in tables
        assert "platform_policy_decisions" not in tables
        assert "platform_approvals" not in tables
        assert connection.execute("SELECT version_num FROM alembic_version").fetchone()[0] == "h2b3c4d5e6f7"

    command.upgrade(config, "head")
    with sqlite3.connect(db_path) as connection:
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert {"platform_policy_decisions", "platform_approvals"} <= tables
