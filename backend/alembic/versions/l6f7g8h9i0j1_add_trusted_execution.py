"""add M1 trusted thread bindings and one-use execution capabilities

Revision ID: l6f7g8h9i0j1
Revises: k5e6f7g8h9i0
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "l6f7g8h9i0j1"
down_revision: str | Sequence[str] | None = "k5e6f7g8h9i0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "platform_thread_bindings",
        sa.Column("thread_id", sa.String(255), primary_key=True),
        sa.Column("tenant_id", sa.String(255), nullable=False),
        sa.Column("user_id", sa.String(255), nullable=False),
        sa.Column("agent_name", sa.String(255), nullable=True),
        sa.Column("legacy_claim", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_platform_thread_owner", "platform_thread_bindings", ["tenant_id", "user_id"])
    op.create_table(
        "platform_execution_capabilities",
        sa.Column("token_hash", sa.String(64), primary_key=True),
        sa.Column("tenant_id", sa.String(255), nullable=False),
        sa.Column("user_id", sa.String(255), nullable=False),
        sa.Column("thread_id", sa.String(255), nullable=False),
        sa.Column("agent_name", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_platform_capability_expiry", "platform_execution_capabilities", ["expires_at"])


def downgrade() -> None:
    op.drop_index("ix_platform_capability_expiry", table_name="platform_execution_capabilities")
    op.drop_table("platform_execution_capabilities")
    op.drop_index("ix_platform_thread_owner", table_name="platform_thread_bindings")
    op.drop_table("platform_thread_bindings")
