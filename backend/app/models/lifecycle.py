"""Task/Run/Attempt lifecycle records (R5, M2 minimal)."""

from datetime import datetime

from sqlalchemy import Column, DateTime, Index, Integer, String, Text, UniqueConstraint
from sqlmodel import Field, SQLModel


class PlatformTaskRecord(SQLModel, table=True):
    """A user-visible unit of work owning one or more runs."""

    __tablename__ = "platform_task_facts"
    __table_args__ = (Index("ix_platform_task_tenant_state", "tenant_id", "state"),)

    id: str = Field(sa_column=Column(String(128), primary_key=True))
    tenant_id: str = Field(sa_column=Column(String(255), nullable=False))
    created_by: str = Field(sa_column=Column(String(255), nullable=False))
    title: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    # pending | running | succeeded | failed | cancelled
    state: str = Field(default="pending", sa_column=Column(String(16), nullable=False))
    created_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))
    finished_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True), nullable=True))


class PlatformRunAttemptRecord(SQLModel, table=True):
    """One execution attempt of a run; retries append attempts rather than mutate."""

    __tablename__ = "platform_run_attempts"
    __table_args__ = (
        Index("ix_platform_attempt_tenant_run", "tenant_id", "run_id"),
        UniqueConstraint("tenant_id", "run_id", "attempt_no", name="uq_platform_attempt"),
    )

    id: str = Field(sa_column=Column(String(128), primary_key=True))
    tenant_id: str = Field(sa_column=Column(String(255), nullable=False))
    task_id: str = Field(sa_column=Column(String(128), nullable=False))
    run_id: str = Field(sa_column=Column(String(128), nullable=False))
    attempt_no: int = Field(default=1, sa_column=Column(Integer, nullable=False))
    # started | succeeded | failed | cancelled | unknown
    state: str = Field(default="started", sa_column=Column(String(16), nullable=False))
    error: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    started_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))
    finished_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True), nullable=True))
    resolved_by: str | None = Field(default=None, sa_column=Column(String(255), nullable=True))
