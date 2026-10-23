"""Fresh identity initialization preserves the legacy schema and existing data."""

from contextlib import contextmanager

from sqlalchemy import create_engine, inspect, text

from app.gateway import bootstrap_admin as bootstrap


def test_fresh_and_repeated_bootstrap_preserves_identity_and_account(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'auth.db'}")

    @contextmanager
    def connection():
        with engine.connect() as conn:
            yield conn

    monkeypatch.setattr(bootstrap, "auth_connection", connection)
    monkeypatch.setattr(bootstrap, "_admin_created", False)
    bootstrap.bootstrap_admin()
    assert set(inspect(engine).get_table_names()) == {"user", "account", "session", "verification", "jwks"}
    with engine.begin() as conn:
        user_id = conn.execute(text('SELECT id FROM "user"')).scalar_one()
        conn.execute(text('UPDATE "user" SET email = :email WHERE id = :id'), {"email": "existing@example.invalid", "id": user_id})
        conn.execute(text("INSERT INTO account (id, \"accountId\", \"providerId\", \"userId\", password, \"createdAt\", \"updatedAt\") VALUES ('a', 'email', 'credential', :id, 'hash', 'date', 'date')"), {"id": user_id})
    monkeypatch.setattr(bootstrap, "_admin_created", False)
    bootstrap.bootstrap_admin()
    with engine.connect() as conn:
        assert conn.execute(text('SELECT count(*) FROM "user"')).scalar_one() == 1
        assert conn.execute(text('SELECT email FROM "user"')).scalar_one() == "existing@example.invalid"
        assert conn.execute(text("SELECT password FROM account")).scalar_one() == "hash"
    engine.dispose()
