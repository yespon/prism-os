"""Explicit isolated Better Auth facts for native-resource fixtures; no production fallback."""
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import create_engine, text

from app.gateway import auth_db
from app.integrations import actor_authorization


@contextmanager
def isolated_identity(directory):
    engine = create_engine("sqlite+pysqlite:///" + str(Path(directory) / "native-auth.sqlite"), connect_args={"check_same_thread": False})
    with engine.begin() as connection:
        connection.execute(text('CREATE TABLE IF NOT EXISTS "user" (id TEXT PRIMARY KEY, role TEXT, status TEXT, "mustChangePassword" BOOLEAN)'))
    engine._prismos_fixture_actors = set()
    try:
        with patch.object(auth_db, "_engine", engine), patch.object(auth_db, "_db_type", "sqlite"), patch.object(actor_authorization, "auth_connection", auth_db.auth_connection):
            yield declare_actor
    finally:
        engine.dispose()


def declare_actor(actor):
    if not actor:
        return
    engine = auth_db._engine
    if engine is None or not hasattr(engine, "_prismos_fixture_actors"):
        raise RuntimeError("Synthetic identity requires its explicitly isolated Auth fixture")
    if actor in engine._prismos_fixture_actors:
        return  # Deletion/suspension must never be undone by another synthetic header.
    with engine.begin() as connection:
        existing = connection.execute(text('SELECT id FROM "user" WHERE id=:actor'), {"actor": actor}).first()
        if existing is None:
            connection.execute(text('INSERT INTO "user" (id,role,status,"mustChangePassword") VALUES (:actor,:role,:status,:change)'), {"actor": actor, "role": "user", "status": "active", "change": False})
    engine._prismos_fixture_actors.add(actor)
