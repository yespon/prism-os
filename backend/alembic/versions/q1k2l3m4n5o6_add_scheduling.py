"""Add schedule definitions, occurrences and delivery attempts.

Revision ID: q1k2l3m4n5o6
Revises: p0j1k2l3m4n5
"""

import sqlalchemy as sa

from alembic import op

revision = "q1k2l3m4n5o6"
down_revision = "p0j1k2l3m4n5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "schedule_definitions",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("tenant_id", sa.String(255), nullable=False),
        sa.Column("owner_user_id", sa.String(255), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("trigger_kind", sa.String(16), nullable=False),
        sa.Column("cron_expr", sa.String(128), nullable=True),
        sa.Column("run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("interval_seconds", sa.Integer(), nullable=True),
        sa.Column("timezone", sa.String(64), nullable=False),
        sa.Column("agent_name", sa.String(255), nullable=False),
        sa.Column("agent_id", sa.String(255), nullable=True),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("delivery_channel", sa.String(16), nullable=False),
        sa.Column("delivery_target", sa.String(255), nullable=True),
        sa.Column("enabled", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_schedule_definition_tenant_owner", "schedule_definitions", ["tenant_id", "owner_user_id"])

    op.create_table(
        "schedule_occurrences",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("tenant_id", sa.String(255), nullable=False),
        sa.Column("schedule_id", sa.String(64), nullable=False),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("run_id", sa.String(128), nullable=True),
        sa.Column("state", sa.String(16), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tenant_id", "idempotency_key", name="uq_schedule_occurrence_idempotency"),
    )
    op.create_index("ix_schedule_occurrence_tenant_schedule", "schedule_occurrences", ["tenant_id", "schedule_id"])

    op.create_table(
        "delivery_attempts",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("tenant_id", sa.String(255), nullable=False),
        sa.Column("occurrence_id", sa.String(64), nullable=False),
        sa.Column("destination", sa.String(512), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("provider_message_id", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_delivery_attempt_tenant_occurrence", "delivery_attempts", ["tenant_id", "occurrence_id"])


def downgrade() -> None:
    for table, index in (
        ("delivery_attempts", "ix_delivery_attempt_tenant_occurrence"),
        ("schedule_occurrences", "ix_schedule_occurrence_tenant_schedule"),
        ("schedule_definitions", "ix_schedule_definition_tenant_owner"),
    ):
        count = op.get_bind().execute(sa.text(f"SELECT COUNT(*) FROM {table}")).scalar_one()
        if count:
            raise RuntimeError(f"{table} rows exist; export or migrate before downgrade")
        op.drop_index(index, table_name=table)
        op.drop_table(table)
