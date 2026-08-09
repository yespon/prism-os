"""Unified database connection layer for Better Auth identity tables.

Supports both SQLite and PostgreSQL backends via SQLAlchemy sync engine.
"""

import logging
import os
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from sqlalchemy import Connection, Engine, create_engine, text

from deerflow.config import get_app_config

logger = logging.getLogger(__name__)


def _resolve_auth_db_url() -> str:
    """Resolve auth database URL from app config, with env variable override."""
    # Direct env var override (takes precedence over config.yaml)
    env_url = os.getenv("AUTH_DB_URL")
    if env_url:
        if env_url.startswith("postgresql+asyncpg://"):
            return env_url.replace("postgresql+asyncpg://", "postgresql+psycopg://", 1)
        if env_url.startswith("sqlite+aiosqlite://"):
            return env_url.replace("sqlite+aiosqlite://", "sqlite+pysqlite://", 1)
        return env_url

    cfg = get_app_config()
    db_type = cfg.database.type
    url = cfg.database.auth.url

    if db_type == "postgres":
        if url.startswith("postgresql+asyncpg://"):
            return url.replace("postgresql+asyncpg://", "postgresql+psycopg://", 1)
        raise RuntimeError(
            f"config.yaml database.type is 'postgres' but database.auth.url is not a "
            f"postgresql+asyncpg:// URL: {url}"
        )

    # SQLite mode
    env_path = os.getenv("AUTH_DB_PATH")
    if env_path:
        return f"sqlite+pysqlite:///{env_path}"

    if url.startswith("sqlite+aiosqlite://"):
        raw_path = url.split(":///", maxsplit=1)[-1]
        normalized_path = raw_path[1:] if raw_path.startswith("/") else raw_path
        Path(normalized_path).parent.mkdir(parents=True, exist_ok=True)
        return url.replace("sqlite+aiosqlite://", "sqlite+pysqlite://", 1)

    raise RuntimeError(f"Unexpected database.auth.url format: {url}")


def _is_postgres(url: str) -> bool:
    return url.startswith("postgresql")


def _is_sqlite(url: str) -> bool:
    return url.startswith("sqlite")


_engine: Engine | None = None
_db_type: str | None = None


def get_auth_engine() -> Engine:
    """Return a cached sync SQLAlchemy engine for auth tables."""
    global _engine, _db_type
    if _engine is not None:
        return _engine

    db_url = _resolve_auth_db_url()
    _db_type = "postgres" if _is_postgres(db_url) else "sqlite"

    if _is_sqlite(db_url):
        raw_path = db_url.split(":///", maxsplit=1)[-1]
        normalized_path = raw_path[1:] if raw_path.startswith("/") else raw_path
        Path(normalized_path).parent.mkdir(parents=True, exist_ok=True)

    connect_args = {}
    if _db_type == "sqlite":
        connect_args["check_same_thread"] = False

    _engine = create_engine(db_url, connect_args=connect_args, pool_pre_ping=True)
    return _engine


def get_db_type() -> str:
    """Return 'postgres' or 'sqlite'."""
    if _db_type is None:
        get_auth_engine()
    return _db_type or "sqlite"


def reset_auth_engine() -> None:
    """Reset the cached engine. Useful in tests or after config changes."""
    global _engine, _db_type
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _db_type = None


@contextmanager
def auth_connection():
    """Context manager yielding a SQLAlchemy Connection for auth operations."""
    engine = get_auth_engine()
    with engine.connect() as conn:
        yield conn


def _row_to_dict(row) -> dict[str, Any]:
    """Convert a SQLAlchemy Row to a dict (compatible with both SQLite and PostgreSQL)."""
    return dict(row._mapping)


def table_exists(conn: Connection, table_name: str) -> bool:
    """Check if a table exists in the database."""
    if get_db_type() == "sqlite":
        result = conn.execute(
            text("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = :name LIMIT 1"),
            {"name": table_name},
        )
    else:
        result = conn.execute(
            text(
                "SELECT 1 FROM information_schema.tables "
                "WHERE table_name = :name LIMIT 1"
            ),
            {"name": table_name},
        )
    return result.fetchone() is not None


def column_exists(conn: Connection, table_name: str, column_name: str) -> bool:
    """Check if a column exists in a table."""
    if get_db_type() == "sqlite":
        result = conn.execute(
            text(f"PRAGMA table_info({table_name})"),
        )
        return any(row._mapping["name"] == column_name for row in result.fetchall())
    else:
        result = conn.execute(
            text(
                "SELECT 1 FROM information_schema.columns "
                "WHERE table_name = :table AND column_name = :column LIMIT 1"
            ),
            {"table": table_name, "column": column_name},
        )
        return result.fetchone() is not None
