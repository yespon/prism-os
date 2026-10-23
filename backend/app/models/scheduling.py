"""Tenant-scoped schedule definitions, occurrences and delivery attempts (R3)."""

from datetime import datetime

from sqlalchemy import Column, DateTime, Index, Integer, String, Text, UniqueConstraint
from sqlmodel import Field, SQLModel


class ScheduleDefinitionRecord(SQLModel, table=True):
    __tablename__ = "schedule_definitions"
    __table_args__ = (Index("ix_schedule_definition_tenant_owner", "tenant_id", "owner_user_id"),)

    id: str = Field(sa_column=Column(String(64), primary_key=True))
    tenant_id: str = Field(sa_column=Column(String(255), nullable=False))
    owner_user_id: str = Field(sa_column=Column(String(255), nullable=False))
    name: str = Field(sa_column=Column(String(255), nullable=False))
    # cron | date | interval
    trigger_kind: str = Field(sa_column=Column(String(16), nullable=False))
    cron_expr: str | None = Field(default=None, sa_column=Column(String(128), nullable=True))
    run_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True), nullable=True))
    interval_seconds: int | None = Field(default=None, sa_column=Column(Integer, nullable=True))
    timezone: str = Field(default="Asia/Shanghai", sa_column=Column(String(64), nullable=False))
    agent_name: str = Field(sa_column=Column(String(255), nullable=False))
    agent_id: str | None = Field(default=None, sa_column=Column(String(255), nullable=True))
    prompt: str = Field(sa_column=Column(Text, nullable=False))
    # web | im
    delivery_channel: str = Field(default="web", sa_column=Column(String(16), nullable=False))
    delivery_target: str | None = Field(default=None, sa_column=Column(String(255), nullable=True))
    enabled: bool = Field(default=True, sa_column=Column(Integer, nullable=False))
    created_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))
    updated_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))


class ScheduleOccurrenceRecord(SQLModel, table=True):
    __tablename__ = "schedule_occurrences"
    __table_args__ = (
        Index("ix_schedule_occurrence_tenant_schedule", "tenant_id", "schedule_id"),
        UniqueConstraint("tenant_id", "idempotency_key", name="uq_schedule_occurrence_idempotency"),
    )

    id: str = Field(sa_column=Column(String(64), primary_key=True))
    tenant_id: str = Field(sa_column=Column(String(255), nullable=False))
    schedule_id: str = Field(sa_column=Column(String(64), nullable=False))
    scheduled_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))
    idempotency_key: str = Field(sa_column=Column(String(128), nullable=False))
    run_id: str | None = Field(default=None, sa_column=Column(String(128), nullable=True))
    # pending | running | completed | failed | skipped
    state: str = Field(default="pending", sa_column=Column(String(16), nullable=False))
    started_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True), nullable=True))
    finished_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True), nullable=True))
    created_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))


class DeliveryAttemptRecord(SQLModel, table=True):
    __tablename__ = "delivery_attempts"
    __table_args__ = (Index("ix_delivery_attempt_tenant_occurrence", "tenant_id", "occurrence_id"),)

    id: str = Field(sa_column=Column(String(64), primary_key=True))
    tenant_id: str = Field(sa_column=Column(String(255), nullable=False))
    occurrence_id: str = Field(sa_column=Column(String(64), nullable=False))
    destination: str = Field(sa_column=Column(String(512), nullable=False))
    # pending | delivered | failed
    status: str = Field(default="pending", sa_column=Column(String(16), nullable=False))
    attempts: int = Field(default=0, sa_column=Column(Integer, nullable=False))
    last_error: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    provider_message_id: str | None = Field(default=None, sa_column=Column(String(255), nullable=True))
    created_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))
