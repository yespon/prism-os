"""Asset management domain models — DB-backed host and credential configuration.

All tables carry tenant_id for multi-tenant isolation and follow the
conventions established in deerflow.database.models.
"""

from datetime import UTC, datetime

from sqlalchemy import Column, DateTime, UniqueConstraint, func
from sqlmodel import Field, SQLModel


def _utcnow() -> datetime:
    return datetime.now(UTC)


class Keychain(SQLModel, table=True):
    """User-managed credentials (passwords, ssh keys)."""

    __tablename__ = "keychains"
    __table_args__ = (
        UniqueConstraint("tenant_id", "user_id", "name", name="uq_keychains_tenant_user_name"),
    )

    id: str = Field(primary_key=True)
    tenant_id: str = Field(index=True)
    user_id: str = Field(index=True)
    name: str = Field(index=True)
    type: str = Field(description="Type of credential: 'password' or 'key'")
    value: str = Field(description="Encrypted credential value")
    created_at: datetime = Field(
        default_factory=_utcnow,
        sa_column=Column(DateTime(timezone=True), nullable=False, server_default=func.now()),
    )
    updated_at: datetime = Field(
        default_factory=_utcnow,
        sa_column=Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()),
    )


class AssetGroup(SQLModel, table=True):
    """User-managed asset groups/folders."""

    __tablename__ = "asset_groups"
    __table_args__ = (
        UniqueConstraint("tenant_id", "user_id", "name", name="uq_asset_groups_tenant_user_name"),
    )

    id: str = Field(primary_key=True)
    tenant_id: str = Field(index=True)
    user_id: str = Field(index=True)
    name: str = Field(index=True)
    description: str = Field(default="")
    created_at: datetime = Field(
        default_factory=_utcnow,
        sa_column=Column(DateTime(timezone=True), nullable=False, server_default=func.now()),
    )
    updated_at: datetime = Field(
        default_factory=_utcnow,
        sa_column=Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()),
    )


class LocalAsset(SQLModel, table=True):
    """User-managed SSH hosts."""

    __tablename__ = "local_assets"
    __table_args__ = (
        UniqueConstraint("tenant_id", "user_id", "name", name="uq_local_assets_tenant_user_name"),
    )

    id: str = Field(primary_key=True)
    tenant_id: str = Field(index=True)
    user_id: str = Field(index=True)
    name: str = Field(index=True, description="Alias/display name for the host")
    ip: str = Field(index=True)
    port: int = Field(default=22)
    username: str = Field(default="root")
    keychain_id: str | None = Field(default=None, foreign_key="keychains.id")
    group_id: str | None = Field(default=None, foreign_key="asset_groups.id")
    is_favorite: bool = Field(default=False)
    comment: str = Field(default="")
    
    created_at: datetime = Field(
        default_factory=_utcnow,
        sa_column=Column(DateTime(timezone=True), nullable=False, server_default=func.now()),
    )
    updated_at: datetime = Field(
        default_factory=_utcnow,
        sa_column=Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()),
    )
