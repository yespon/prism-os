"""Tenant-scoped knowledge bases, documents, members and connectors (R2)."""

from datetime import datetime

from sqlalchemy import Column, DateTime, Index, Integer, String, Text, UniqueConstraint
from sqlmodel import Field, SQLModel


class KnowledgeBaseRecord(SQLModel, table=True):
    __tablename__ = "knowledge_bases"
    __table_args__ = (Index("ix_knowledge_base_tenant_owner", "tenant_id", "owner_user_id"),)

    id: str = Field(sa_column=Column(String(64), primary_key=True))
    tenant_id: str = Field(sa_column=Column(String(255), nullable=False))
    owner_user_id: str = Field(sa_column=Column(String(255), nullable=False))
    name: str = Field(sa_column=Column(String(255), nullable=False))
    # private: owner + explicit members only; tenant: every tenant member can read.
    visibility: str = Field(default="private", sa_column=Column(String(16), nullable=False))
    created_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))


class KnowledgeDocumentRecord(SQLModel, table=True):
    __tablename__ = "knowledge_documents"
    __table_args__ = (Index("ix_knowledge_document_tenant_kb", "tenant_id", "kb_id"),)

    id: str = Field(sa_column=Column(String(64), primary_key=True))
    tenant_id: str = Field(sa_column=Column(String(255), nullable=False))
    kb_id: str = Field(sa_column=Column(String(64), nullable=False))
    filename: str = Field(sa_column=Column(String(512), nullable=False))
    content_type: str = Field(sa_column=Column(String(255), nullable=False))
    file_object_id: str = Field(sa_column=Column(String(64), nullable=False))
    version: int = Field(default=1, sa_column=Column(Integer, nullable=False))
    content_hash: str = Field(sa_column=Column(String(64), nullable=False))
    index_state: str = Field(default="pending", sa_column=Column(String(16), nullable=False))
    index_error: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    indexed_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True), nullable=True))
    created_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))


class KnowledgeMemberRecord(SQLModel, table=True):
    __tablename__ = "knowledge_members"
    __table_args__ = (
        Index("ix_knowledge_member_tenant_kb", "tenant_id", "kb_id"),
        UniqueConstraint("tenant_id", "kb_id", "user_id", name="uq_knowledge_member"),
    )

    id: str = Field(sa_column=Column(String(64), primary_key=True))
    tenant_id: str = Field(sa_column=Column(String(255), nullable=False))
    kb_id: str = Field(sa_column=Column(String(64), nullable=False))
    user_id: str = Field(sa_column=Column(String(255), nullable=False))
    granted_by: str = Field(sa_column=Column(String(255), nullable=False))
    created_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))


class ConnectorCatalogRecord(SQLModel, table=True):
    __tablename__ = "connector_catalog"
    __table_args__ = (Index("ix_connector_catalog_kind", "kind"),)

    id: str = Field(sa_column=Column(String(64), primary_key=True))
    # NULL tenant_id = platform-level catalog seed; otherwise tenant-custom.
    tenant_id: str | None = Field(default=None, sa_column=Column(String(255), nullable=True))
    kind: str = Field(sa_column=Column(String(64), nullable=False))
    display_name: str = Field(sa_column=Column(String(255), nullable=False))
    config_schema_json: str = Field(sa_column=Column("schema_json", Text, nullable=False))
    created_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))


class ConnectorInstanceRecord(SQLModel, table=True):
    __tablename__ = "connector_instances"
    __table_args__ = (Index("ix_connector_instance_tenant_owner", "tenant_id", "owner_user_id"),)

    id: str = Field(sa_column=Column(String(64), primary_key=True))
    tenant_id: str = Field(sa_column=Column(String(255), nullable=False))
    catalog_id: str = Field(sa_column=Column(String(64), nullable=False))
    owner_user_id: str = Field(sa_column=Column(String(255), nullable=False))
    name: str = Field(sa_column=Column(String(255), nullable=False))
    secret_ref_id: str | None = Field(default=None, sa_column=Column(String(255), nullable=True))
    status: str = Field(default="configured", sa_column=Column(String(32), nullable=False))
    last_health: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    created_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))
