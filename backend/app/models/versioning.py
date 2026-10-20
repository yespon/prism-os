"""Immutable agent versions and deployments (R5, M4 minimal)."""

from datetime import datetime

from sqlalchemy import Column, DateTime, Index, String, Text
from sqlmodel import Field, SQLModel


class AgentVersionRecord(SQLModel, table=True):
    """An immutable snapshot of an agent's configuration.

    The content hash reuses the gateway's agent-revision digest, so an
    existing agent maps to its version without migration of content.
    Publish freezes the snapshot; records are never updated afterwards.
    """

    __tablename__ = "agent_versions"
    __table_args__ = (
        Index("ix_agent_version_tenant_agent", "tenant_id", "agent_id"),
    )

    id: str = Field(sa_column=Column(String(64), primary_key=True))
    tenant_id: str = Field(sa_column=Column(String(255), nullable=False))
    agent_id: str = Field(sa_column=Column(String(255), nullable=False))
    version_hash: str = Field(sa_column=Column(String(64), nullable=False))
    version_no: int = Field(nullable=False)
    # Frozen configuration snapshot (prompt/model/tools/meta references).
    config_json: str = Field(sa_column=Column(Text, nullable=False))
    notes: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    published_by: str = Field(sa_column=Column(String(255), nullable=False))
    published_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))


class AgentDeploymentRecord(SQLModel, table=True):
    """The current deployment pointer for an agent: which version runs."""

    __tablename__ = "agent_deployments"
    __table_args__ = (
        Index("ix_agent_deployment_tenant_agent", "tenant_id", "agent_id"),
    )

    tenant_id: str = Field(sa_column=Column(String(255), primary_key=True))
    agent_id: str = Field(sa_column=Column(String(255), primary_key=True))
    version_id: str = Field(sa_column=Column(String(64), nullable=False))
    previous_version_id: str | None = Field(default=None, sa_column=Column(String(64), nullable=True))
    deployed_by: str = Field(sa_column=Column(String(255), nullable=False))
    deployed_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))
