"""Add agent versions and deployments (R5, M4 minimal).

Revision ID: s3m4n5o6p7q8
Revises: r2l3m4n5o6p7
"""

import sqlalchemy as sa

from alembic import op

revision = "s3m4n5o6p7q8"
down_revision = "r2l3m4n5o6p7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "agent_versions",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("tenant_id", sa.String(255), nullable=False),
        sa.Column("agent_id", sa.String(255), nullable=False),
        sa.Column("version_hash", sa.String(64), nullable=False),
        sa.Column("version_no", sa.Integer(), nullable=False),
        sa.Column("config_json", sa.Text(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("published_by", sa.String(255), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_agent_version_tenant_agent", "agent_versions", ["tenant_id", "agent_id"])

    op.create_table(
        "agent_deployments",
        sa.Column("tenant_id", sa.String(255), primary_key=True),
        sa.Column("agent_id", sa.String(255), primary_key=True),
        sa.Column("version_id", sa.String(64), nullable=False),
        sa.Column("previous_version_id", sa.String(64), nullable=True),
        sa.Column("deployed_by", sa.String(255), nullable=False),
        sa.Column("deployed_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_agent_deployment_tenant_agent", "agent_deployments", ["tenant_id", "agent_id"])


def downgrade() -> None:
    count = op.get_bind().execute(sa.text("SELECT COUNT(*) FROM agent_deployments")).scalar_one()
    if count:
        raise RuntimeError("agent deployment rows exist; un-deploy before downgrade")
    op.drop_index("ix_agent_deployment_tenant_agent", table_name="agent_deployments")
    op.drop_table("agent_deployments")

    count = op.get_bind().execute(sa.text("SELECT COUNT(*) FROM agent_versions")).scalar_one()
    if count:
        raise RuntimeError("agent version rows exist; export history before downgrade")
    op.drop_index("ix_agent_version_tenant_agent", table_name="agent_versions")
    op.drop_table("agent_versions")
