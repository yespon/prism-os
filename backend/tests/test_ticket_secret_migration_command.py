"""Atomic tenant migration with real SQLModel storage and CLI process checks."""

import json
import logging
import os
import subprocess
import sys
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import Session
from sqlmodel import SQLModel, select
from sqlmodel.ext.asyncio.session import AsyncSession
from starlette.requests import Request

from app.alerting import ticket_provider, ticket_secret_migration, ticket_secrets
from app.alerting.escalation import apply_escalation_actions
from app.alerting.ticket_secret_migration import EXPECTED_HEAD, TicketMigrationError, migrate_ticket_secret_refs
from app.alerting.ticket_secrets import TicketSecretRepository
from app.gateway.routers import alerts
from app.models.alerting import AlertRule, AlertSource, Incident, IncidentAction, IncidentSignalLink, RawAlert, Signal
from app.models.governance import PlatformAuditEventRecord, PlatformTicketSecretRecord
from app.platform.audit.repository import AuditEventRepository
from app.platform.contracts import SecretRef
from scripts.migrate_ticket_secret_refs import _database_url, parser

pytestmark = pytest.mark.anyio
URL = "https://tickets.example/migrate-private-path?token=migrate-private-query"
HEADER = "Bearer migrate-private-header"
PRIVATE = ("migrate-private-path", "migrate-private-query", "migrate-private-header")
NOW = datetime(2026, 10, 9, 9, tzinfo=UTC)


def legacy():
    return {"ticket": {"provider": "webhook", "webhook_url": URL, "headers": {"Authorization": HEADER}, "template": {"title": "{{ incident.title }}"}}, "analysis_trigger": {"enabled": False}, "other": [1, 2]}


@pytest.fixture
async def state(tmp_path, monkeypatch):
    monkeypatch.setenv("DEERFLOW_SECRETS_ENCRYPTION_KEY", "migration-test-key")
    path = tmp_path / "migration.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{path}")
    async with engine.begin() as connection:
        await connection.run_sync(SQLModel.metadata.create_all)
        await connection.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32) PRIMARY KEY)"))
        await connection.execute(text("INSERT INTO alembic_version VALUES (:head)"), {"head": EXPECTED_HEAD})
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        session.add_all(
            [
                AlertSource(id="source-a", tenant_id="tenant-a", name="monitor", config_json=legacy()),
                AlertSource(id="source-disabled", tenant_id="tenant-a", name="disabled", status="disabled", config_json=legacy()),
                AlertSource(id="source-empty", tenant_id="tenant-a", name="empty"),
                AlertSource(id="source-b", tenant_id="tenant-b", name="other tenant", config_json=legacy()),
            ]
        )
        await session.commit()
    config = tmp_path / "config.yaml"
    config.write_text(f"database:\n  url: sqlite+aiosqlite:///{path}\n  echo: true\n")
    result = SimpleNamespace(engine=engine, factory=factory, config=config, path=path)
    yield result
    await engine.dispose()


async def snapshot(state):
    async with state.factory() as session:
        return {model.__tablename__: [row.model_dump(mode="json") for row in (await session.exec(select(model).order_by(model.id))).all()] for model in (AlertSource, PlatformTicketSecretRecord, PlatformAuditEventRecord)}


def assert_private_absent(value):
    for private in PRIVATE:
        assert private not in str(value)


async def test_default_dry_run_reads_without_mutation_and_suppresses_driver_logs(state, caplog):
    before = await snapshot(state)
    caplog.set_level(logging.DEBUG)
    previous = logging.root.manager.disable
    result = await migrate_ticket_secret_refs(state.factory, "tenant-a")
    assert result.mode == "dry-run" and result.scanned == 3 and result.eligible == 2 and result.migrated == 0
    assert logging.root.manager.disable == previous
    assert_private_absent(caplog.text)
    caplog.clear()
    assert await snapshot(state) == before
    assert_private_absent(result.as_dict())


