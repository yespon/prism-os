import logging
import sqlite3
from pathlib import Path

from alembic.config import Config

from alembic import command


def test_execution_trust_migration_round_trip(tmp_path) -> None:
    db_path = tmp_path / "trust-migration.db"
    config = Config(str(Path("alembic.ini").resolve()))
    config.set_main_option("sqlalchemy.url", f"sqlite+aiosqlite:///{db_path}")
    app_logger = logging.getLogger("deerflow.config.app_config")
    app_logger.disabled = False
    command.upgrade(config, "head")
    assert not app_logger.disabled
    with sqlite3.connect(db_path) as connection:
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert {"platform_thread_bindings", "platform_execution_capabilities", "platform_legacy_audit_deliveries"} <= tables
        assert connection.execute("SELECT version_num FROM alembic_version").fetchone()[0] == "m7g8h9i0j1k2"
        columns = {row[1] for row in connection.execute("PRAGMA table_info(platform_execution_capabilities)")}
        assert "action_incident_id" in columns
    command.downgrade(config, "l6f7g8h9i0j1")
    with sqlite3.connect(db_path) as connection:
        columns = {row[1] for row in connection.execute("PRAGMA table_info(platform_execution_capabilities)")}
        assert "action_incident_id" not in columns
    command.upgrade(config, "head")
    with sqlite3.connect(db_path) as connection:
        columns = {row[1] for row in connection.execute("PRAGMA table_info(platform_execution_capabilities)")}
        assert "action_incident_id" in columns
    command.downgrade(config, "k5e6f7g8h9i0")
    with sqlite3.connect(db_path) as connection:
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert "platform_thread_bindings" not in tables
        assert "platform_execution_capabilities" not in tables
        assert "platform_legacy_audit_deliveries" in tables
    command.upgrade(config, "head")
