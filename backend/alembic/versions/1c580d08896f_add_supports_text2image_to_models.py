"""add supports_text2image to models

Revision ID: 1c580d08896f
Revises: ef71a511e35d
Create Date: 2026-06-05 22:48:56.370672

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '1c580d08896f'
down_revision: str | Sequence[str] | None = 'ef71a511e35d'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('tenant_model_configs', sa.Column('supports_text2image', sa.Boolean(), server_default='0', nullable=False))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('tenant_model_configs', 'supports_text2image')
