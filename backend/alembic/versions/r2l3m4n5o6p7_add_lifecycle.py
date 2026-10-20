"""Add task/run-attempt lifecycle tables (R5, M2 minimal).

Revision ID: r2l3m4n5o6p7
Revises: q1k2l3m4n5o6
"""

import sqlalchemy as sa

from alembic import op

revision = "r2l3m4n5o6p7"
down_revision = "q1k2l3m4n5o6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "platform_task_facts",
        sa.Column("id", sa.String(128), primary_key=True),
        sa.Column("tenant_id", sa.String(255), nullable=False),
        sa.Column("created_by", sa.String(255), nullable=False),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("state", sa.String(16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_platform_task_tenant_state", "platform_task_facts", ["tenant_id", "state"])

    op.create_table(
        "platform_run_attempts",
        sa.Column("id", sa.String(128), primary_key=True),
        sa.Column("tenant_id", sa.String(255), nullable=False),
        sa.Column("task_id", sa.String(128), nullable=False),
        sa.Column("run_id", sa.String(128), nullable=False),
        sa.Column("attempt_no", sa.Integer(), nullable=False),
        sa.Column("state", sa.String(16), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_by", sa.String(255), nullable=True),
        sa.UniqueConstraint("tenant_id", "run_id", "attempt_no", name="uq_platform_attempt"),
    )
    op.create_index("ix_platform_attempt_tenant_run", "platform_run_attempts", ["tenant_id", "run_id"])


def downgrade() -> None:
    for table, index in (
        ("platform_run_attempts", "ix_platform_attempt_tenant_run"),
        ("platform_task_facts", "ix_platform_task_tenant_state"),
    ):
        count = op.get_bind().execute(sa.text(f"SELECT COUNT(*) FROM {table}")).scalar_one()
        if count:
            raise RuntimeError(f"{table} rows exist; export or migrate before downgrade")
        op.drop_index(index, table_name=table)
        op.drop_table(table)
