"""add M1 Action submission facts

Revision ID: j4d5e6f7g8h9
Revises: i3c4d5e6f7g8
Create Date: 2026-09-24
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "j4d5e6f7g8h9"
down_revision: str | Sequence[str] | None = "i3c4d5e6f7g8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "platform_action_submissions",
        sa.Column("idempotency_key", sa.String(length=255), nullable=False),
        sa.Column("tenant_id", sa.String(length=255), nullable=False),
        sa.Column("decision_id", sa.String(length=255), nullable=False),
        sa.Column("approval_id", sa.String(length=255), nullable=True),
        sa.Column("action", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("ticket_id", sa.String(length=255), nullable=True),
        sa.Column("ticket_url", sa.String(length=2048), nullable=True),
        sa.Column("provider", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["decision_id"], ["platform_policy_decisions.id"]),
        sa.ForeignKeyConstraint(["approval_id"], ["platform_approvals.id"]),
        sa.PrimaryKeyConstraint("idempotency_key"),
        sa.UniqueConstraint("tenant_id", "decision_id", name="uq_platform_submission_tenant_decision"),
    )
    op.create_index(
        "ix_platform_submission_tenant_status", "platform_action_submissions", ["tenant_id", "status"],
    )


def downgrade() -> None:
    op.drop_index("ix_platform_submission_tenant_status", table_name="platform_action_submissions")
    op.drop_table("platform_action_submissions")