async def test_apply_is_tenant_scoped_atomic_preserves_other_config_and_is_idempotent(state):
    result = await migrate_ticket_secret_refs(state.factory, "tenant-a", apply=True)
    assert result.migrated == 2
    assert_private_absent(result.as_dict())
    async with state.factory() as session:
        rows = (await session.exec(select(PlatformTicketSecretRecord))).all()
        audits = (await session.exec(select(PlatformAuditEventRecord))).all()
        assert len(rows) == len(audits) == 2
        assert all(row.event_type == "secret.migrated" for row in audits)
        assert_private_absent([row.model_dump_json() for row in rows + audits])
        for source_id in ("source-a", "source-disabled"):
            source = await session.get(AlertSource, source_id)
            config = source.config_json
            assert config["other"] == [1, 2] and config["analysis_trigger"] == {"enabled": False}
            assert config["ticket"]["template"] == legacy()["ticket"]["template"]
            assert_private_absent(config)
            ref = SecretRef.model_validate(config["ticket"]["secret_ref"])
            material = await TicketSecretRepository().read(session, "tenant-a", source_id, ref)
            assert material.webhook_url == URL and material.headers == {"Authorization": HEADER}
        assert (await session.get(AlertSource, "source-disabled")).status == "disabled"
        assert (await session.get(AlertSource, "source-b")).config_json == legacy()
    before = await snapshot(state)
    repeated = await migrate_ticket_secret_refs(state.factory, "tenant-a", apply=True)
    assert repeated.eligible == repeated.migrated == 0 and await snapshot(state) == before


async def test_missing_key_and_invalid_late_row_make_zero_writes(state, monkeypatch):
    before = await snapshot(state)
    monkeypatch.delenv("DEERFLOW_SECRETS_ENCRYPTION_KEY")
    with pytest.raises(TicketMigrationError, match="encryption_key_unavailable"):
        await migrate_ticket_secret_refs(state.factory, "tenant-a", apply=True)
    assert await snapshot(state) == before
    monkeypatch.setenv("DEERFLOW_SECRETS_ENCRYPTION_KEY", "migration-test-key")
    async with state.factory() as session:
        source = await session.get(AlertSource, "source-disabled")
        source.config_json = {"ticket": {"webhook_url": URL, "headers": {"Authorization": HEADER + "\r\n"}}}
        await session.commit()
    before = await snapshot(state)
    with pytest.raises(TicketMigrationError, match="invalid_legacy_credentials") as error:
        await migrate_ticket_secret_refs(state.factory, "tenant-a", apply=True)
    assert_private_absent(str(error.value))
    assert await snapshot(state) == before


async def test_second_audit_failure_rolls_back_the_first_source_and_secret(state, monkeypatch):
    before = await snapshot(state)
    original = AuditEventRepository.append_in_session
    count = 0

    async def fail_second(session, event):
        nonlocal count
        count += 1
        if count == 2:
            raise RuntimeError(HEADER)
        await original(session, event)

    monkeypatch.setattr(AuditEventRepository, "append_in_session", fail_second)
    with pytest.raises(TicketMigrationError, match="storage_or_audit_unavailable") as error:
        await migrate_ticket_secret_refs(state.factory, "tenant-a", apply=True)
    assert count == 2 and await snapshot(state) == before
    assert_private_absent(str(error.value))


async def test_cas_conflict_rolls_back_all_selected_sources(state, monkeypatch):
    before = await snapshot(state)
    original = ticket_secret_migration._replace_config
    count = 0

    async def conflict(session, source, previous, config):
        nonlocal count
        count += 1
        if count == 2:
            # Change the compared JSON in the same transaction to force actual CAS failure.
            await session.exec(text("UPDATE alert_sources SET config_json = :config WHERE id = :id"), params={"config": json.dumps({"changed": True}), "id": source.id})
        await original(session, source, previous, config)

    monkeypatch.setattr(ticket_secret_migration, "_replace_config", conflict)
    with pytest.raises(TicketMigrationError, match="source_configuration_changed"):
        await migrate_ticket_secret_refs(state.factory, "tenant-a", apply=True)
    assert count == 2 and await snapshot(state) == before


@pytest.mark.parametrize("limit", [0, 1001, -1, True])
async def test_limit_is_bounded(state, limit):
    before = await snapshot(state)
    with pytest.raises(TicketMigrationError, match="invalid_limit"):
        await migrate_ticket_secret_refs(state.factory, "tenant-a", apply=True, limit=limit)
    assert await snapshot(state) == before


