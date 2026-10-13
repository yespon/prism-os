"""Serialize original Agent reference writes and Skill withdrawal transactions."""

import hashlib

from sqlalchemy import text


async def begin_reference_transaction(session, tenant_id: str) -> None:
    """Acquire before querying Agent/Skill rows; released by commit/rollback.

    PostgreSQL row locks do not protect absent Agent references. A deterministic
    tenant transaction advisory lock coordinates all host CRUD participants.
    SQLite uses its existing immediate write transaction instead. No registry,
    permission, persistent lock row or execution fact is introduced here.
    """
    if not isinstance(tenant_id, str) or not tenant_id:
        raise ValueError("Reference transaction requires a tenant")
    dialect = session.get_bind().dialect.name
    if dialect == "postgresql":
        digest = hashlib.sha256(("prismos.skill-references:" + tenant_id).encode()).digest()
        key = int.from_bytes(digest[:8], "big", signed=True)
        await session.exec(text("SELECT pg_advisory_xact_lock(:key)"), params={"key": key})
    elif dialect == "sqlite":
        await session.exec(text("BEGIN IMMEDIATE"))
    else:
        raise RuntimeError("Reference transaction coordination is unavailable for this database")
