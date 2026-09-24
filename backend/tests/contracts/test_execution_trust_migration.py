import sqlite3
from pathlib import Path

from alembic.config import Config

from alembic import command


def test_execution_trust_migration_round_trip(tmp_path) -> None:
    db_path = tmp_path / "trust-migration.db"
    config = Config(str(Path("alembic.ini").resolve()))
    config.set_main_option("sqlalchemy.url", f"sqlite+aiosqlite:///{db_path}")
    command.upgrade(config, "head")
    with sqlite3.connect(db_path) as connection:
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert {"platform_thread_bindings", "platform_execution_capabilities", "platform_legacy_audit_deliveries"} <= tables
        assert connection.execute("SELECT version_num FROM alembic_version").fetchone()[0] == "l6f7g8h9i0j1"
    command.downgrade(config, "k5e6f7g8h9i0")
    with sqlite3.connect(db_path) as connection:
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert "platform_thread_bindings" not in tables
        assert "platform_execution_capabilities" not in tables
        assert "platform_legacy_audit_deliveries" in tables
    command.upgrade(config, "head")
