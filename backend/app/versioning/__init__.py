"""Agent version publication and deployment rollback (R5, M4 minimal).

Publishing snapshots the current CustomAgent configuration into an
immutable version; deploying points the agent's deployment record at a
version; rollback re-points to the previous version. Historical run
facts keep referencing the version they executed under - rollback
never rewrites history.
"""

from datetime import UTC, datetime
from hashlib import sha256
from json import dumps
from uuid import uuid4

from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.versioning import AgentDeploymentRecord, AgentVersionRecord
from deerflow.database.session import get_session_factory


class VersioningError(Exception):
    """Domain error with a user-presentable message."""


def _config_snapshot(agent) -> dict:
    return {
        "name": agent.name,
        "description": agent.description or "",
        "model": agent.model,
        "tool_groups": list(agent.tool_groups or []),
        "system_prompt": agent.system_prompt or "",
        "skills": list(agent.skills or []),
        "tags": list(agent.tags or []),
        "meta_info": dict(agent.meta_info or {}),
    }


def snapshot_hash(agent) -> str:
    payload = dumps(_config_snapshot(agent), sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return sha256(payload.encode()).hexdigest()


class VersioningService:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession] | None = None) -> None:
        self._session_factory = session_factory or get_session_factory()

    async def publish(self, agent, *, notes: str | None = None) -> AgentVersionRecord:
        """Snapshot the agent's current configuration as a new immutable version."""
        snapshot = _config_snapshot(agent)
        digest = snapshot_hash(agent)
        async with self._session_factory() as session, session.begin():
            existing = (await session.exec(
                select(AgentVersionRecord).where(
                    AgentVersionRecord.tenant_id == agent.tenant_id,
                    AgentVersionRecord.agent_id == agent.id,
                )
            )).all()
            for row in existing:
                if row.version_hash == digest:
                    raise VersioningError("identical configuration already published as a version")
            record = AgentVersionRecord(
                id=f"av_{uuid4().hex}", tenant_id=agent.tenant_id, agent_id=agent.id,
                version_hash=digest, version_no=len(existing) + 1,
                config_json=dumps(snapshot, sort_keys=True, ensure_ascii=False),
                notes=notes, published_by=agent.created_by or "unknown",
                published_at=datetime.now(UTC),
            )
            session.add(record)
        return record

    async def deploy(self, tenant_id: str, agent_id: str, version_id: str, *, deployed_by: str) -> AgentDeploymentRecord:
        """Point the agent's deployment at a version; the previous is kept for rollback."""
        async with self._session_factory() as session, session.begin():
            version = await session.get(AgentVersionRecord, version_id)
            if version is None or version.tenant_id != tenant_id or version.agent_id != agent_id:
                raise VersioningError("version not found for this agent")
            current = (await session.exec(
                select(AgentDeploymentRecord).where(
                    AgentDeploymentRecord.tenant_id == tenant_id,
                    AgentDeploymentRecord.agent_id == agent_id,
                )
            )).first()
            if current is not None and current.version_id == version_id:
                raise VersioningError("version already deployed")
            if current is None:
                record = AgentDeploymentRecord(
                    tenant_id=tenant_id, agent_id=agent_id, version_id=version_id,
                    previous_version_id=None, deployed_by=deployed_by,
                    deployed_at=datetime.now(UTC),
                )
            else:
                record = AgentDeploymentRecord(
                    tenant_id=tenant_id, agent_id=agent_id, version_id=version_id,
                    previous_version_id=current.version_id, deployed_by=deployed_by,
                    deployed_at=datetime.now(UTC),
                )
                await session.delete(current)
            session.add(record)
        return record

    async def rollback(self, tenant_id: str, agent_id: str, *, deployed_by: str) -> AgentDeploymentRecord:
        """Re-point the deployment at its previous version (one level)."""
        async with self._session_factory() as session, session.begin():
            current = (await session.exec(
                select(AgentDeploymentRecord).where(
                    AgentDeploymentRecord.tenant_id == tenant_id,
                    AgentDeploymentRecord.agent_id == agent_id,
                )
            )).first()
            if current is None:
                raise VersioningError("no deployment to roll back")
            if current.previous_version_id is None:
                raise VersioningError("no previous version to roll back to")
            previous = await session.get(AgentVersionRecord, current.previous_version_id)
            if previous is None:
                raise VersioningError("previous version vanished")
            record = AgentDeploymentRecord(
                tenant_id=tenant_id, agent_id=agent_id,
                version_id=previous.id,
                previous_version_id=None,
                deployed_by=deployed_by, deployed_at=datetime.now(UTC),
            )
            await session.delete(current)
            session.add(record)
        return record

    async def get_deployment(self, tenant_id: str, agent_id: str) -> AgentDeploymentRecord | None:
        async with self._session_factory() as session:
            return (await session.exec(
                select(AgentDeploymentRecord).where(
                    AgentDeploymentRecord.tenant_id == tenant_id,
                    AgentDeploymentRecord.agent_id == agent_id,
                )
            )).first()

    async def list_versions(self, tenant_id: str, agent_id: str) -> list[AgentVersionRecord]:
        async with self._session_factory() as session:
            return list((await session.exec(
                select(AgentVersionRecord)
                .where(AgentVersionRecord.tenant_id == tenant_id,
                       AgentVersionRecord.agent_id == agent_id)
                .order_by(AgentVersionRecord.version_no)
            )).all())

    async def get_version(self, tenant_id: str, version_id: str) -> AgentVersionRecord:
        async with self._session_factory() as session:
            record = await session.get(AgentVersionRecord, version_id)
            if record is None or record.tenant_id != tenant_id:
                raise VersioningError("version not found")
            return record