async def test_batch_overflow_requires_explicit_selection_and_cross_tenant_selection_rejects(state):
    before = await snapshot(state)
    with pytest.raises(TicketMigrationError, match="batch_limit_exceeded"):
        await migrate_ticket_secret_refs(state.factory, "tenant-a", apply=True, limit=1)
    with pytest.raises(TicketMigrationError, match="source_selection_unavailable"):
        await migrate_ticket_secret_refs(state.factory, "tenant-a", apply=True, source_ids=("source-b",))
    assert await snapshot(state) == before
    result = await migrate_ticket_secret_refs(state.factory, "tenant-a", apply=True, source_ids=("source-a",), limit=1)
    assert result.scanned == result.migrated == 1


@pytest.mark.parametrize("change", ["inline", "wrong-tenant", "missing-row", "wrong-key", "disabled"])
async def test_existing_reference_is_checked_without_reenabling_or_rebinding(state, monkeypatch, change):
    await migrate_ticket_secret_refs(state.factory, "tenant-a", apply=True)
    async with state.factory() as session:
        source = await session.get(AlertSource, "source-a")
        config = deepcopy(source.config_json)
        ref_id = config["ticket"]["secret_ref"]["id"]
        row = await session.get(PlatformTicketSecretRecord, ref_id)
        if change == "inline":
            config["ticket"]["headers"] = {"Authorization": HEADER}
        elif change == "wrong-tenant":
            config["ticket"]["secret_ref"]["tenant_id"] = "tenant-b"
        elif change == "missing-row":
            await session.delete(row)
        elif change == "disabled":
            row.active = False
        else:
            monkeypatch.setenv("DEERFLOW_SECRETS_ENCRYPTION_KEY", "wrong-key")
        source.config_json = config
        await session.commit()
    before = await snapshot(state)
    if change == "disabled":
        result = await migrate_ticket_secret_refs(state.factory, "tenant-a", apply=True)
        assert result.migrated == 0
    else:
        with pytest.raises(TicketMigrationError, match="reference_or_key_unavailable"):
            await migrate_ticket_secret_refs(state.factory, "tenant-a", apply=True)
    assert await snapshot(state) == before


async def test_old_schema_is_rejected_without_writing(state):
    async with state.factory() as session:
        await session.exec(text("UPDATE alembic_version SET version_num = 'm7g8h9i0j1k2'"))
        await session.commit()
    before = await snapshot(state)
    with pytest.raises(TicketMigrationError, match="schema_head_mismatch"):
        await migrate_ticket_secret_refs(state.factory, "tenant-a", apply=True)
    assert await snapshot(state) == before


async def test_unsupported_provider_is_reported_without_mutation(state):
    async with state.factory() as session:
        source = await session.get(AlertSource, "source-a")
        source.config_json = {"ticket": {"provider": "future-provider", "headers": {"Authorization": HEADER}}}
        await session.commit()
    before = await snapshot(state)
    result = await migrate_ticket_secret_refs(state.factory, "tenant-a", source_ids=("source-a",), apply=True)
    assert result.migrated == 0 and result.sources[0]["status"] == "unsupported_provider"
    assert await snapshot(state) == before
    assert_private_absent(result.as_dict())


