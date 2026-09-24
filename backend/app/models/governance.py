from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Column, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint
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


class PlatformPolicyDecisionRecord(SQLModel, table=True):
    __tablename__ = "platform_policy_decisions"
    __table_args__ = (
        UniqueConstraint("tenant_id", "request_id", name="uq_platform_policy_tenant_request"),
        Index("ix_platform_policy_tenant_run", "tenant_id", "run_id"),
    )

    id: str = Field(sa_column=Column(String(255), primary_key=True))
    tenant_id: str = Field(sa_column=Column(String(255), nullable=False))
    request_id: str = Field(sa_column=Column(String(255), nullable=False))
    run_id: str = Field(sa_column=Column(String(255), nullable=False))
    verdict: str = Field(sa_column=Column(String(32), nullable=False))
    policy_id: str = Field(sa_column=Column(String(255), nullable=False))
    policy_version: str = Field(sa_column=Column(String(255), nullable=False))
    context_hash: str = Field(sa_column=Column(String(64), nullable=False))
    decision_json: dict[str, Any] = Field(sa_column=Column(JSON, nullable=False))
    decided_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))
    expires_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))


class PlatformApprovalRecord(SQLModel, table=True):
    __tablename__ = "platform_approvals"
    __table_args__ = (
        UniqueConstraint("tenant_id", "decision_id", name="uq_platform_approval_tenant_decision"),
        Index("ix_platform_approval_tenant_status", "tenant_id", "status", "expires_at"),
    )

    id: str = Field(sa_column=Column(String(255), primary_key=True))
    tenant_id: str = Field(sa_column=Column(String(255), nullable=False))
    decision_id: str = Field(sa_column=Column(String(255), ForeignKey("platform_policy_decisions.id"), nullable=False))
    request_id: str = Field(sa_column=Column(String(255), nullable=False))
    run_id: str = Field(sa_column=Column(String(255), nullable=False))
    status: str = Field(sa_column=Column(String(32), nullable=False))
    version: int = Field(default=0, sa_column=Column(Integer, nullable=False, default=0))
    approval_json: dict[str, Any] = Field(sa_column=Column(JSON, nullable=False))
    created_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))
    expires_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))
    decided_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True), nullable=True))
    consumed_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True), nullable=True))
