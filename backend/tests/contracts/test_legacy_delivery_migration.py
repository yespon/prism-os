import sqlite3
from pathlib import Path

from alembic.config import Config

from alembic import command


def test_legacy_delivery_migration_round_trip(tmp_path) -> None:
    db_path = tmp_path / "legacy-delivery.db"
    config = Config(str(Path("alembic.ini").resolve()))
    config.set_main_option("sqlalchemy.url", f"sqlite+aiosqlite:///{db_path}")
    command.upgrade(config, "k5e6f7g8h9i0")
    with sqlite3.connect(db_path) as connection:
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert "platform_legacy_audit_deliveries" in tables
        assert "platform_action_submissions" in tables
    command.downgrade(config, "j4d5e6f7g8h9")
    with sqlite3.connect(db_path) as connection:
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert "platform_legacy_audit_deliveries" not in tables
        assert "platform_action_submissions" in tables
    command.upgrade(config, "head")
