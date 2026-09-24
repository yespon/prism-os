from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Column, DateTime, Index, String
from sqlmodel import Field, SQLModel


class PlatformAuditEventRecord(SQLModel, table=True):
    __tablename__ = "platform_audit_events"
    __table_args__ = (
        Index("ix_platform_audit_tenant_recorded", "tenant_id", "recorded_at"),
        Index("ix_platform_audit_tenant_run", "tenant_id", "run_id"),
    )

    id: str = Field(sa_column=Column(String(255), primary_key=True))
    schema_version: str = Field(sa_column=Column(String(64), nullable=False))
    tenant_id: str = Field(sa_column=Column(String(255), nullable=False))
    event_type: str = Field(sa_column=Column(String(255), nullable=False))
    action: str = Field(sa_column=Column(String(255), nullable=False))
    outcome: str = Field(sa_column=Column(String(32), nullable=False))
    severity: str = Field(sa_column=Column(String(32), nullable=False))
    task_id: str = Field(sa_column=Column(String(255), nullable=False))
    run_id: str = Field(sa_column=Column(String(255), nullable=False))
    correlation_id: str = Field(sa_column=Column(String(255), nullable=False))
    policy_decision_id: str | None = Field(default=None, sa_column=Column(String(255), nullable=True))
    approval_id: str | None = Field(default=None, sa_column=Column(String(255), nullable=True))
    resource_id: str | None = Field(default=None, sa_column=Column(String(255), nullable=True))
    event_json: dict[str, Any] = Field(sa_column=Column(JSON, nullable=False))
    occurred_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))
    recorded_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))
