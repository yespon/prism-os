"""Add evaluation results (R5, M3 minimal).

Revision ID: t4n5o6p7q8r9
Revises: s3m4n5o6p7q8
"""

import sqlalchemy as sa

from alembic import op

revision = "t4n5o6p7q8r9"
down_revision = "s3m4n5o6p7q8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "evaluation_results",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("tenant_id", sa.String(255), nullable=False),
        sa.Column("version_id", sa.String(64), nullable=False),
        sa.Column("dataset", sa.String(128), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("passed", sa.Boolean(), nullable=False),
        sa.Column("details_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_evaluation_tenant_version", "evaluation_results", ["tenant_id", "version_id"])


def downgrade() -> None:
    count = op.get_bind().execute(sa.text("SELECT COUNT(*) FROM evaluation_results")).scalar_one()
    if count:
        raise RuntimeError("evaluation results exist; export before downgrade")
    op.drop_index("ix_evaluation_tenant_version", table_name="evaluation_results")
    op.drop_table("evaluation_results")
