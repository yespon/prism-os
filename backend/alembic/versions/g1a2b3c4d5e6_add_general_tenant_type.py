"""add_general_tenant_type — add 'general' as valid tenant_type value.

Revision ID: g1a2b3c4d5e6
Revises: f1a2b3c4d5e6
Create Date: 2026-07-21
"""
from collections.abc import Sequence

revision: str = "g1a2b3c4d5e6"
down_revision: str | None = "f1a2b3c4d5e6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # No schema change needed — tenant_type is a VARCHAR column.
    # This migration is a marker for the semantic change.
    pass


def downgrade() -> None:
    pass