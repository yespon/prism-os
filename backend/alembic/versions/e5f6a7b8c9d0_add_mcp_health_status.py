"""add_mcp_health_status

Revision ID: e5f6a7b8c9d0
Revises: d4f5e6a7b8c9
Create Date: 2026-05-07 10:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e5f6a7b8c9d0"
down_revision: str | Sequence[str] | None = "d4f5e6a7b8c9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "tenant_mcp_servers",
        sa.Column("health_status", sa.String(), nullable=False, server_default="unknown"),
    )
    op.add_column(
        "tenant_mcp_servers",
        sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("tenant_mcp_servers", "last_checked_at")
    op.drop_column("tenant_mcp_servers", "health_status")
