"""Terminal agent domain models — DB-backed sessions, chat history, and audit logs.

All tables carry tenant_id for multi-tenant isolation.
"""

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, Column, DateTime, Text, func
from sqlmodel import Field, SQLModel


def _utcnow() -> datetime:
    return datetime.now(UTC)


class TerminalSession(SQLModel, table=True):
    """Represents a long-running PTY/SSH session context."""

    __tablename__ = "terminal_sessions"

    id: str = Field(primary_key=True)
    tenant_id: str = Field(index=True)
    user_id: str = Field(index=True)
    asset_id: str = Field(index=True)
    mode: str = Field(default="cmd", description="'cmd' or 'agent'")
    is_active: bool = Field(default=True)
    
    created_at: datetime = Field(
        default_factory=_utcnow,
        sa_column=Column(DateTime(timezone=True), nullable=False, server_default=func.now()),
    )
    updated_at: datetime = Field(
        default_factory=_utcnow,
        sa_column=Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()),
    )


class ChatSession(SQLModel, table=True):
    """Represents a chat history thread for the Terminal Agent."""

    __tablename__ = "terminal_chat_sessions"

    id: str = Field(primary_key=True)
    tenant_id: str = Field(index=True)
    user_id: str = Field(index=True)
    terminal_session_id: str = Field(index=True, description="The associated SSH session")
    title: str = Field(default="未命名会话")
    model_name: str = Field(default="gpt-4o")
    
    # Store messages as JSON for now. A production system might normalize this.
    messages: list[dict[str, Any]] = Field(default=[], sa_column=Column(JSON))
    todos: list[dict[str, Any]] = Field(default=[], sa_column=Column(JSON))
    
    created_at: datetime = Field(
        default_factory=_utcnow,
        sa_column=Column(DateTime(timezone=True), nullable=False, server_default=func.now()),
    )
    updated_at: datetime = Field(
        default_factory=_utcnow,
        sa_column=Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()),
    )


class CommandAuditLog(SQLModel, table=True):
    """Audit log for commands executed on assets."""

    __tablename__ = "terminal_audit_logs"

    id: str = Field(primary_key=True)
    tenant_id: str = Field(index=True)
    user_id: str = Field(index=True)
    terminal_session_id: str = Field(index=True)
    asset_id: str = Field(index=True)
    
    command: str = Field(sa_column=Column(Text))
    mode: str = Field(description="'cmd' or 'agent'")
    security_action: str = Field(description="'allow', 'ask', or 'block'")
    approved_by: str | None = Field(default=None, description="user_id if approved manually")
    
    stdout: str | None = Field(default=None, sa_column=Column(Text))
    stderr: str | None = Field(default=None, sa_column=Column(Text))
    return_code: int | None = Field(default=None)
    
    executed_at: datetime = Field(
        default_factory=_utcnow,
        sa_column=Column(DateTime(timezone=True), nullable=False, server_default=func.now()),
    )


class TerminalSecuritySettings(SQLModel, table=True):
    """Terminal security and auto-approval configurations."""

    __tablename__ = "terminal_security_settings"

    id: str = Field(primary_key=True)
    tenant_id: str = Field(index=True)
    user_id: str = Field(index=True)
    
    # Stores both security_config and auto_approval in JSON format
    config: dict[str, Any] = Field(default={}, sa_column=Column(JSON))

