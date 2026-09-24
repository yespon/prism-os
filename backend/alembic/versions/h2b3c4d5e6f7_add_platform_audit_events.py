"""add platform audit events

Revision ID: h2b3c4d5e6f7
Revises: g1a2b3c4d5e6
Create Date: 2026-09-24
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "h2b3c4d5e6f7"
down_revision: str | Sequence[str] | None = "g1a2b3c4d5e6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "platform_audit_events",
        sa.Column("id", sa.String(length=255), nullable=False),
        sa.Column("schema_version", sa.String(length=64), nullable=False),
        sa.Column("tenant_id", sa.String(length=255), nullable=False),
        sa.Column("event_type", sa.String(length=255), nullable=False),
        sa.Column("action", sa.String(length=255), nullable=False),
        sa.Column("outcome", sa.String(length=32), nullable=False),
        sa.Column("severity", sa.String(length=32), nullable=False),
        sa.Column("task_id", sa.String(length=255), nullable=False),
        sa.Column("run_id", sa.String(length=255), nullable=False),
        sa.Column("correlation_id", sa.String(length=255), nullable=False),
        sa.Column("policy_decision_id", sa.String(length=255), nullable=True),
        sa.Column("approval_id", sa.String(length=255), nullable=True),
        sa.Column("resource_id", sa.String(length=255), nullable=True),
        sa.Column("event_json", sa.JSON(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_platform_audit_tenant_recorded",
        "platform_audit_events",
        ["tenant_id", "recorded_at"],
        unique=False,
    )
    op.create_index(
        "ix_platform_audit_tenant_run",
        "platform_audit_events",
        ["tenant_id", "run_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_platform_audit_tenant_run", table_name="platform_audit_events")
    op.drop_index("ix_platform_audit_tenant_recorded", table_name="platform_audit_events")
    op.drop_table("platform_audit_events")
