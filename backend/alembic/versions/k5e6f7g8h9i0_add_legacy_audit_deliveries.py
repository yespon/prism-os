"""add replayable M1 legacy audit deliveries

Revision ID: k5e6f7g8h9i0
Revises: j4d5e6f7g8h9
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "k5e6f7g8h9i0"
down_revision: str | Sequence[str] | None = "j4d5e6f7g8h9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "platform_legacy_audit_deliveries",
        sa.Column("id", sa.String(length=255), primary_key=True),
        sa.Column("tenant_id", sa.String(length=255), nullable=False),
        sa.Column("event_id", sa.String(length=255), sa.ForeignKey("platform_audit_events.id"), nullable=False),
        sa.Column("destination", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("error_category", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tenant_id", "event_id", "destination", name="uq_platform_legacy_delivery"),
    )
    op.create_index("ix_platform_legacy_delivery_tenant_status", "platform_legacy_audit_deliveries", ["tenant_id", "status"])


def downgrade() -> None:
    op.drop_index("ix_platform_legacy_delivery_tenant_status", table_name="platform_legacy_audit_deliveries")
    op.drop_table("platform_legacy_audit_deliveries")
