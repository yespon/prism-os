from pathlib import Path


def test_platform_audit_migration_extends_one_head() -> None:
    migration = Path("alembic/versions/h2b3c4d5e6f7_add_platform_audit_events.py").read_text(
        encoding="utf-8"
    )
    assert 'revision: str = "h2b3c4d5e6f7"' in migration
    assert 'down_revision: str | Sequence[str] | None = "g1a2b3c4d5e6"' in migration
    assert 'op.create_table(' in migration
    assert '"platform_audit_events"' in migration
    assert '"ix_platform_audit_tenant_recorded"' in migration
    assert '"ix_platform_audit_tenant_run"' in migration
    assert 'op.drop_table("platform_audit_events")' in migration
