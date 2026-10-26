"""Persist extension package installations (R5 leftover, M7 minimal).

Revision ID: u5o6p7q8r9s0
Revises: t4n5o6p7q8r9
"""

import sqlalchemy as sa

from alembic import op

revision = "u5o6p7q8r9s0"
down_revision = "t4n5o6p7q8r9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "extension_installations",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("tenant_id", sa.String(255), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("version", sa.String(128), nullable=False),
        sa.Column("manifest_sha256", sa.String(64), nullable=False),
        sa.Column("manifest_json", sa.Text(), nullable=False),
        sa.Column("permissions_json", sa.Text(), nullable=False),
        sa.Column("installed_by", sa.String(255), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_extension_installation_tenant", "extension_installations", ["tenant_id"])


def downgrade() -> None:
    count = op.get_bind().execute(sa.text("SELECT COUNT(*) FROM extension_installations")).scalar_one()
    if count:
        raise RuntimeError("extension installations exist; export before downgrade")
    op.drop_index("ix_extension_installation_tenant", table_name="extension_installations")
    op.drop_table("extension_installations")
