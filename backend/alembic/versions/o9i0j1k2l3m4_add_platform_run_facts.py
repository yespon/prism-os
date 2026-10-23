"""Add minimal platform run facts with frozen snapshots.

Revision ID: o9i0j1k2l3m4
Revises: n8h9i0j1k2l3
"""

import sqlalchemy as sa

from alembic import op

revision = "o9i0j1k2l3m4"
down_revision = "n8h9i0j1k2l3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "platform_run_facts",
        sa.Column("run_id", sa.String(128), primary_key=True),
        sa.Column("tenant_id", sa.String(255), nullable=False),
        sa.Column("task_id", sa.String(128), nullable=False),
        sa.Column("correlation_id", sa.String(128), nullable=True),
        sa.Column("thread_id", sa.String(255), nullable=True),
        sa.Column("workload_id", sa.String(255), nullable=False),
        sa.Column("actor_id", sa.String(255), nullable=True),
        sa.Column("state", sa.String(32), nullable=False),
        sa.Column("snapshot_json", sa.Text(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_platform_run_fact_tenant_task", "platform_run_facts", ["tenant_id", "task_id"]
    )
    op.create_index(
        "ix_platform_run_fact_tenant_thread", "platform_run_facts", ["tenant_id", "thread_id"]
    )


def downgrade() -> None:
    count = op.get_bind().execute(sa.text("SELECT COUNT(*) FROM platform_run_facts")).scalar_one()
    if count:
        raise RuntimeError("platform run facts exist; export or migrate history before downgrade")
    op.drop_index("ix_platform_run_fact_tenant_thread", table_name="platform_run_facts")
    op.drop_index("ix_platform_run_fact_tenant_task", table_name="platform_run_facts")
    op.drop_table("platform_run_facts")
