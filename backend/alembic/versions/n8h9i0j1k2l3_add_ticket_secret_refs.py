"""Add encrypted, source-scoped ticket secret records.

Revision ID: n8h9i0j1k2l3
Revises: m7g8h9i0j1k2
"""

import sqlalchemy as sa

from alembic import op

revision = "n8h9i0j1k2l3"
down_revision = "m7g8h9i0j1k2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "platform_ticket_secrets",
        sa.Column("id", sa.String(255), primary_key=True),
        sa.Column("tenant_id", sa.String(255), nullable=False),
        sa.Column("source_id", sa.String(255), nullable=False),
        sa.Column("purpose", sa.String(64), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("encrypted_payload", sa.Text(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_ticket_secret_tenant_source", "platform_ticket_secrets", ["tenant_id", "source_id"])


def downgrade() -> None:
    count = op.get_bind().execute(sa.text("SELECT COUNT(*) FROM platform_ticket_secrets")).scalar_one()
    if count:
        raise RuntimeError("ticket secret records exist; restore or migrate references before downgrade")
    op.drop_index("ix_ticket_secret_tenant_source", table_name="platform_ticket_secrets")
    op.drop_table("platform_ticket_secrets")
