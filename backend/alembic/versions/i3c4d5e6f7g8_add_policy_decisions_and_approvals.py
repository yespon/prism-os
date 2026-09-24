"""add M1 Policy Decision and Approval facts

Revision ID: i3c4d5e6f7g8
Revises: h2b3c4d5e6f7
Create Date: 2026-09-24
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "i3c4d5e6f7g8"
down_revision: str | Sequence[str] | None = "h2b3c4d5e6f7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "platform_policy_decisions",
        sa.Column("id", sa.String(length=255), nullable=False),
        sa.Column("tenant_id", sa.String(length=255), nullable=False),
        sa.Column("request_id", sa.String(length=255), nullable=False),
        sa.Column("run_id", sa.String(length=255), nullable=False),
        sa.Column("verdict", sa.String(length=32), nullable=False),
        sa.Column("policy_id", sa.String(length=255), nullable=False),
        sa.Column("policy_version", sa.String(length=255), nullable=False),
        sa.Column("context_hash", sa.String(length=64), nullable=False),
        sa.Column("decision_json", sa.JSON(), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "request_id", name="uq_platform_policy_tenant_request"),
    )
    op.create_index(
        "ix_platform_policy_tenant_run",
        "platform_policy_decisions",
        ["tenant_id", "run_id"],
        unique=False,
    )
    op.create_table(
        "platform_approvals",
        sa.Column("id", sa.String(length=255), nullable=False),
        sa.Column("tenant_id", sa.String(length=255), nullable=False),
        sa.Column("decision_id", sa.String(length=255), nullable=False),
        sa.Column("request_id", sa.String(length=255), nullable=False),
        sa.Column("run_id", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("approval_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["decision_id"], ["platform_policy_decisions.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "decision_id", name="uq_platform_approval_tenant_decision"),
    )
    op.create_index(
        "ix_platform_approval_tenant_status",
        "platform_approvals",
        ["tenant_id", "status", "expires_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_platform_approval_tenant_status", table_name="platform_approvals")
    op.drop_table("platform_approvals")
    op.drop_index("ix_platform_policy_tenant_run", table_name="platform_policy_decisions")
    op.drop_table("platform_policy_decisions")
