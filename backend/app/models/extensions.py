"""Persisted extension package installations (R5 leftover, M7 minimal)."""

from datetime import datetime

from sqlalchemy import Column, DateTime, Index, String, Text
from sqlmodel import Field, SQLModel


class ExtensionInstallationRecord(SQLModel, table=True):
    """A validated manifest installation, persisted across restarts.

    The registry never loads or executes package code (gateway-process red
    line); this table records what was installed, its manifest digest and
    permission set, and its enablement state.
    """

    __tablename__ = "extension_installations"
    __table_args__ = (
        Index("ix_extension_installation_tenant", "tenant_id"),
    )

    id: str = Field(sa_column=Column(String(64), primary_key=True))
    tenant_id: str = Field(sa_column=Column(String(255), nullable=False))
    name: str = Field(sa_column=Column(String(255), nullable=False))
    version: str = Field(sa_column=Column(String(128), nullable=False))
    manifest_sha256: str = Field(sa_column=Column(String(64), nullable=False))
    manifest_json: str = Field(sa_column=Column(Text, nullable=False))
    permissions_json: str = Field(sa_column=Column(Text, nullable=False))
    installed_by: str = Field(sa_column=Column(String(255), nullable=False))
    enabled: bool = Field(nullable=False)
    created_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))
