from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, Column, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
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


class PlatformActionSubmissionRecord(SQLModel, table=True):
    __tablename__ = "platform_action_submissions"
    __table_args__ = (
        UniqueConstraint("tenant_id", "decision_id", name="uq_platform_submission_tenant_decision"),
        Index("ix_platform_submission_tenant_status", "tenant_id", "status"),
    )

    idempotency_key: str = Field(sa_column=Column(String(255), primary_key=True))
    tenant_id: str = Field(sa_column=Column(String(255), nullable=False))
    decision_id: str = Field(sa_column=Column(String(255), ForeignKey("platform_policy_decisions.id"), nullable=False))
    approval_id: str | None = Field(default=None, sa_column=Column(String(255), ForeignKey("platform_approvals.id"), nullable=True))
    action: str = Field(sa_column=Column(String(255), nullable=False))
    status: str = Field(sa_column=Column(String(32), nullable=False))
    ticket_id: str | None = Field(default=None, sa_column=Column(String(255), nullable=True))
    ticket_url: str | None = Field(default=None, sa_column=Column(String(2048), nullable=True))
    provider: str | None = Field(default=None, sa_column=Column(String(255), nullable=True))
    created_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))
    claimed_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True), nullable=True))
    submitted_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True), nullable=True))


class PlatformLegacyAuditDeliveryRecord(SQLModel, table=True):
    __tablename__ = "platform_legacy_audit_deliveries"
    __table_args__ = (
        UniqueConstraint("tenant_id", "event_id", "destination", name="uq_platform_legacy_delivery"),
        Index("ix_platform_legacy_delivery_tenant_status", "tenant_id", "status"),
    )

    id: str = Field(sa_column=Column(String(255), primary_key=True))
    tenant_id: str = Field(sa_column=Column(String(255), nullable=False))
    event_id: str = Field(sa_column=Column(String(255), ForeignKey("platform_audit_events.id"), nullable=False))
    destination: str = Field(sa_column=Column(String(64), nullable=False))
    status: str = Field(sa_column=Column(String(32), nullable=False))
    attempts: int = Field(default=0, sa_column=Column(Integer, nullable=False))
    error_category: str | None = Field(default=None, sa_column=Column(String(128), nullable=True))
    created_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))
    updated_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))


class PlatformThreadBindingRecord(SQLModel, table=True):
    __tablename__ = "platform_thread_bindings"
    __table_args__ = (Index("ix_platform_thread_owner", "tenant_id", "user_id"),)

    thread_id: str = Field(sa_column=Column(String(255), primary_key=True))
    tenant_id: str = Field(sa_column=Column(String(255), nullable=False))
    user_id: str = Field(sa_column=Column(String(255), nullable=False))
    agent_name: str | None = Field(default=None, sa_column=Column(String(255), nullable=True))
    legacy_claim: bool = Field(default=False, nullable=False)
    created_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))


class PlatformExecutionCapabilityRecord(SQLModel, table=True):
    __tablename__ = "platform_execution_capabilities"
    __table_args__ = (Index("ix_platform_capability_expiry", "expires_at"),)

    token_hash: str = Field(sa_column=Column(String(64), primary_key=True))
    tenant_id: str = Field(sa_column=Column(String(255), nullable=False))
    user_id: str = Field(sa_column=Column(String(255), nullable=False))
    thread_id: str = Field(sa_column=Column(String(255), nullable=False))
    agent_name: str | None = Field(default=None, sa_column=Column(String(255), nullable=True))
    action_incident_id: str | None = Field(default=None, sa_column=Column(String(255), nullable=True))
    created_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))
    expires_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))
    consumed_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True), nullable=True))


class PlatformTicketSecretRecord(SQLModel, table=True):
    __tablename__ = "platform_ticket_secrets"
    __table_args__ = (Index("ix_ticket_secret_tenant_source", "tenant_id", "source_id"),)

    id: str = Field(sa_column=Column(String(255), primary_key=True))
    tenant_id: str = Field(sa_column=Column(String(255), nullable=False))
    source_id: str = Field(sa_column=Column(String(255), nullable=False))
    purpose: str = Field(sa_column=Column(String(64), nullable=False))
    version: int = Field(sa_column=Column(Integer, nullable=False))
    encrypted_payload: str = Field(repr=False, sa_column=Column(Text, nullable=False))
    active: bool = Field(default=True, sa_column=Column(Boolean, nullable=False))
    created_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))
