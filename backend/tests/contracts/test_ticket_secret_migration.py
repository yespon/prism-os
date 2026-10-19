import sqlite3
from pathlib import Path

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory

from alembic import command


def test_secret_schema_upgrade_and_nonempty_downgrade_protection(tmp_path):
    database = tmp_path / "ticket-secret-migration.db"
    config = Config(str(Path("alembic.ini").resolve()))
    config.set_main_option("sqlalchemy.url", f"sqlite+aiosqlite:///{database}")
    assert ScriptDirectory.from_config(config).get_heads() == ["q1k2l3m4n5o6"]
    command.upgrade(config, "head")
    with sqlite3.connect(database) as conn:
        conn.execute("INSERT INTO platform_ticket_secrets VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                     ("secret-1", "tenant-a", "source-a", "ticket.create", 1, "enc:v1:test", 1, "2026-10-08"))
    with pytest.raises(RuntimeError, match="records exist"):
        command.downgrade(config, "m7g8h9i0j1k2")
    with sqlite3.connect(database) as conn:
        assert conn.execute("SELECT COUNT(*) FROM platform_ticket_secrets").fetchone()[0] == 1
        # The R1 run-fact migration downgrades cleanly first; the ticket-secret
        # non-empty protection then stops the chain at its own revision.
        assert conn.execute("SELECT version_num FROM alembic_version").fetchone()[0] == "n8h9i0j1k2l3"
        assert conn.execute("SELECT name FROM sqlite_master WHERE name='platform_run_facts'").fetchone() is None
        conn.execute("DELETE FROM platform_ticket_secrets")
    command.upgrade(config, "head")
    command.downgrade(config, "m7g8h9i0j1k2")
    with sqlite3.connect(database) as conn:
        assert conn.execute("SELECT version_num FROM alembic_version").fetchone()[0] == "m7g8h9i0j1k2"
        assert conn.execute("SELECT name FROM sqlite_master WHERE name='incident_actions'").fetchone()
    command.upgrade(config, "head")
    with sqlite3.connect(database) as conn:
        assert conn.execute("SELECT COUNT(*) FROM platform_ticket_secrets").fetchone()[0] == 0