async def test_cli_defaults_to_dry_run_and_does_not_echo_errors_or_create_fallback_database(state):
    backend = Path(__file__).resolve().parents[1]
    args = [sys.executable, "-m", "scripts.migrate_ticket_secret_refs", "--tenant", "tenant-a", "--config", str(state.config)]
    before = await snapshot(state)
    result = subprocess.run(args, cwd=backend, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    output = json.loads(result.stdout)
    assert output["mode"] == "dry-run" and output["migrated"] == 0 and output["eligible"] == 2
    assert not result.stderr and await snapshot(state) == before
    assert_private_absent(result.stdout)
    env = dict(os.environ)
    env.pop("DEERFLOW_SECRETS_ENCRYPTION_KEY", None)
    result = subprocess.run(args + ["--apply"], cwd=backend, env=env, capture_output=True, text=True, timeout=30)
    assert result.returncode == 2 and json.loads(result.stdout)["migrated"] == 0
    assert not result.stderr and await snapshot(state) == before
    assert_private_absent(result.stdout)
    state.config.write_text("database: {}\n")
    with pytest.raises(TicketMigrationError, match="explicit_database_configuration_required"):
        _database_url(str(state.config))
    missing = state.path.parent / "nonexistent.db"
    state.config.write_text(f"database:\n  url: sqlite+aiosqlite:///{missing}\n")
    with pytest.raises(TicketMigrationError):
        _database_url(str(state.config))
    assert not missing.exists()
    assert parser().parse_args(["--tenant", "tenant-a"]).apply is False


async def test_cli_apply_is_repeatable_and_private(state):
    args = [sys.executable, "-m", "scripts.migrate_ticket_secret_refs", "--tenant", "tenant-a", "--config", str(state.config), "--apply"]
    backend = Path(__file__).resolve().parents[1]
    for expected in (2, 0):
        result = subprocess.run(args, cwd=backend, capture_output=True, text=True, timeout=30)
        assert result.returncode == 0, result.stderr
        assert json.loads(result.stdout)["migrated"] == expected
        assert_private_absent(result.stdout)
        assert not result.stderr


async def test_migrated_binding_is_consumed_by_manual_and_rule_paths(state, monkeypatch):
    await migrate_ticket_secret_refs(state.factory, "tenant-a", apply=True)
    async with state.factory() as session:
        for index in (1, 2):
            session.add_all(
                [
                    Incident(id=f"incident-{index}", tenant_id="tenant-a", incident_key=f"INC-{index}", title="Alarm", first_seen_at=NOW, last_seen_at=NOW),
                    RawAlert(id=f"raw-{index}", tenant_id="tenant-a", source_id="source-a", payload_hash=f"hash-{index}", received_at=NOW),
                    Signal(id=f"signal-{index}", tenant_id="tenant-a", raw_alert_id=f"raw-{index}", fingerprint=f"fp-{index}", title="Alarm"),
                    IncidentSignalLink(id=f"link-{index}", tenant_id="tenant-a", incident_id=f"incident-{index}", signal_id=f"signal-{index}"),
                ]
            )
        await session.commit()
    monkeypatch.setattr(ticket_secrets, "get_session_factory", lambda: state.factory)
    calls = []
    client_class = httpx.AsyncClient

    async def receive(request):
        assert str(request.url) == URL and request.headers["Authorization"] == HEADER
        calls.append(request)
        return httpx.Response(200, json={"id": f"T-{len(calls)}"})

    monkeypatch.setattr(ticket_provider.httpx, "AsyncClient", lambda **kwargs: client_class(transport=httpx.MockTransport(receive), **kwargs))
    request = Request({"type": "http", "state": {"tenant_id": "tenant-a", "tenant_role": "admin", "user_id": "admin-a"}})
    async with state.factory() as session:
        manual = await alerts.create_incident_ticket("incident-1", request=request, session=session)
        assert manual["ticket_id"] == "T-1"
    async with state.factory() as session:
        incident = await session.get(Incident, "incident-2")
        rule = AlertRule(id="rule-a", tenant_id="tenant-a", name="auto", rule_type="escalation", action_json={"action": "auto_ticket"})
        await apply_escalation_actions(incident, [rule], session)
        await session.commit()
        assert incident.ticket_id == "T-2"
    assert len(calls) == 2
    async with state.factory() as session:
        assert_private_absent([row.model_dump_json() for row in (await session.exec(select(IncidentAction))).all()])


async def test_lost_commit_acknowledgment_is_unknown_and_can_be_reconciled(state):
    def lose_ack(_session):
        raise RuntimeError(HEADER)

    event.listen(Session, "after_commit", lose_ack)
    try:
        with pytest.raises(TicketMigrationError, match="commit_outcome_unknown") as error:
            await migrate_ticket_secret_refs(state.factory, "tenant-a", apply=True)
        assert_private_absent(str(error.value))
    finally:
        event.remove(Session, "after_commit", lose_ack)
    async with state.factory() as session:
        assert len((await session.exec(select(PlatformTicketSecretRecord))).all()) == 2
        assert len((await session.exec(select(PlatformAuditEventRecord))).all()) == 2
    result = await migrate_ticket_secret_refs(state.factory, "tenant-a")
    assert result.migrated == result.eligible == 0


async def test_cli_unknown_does_not_claim_zero_writes(state, monkeypatch):
    from scripts import migrate_ticket_secret_refs as command

    async def unknown(*args, **kwargs):
        raise TicketMigrationError("commit_outcome_unknown")

    monkeypatch.setattr(command, "migrate_ticket_secret_refs", unknown)
    args = command.parser().parse_args(["--tenant", "tenant-a", "--config", str(state.config), "--apply"])
    result = await command.run(args)
    assert result["status"] == "unknown" and result["migrated"] is None
    assert_private_absent(result)
