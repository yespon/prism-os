"""Tenant-scoped thread binding and single-use graph execution capabilities."""

import os
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256

from sqlalchemy import update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.governance import PlatformExecutionCapabilityRecord, PlatformThreadBindingRecord
from deerflow.database.session import get_session_factory

DEFAULT_AGENT = "__default__"


class ExecutionTrustError(PermissionError):
    """The requested thread or one-use capability is not trusted."""


@dataclass(frozen=True)
class ThreadBinding:
    thread_id: str
    tenant_id: str
    user_id: str
    agent_name: str | None
    legacy_claim: bool


class ThreadBindingRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession] | None = None) -> None:
        self._session_factory = session_factory or get_session_factory()

    @staticmethod
    def _fact(row: PlatformThreadBindingRecord) -> ThreadBinding:
        return ThreadBinding(row.thread_id, row.tenant_id, row.user_id, row.agent_name, row.legacy_claim)

    async def create(
        self, thread_id: str, tenant_id: str, user_id: str, *, legacy_claim: bool = False,
    ) -> ThreadBinding:
        if not all((thread_id, tenant_id, user_id)):
            raise ExecutionTrustError("thread identity is incomplete")
        try:
            async with self._session_factory() as session, session.begin():
                if await session.get(PlatformThreadBindingRecord, thread_id) is not None:
                    raise ExecutionTrustError("thread is already bound")
                row = PlatformThreadBindingRecord(
                    thread_id=thread_id, tenant_id=tenant_id, user_id=user_id,
                    agent_name=None, legacy_claim=legacy_claim, created_at=datetime.now(UTC),
                )
                session.add(row)
                await session.flush()
                return self._fact(row)
        except IntegrityError as exc:
            raise ExecutionTrustError("thread is already bound") from exc

    async def lookup(self, thread_id: str) -> ThreadBinding | None:
        async with self._session_factory() as session:
            row = await session.get(PlatformThreadBindingRecord, thread_id)
            return None if row is None else self._fact(row)

    async def get(self, thread_id: str, tenant_id: str, user_id: str) -> ThreadBinding:
        found = await self.lookup(thread_id)
        if found is None or found.tenant_id != tenant_id or found.user_id != user_id:
            raise ExecutionTrustError("thread is unavailable")
        return found

    async def bind_agent(self, thread_id: str, tenant_id: str, user_id: str, agent_name: str | None) -> ThreadBinding:
        choice = agent_name or DEFAULT_AGENT
        async with self._session_factory() as session, session.begin():
            row = await session.get(PlatformThreadBindingRecord, thread_id)
            if row is None or row.tenant_id != tenant_id or row.user_id != user_id:
                raise ExecutionTrustError("thread is unavailable")
            if row.agent_name is None:
                result = await session.exec(update(PlatformThreadBindingRecord).where(
                    PlatformThreadBindingRecord.thread_id == thread_id,
                    PlatformThreadBindingRecord.tenant_id == tenant_id,
                    PlatformThreadBindingRecord.user_id == user_id,
                    PlatformThreadBindingRecord.agent_name.is_(None),
                ).values(agent_name=choice))
                if result.rowcount != 1:
                    raise ExecutionTrustError("thread Agent changed concurrently")
                return ThreadBinding(thread_id, tenant_id, user_id, choice, row.legacy_claim)
            if row.agent_name != choice:
                raise ExecutionTrustError("thread Agent cannot change")
            return self._fact(row)

    async def delete(self, thread_id: str, tenant_id: str, user_id: str) -> None:
        async with self._session_factory() as session, session.begin():
            row = await session.get(PlatformThreadBindingRecord, thread_id)
            if row is None or row.tenant_id != tenant_id or row.user_id != user_id:
                raise ExecutionTrustError("thread is unavailable")
            await session.delete(row)

    async def owned_ids(self, tenant_id: str, user_id: str) -> set[str]:
        async with self._session_factory() as session:
            rows = (await session.exec(select(PlatformThreadBindingRecord.thread_id).where(
                PlatformThreadBindingRecord.tenant_id == tenant_id,
                PlatformThreadBindingRecord.user_id == user_id,
            ))).all()
            return set(rows)


class ExecutionCapabilityRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession] | None = None) -> None:
        self._session_factory = session_factory or get_session_factory()

    async def issue(
        self, tenant_id: str, user_id: str, thread_id: str, agent_name: str | None,
        *, at: datetime | None = None, ttl_seconds: int = 60,
    ) -> str:
        if not all((tenant_id, user_id, thread_id)) or ttl_seconds <= 0 or ttl_seconds > 300:
            raise ExecutionTrustError("invalid execution capability request")
        instant = at or datetime.now(UTC)
        token = secrets.token_urlsafe(32)
        row = PlatformExecutionCapabilityRecord(
            token_hash=sha256(token.encode()).hexdigest(),
            tenant_id=tenant_id, user_id=user_id, thread_id=thread_id,
            agent_name=agent_name, created_at=instant,
            expires_at=instant + timedelta(seconds=ttl_seconds),
        )
        async with self._session_factory() as session, session.begin():
            session.add(row)
        return token

    async def consume(
        self, token: str | None, tenant_id: str, user_id: str,
        thread_id: str, agent_name: str | None, *, at: datetime | None = None,
    ) -> None:
        if not isinstance(token, str) or len(token) < 32:
            raise ExecutionTrustError("trusted execution capability required")
        instant = at or datetime.now(UTC)
        digest = sha256(token.encode()).hexdigest()
        async with self._session_factory() as session, session.begin():
            row = await session.get(PlatformExecutionCapabilityRecord, digest)
            if (row is None or row.tenant_id != tenant_id or row.user_id != user_id
                or row.thread_id != thread_id or row.agent_name != agent_name
                or row.consumed_at is not None):
                raise ExecutionTrustError("execution capability mismatch or replay")
            expires = row.expires_at.replace(tzinfo=UTC) if row.expires_at.tzinfo is None else row.expires_at
            if expires <= instant:
                raise ExecutionTrustError("execution capability expired")
            result = await session.exec(update(PlatformExecutionCapabilityRecord).where(
                PlatformExecutionCapabilityRecord.token_hash == digest,
                PlatformExecutionCapabilityRecord.consumed_at.is_(None),
            ).values(consumed_at=instant))
            if result.rowcount != 1:
                raise ExecutionTrustError("execution capability replay")


async def attach_execution_capability(context: dict) -> dict:
    """Add a short-lived bearer to a server-created LangGraph run context."""
    trusted = dict(context)
    if os.getenv("PRISMOS_TRUSTED_GRAPH_CONTEXT", "off").lower() != "required":
        return trusted
    trusted["prismos_execution_capability"] = await ExecutionCapabilityRepository().issue(
        trusted["tenant_id"], trusted["user_id"], trusted["thread_id"],
        trusted.get("agent_name"),
    )
    return trusted
