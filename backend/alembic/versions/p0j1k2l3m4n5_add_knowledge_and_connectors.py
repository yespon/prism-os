"""Add tenant-scoped knowledge bases, documents, members and connectors.

Revision ID: p0j1k2l3m4n5
Revises: o9i0j1k2l3m4
"""

import sqlalchemy as sa

from alembic import op

revision = "p0j1k2l3m4n5"
down_revision = "o9i0j1k2l3m4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "knowledge_bases",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("tenant_id", sa.String(255), nullable=False),
        sa.Column("owner_user_id", sa.String(255), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("visibility", sa.String(16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_knowledge_base_tenant_owner", "knowledge_bases", ["tenant_id", "owner_user_id"])

    op.create_table(
        "knowledge_documents",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("tenant_id", sa.String(255), nullable=False),
        sa.Column("kb_id", sa.String(64), nullable=False),
        sa.Column("filename", sa.String(512), nullable=False),
        sa.Column("content_type", sa.String(255), nullable=False),
        sa.Column("file_object_id", sa.String(64), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("index_state", sa.String(16), nullable=False),
        sa.Column("index_error", sa.Text(), nullable=True),
        sa.Column("indexed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_knowledge_document_tenant_kb", "knowledge_documents", ["tenant_id", "kb_id"])

    op.create_table(
        "knowledge_members",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("tenant_id", sa.String(255), nullable=False),
        sa.Column("kb_id", sa.String(64), nullable=False),
        sa.Column("user_id", sa.String(255), nullable=False),
        sa.Column("granted_by", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tenant_id", "kb_id", "user_id", name="uq_knowledge_member"),
    )
    op.create_index("ix_knowledge_member_tenant_kb", "knowledge_members", ["tenant_id", "kb_id"])

    op.create_table(
        "connector_catalog",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("tenant_id", sa.String(255), nullable=True),
        sa.Column("kind", sa.String(64), nullable=False),
        sa.Column("display_name", sa.String(255), nullable=False),
        sa.Column("schema_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_connector_catalog_kind", "connector_catalog", ["kind"])

    op.create_table(
        "connector_instances",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("tenant_id", sa.String(255), nullable=False),
        sa.Column("catalog_id", sa.String(64), nullable=False),
        sa.Column("owner_user_id", sa.String(255), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("secret_ref_id", sa.String(255), nullable=True),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("last_health", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_connector_instance_tenant_owner", "connector_instances", ["tenant_id", "owner_user_id"])


def downgrade() -> None:
    for table, index in (
        ("connector_instances", "ix_connector_instance_tenant_owner"),
        ("connector_catalog", "ix_connector_catalog_kind"),
        ("knowledge_members", "ix_knowledge_member_tenant_kb"),
        ("knowledge_documents", "ix_knowledge_document_tenant_kb"),
        ("knowledge_bases", "ix_knowledge_base_tenant_owner"),
    ):
        count = op.get_bind().execute(sa.text(f"SELECT COUNT(*) FROM {table}")).scalar_one()
        if count:
            raise RuntimeError(f"{table} rows exist; export or migrate before downgrade")
        op.drop_index(index, table_name=table)
        op.drop_table(table)
