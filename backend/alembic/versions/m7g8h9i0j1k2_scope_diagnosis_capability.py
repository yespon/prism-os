"""Bind diagnosis Action scope to the one-use execution capability.

Revision ID: m7g8h9i0j1k2
Revises: l6f7g8h9i0j1
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "m7g8h9i0j1k2"
down_revision: str | Sequence[str] | None = "l6f7g8h9i0j1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("platform_execution_capabilities", sa.Column("action_incident_id", sa.String(255), nullable=True))


def downgrade() -> None:
    op.drop_column("platform_execution_capabilities", "action_incident_id")
