"""Bounded, atomic ticket credential migration for an exclusive maintenance process."""

import logging
import os
import sys
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import JSON, Text, cast, literal, text, update
from sqlmodel import select

from app.alerting.ticket_secrets import TicketSecretRepository, _validate_material, ticket_secret_ref
from app.models.alerting import AlertSource
from app.models.governance import PlatformTicketSecretRecord
from app.platform.audit.repository import AuditEventRepository
from app.platform.contracts import AuditEvent, ExecutionEnvelope, IdentityRef, stable_platform_id
from deerflow.database.secrets_crypto import encrypt_text_strict

EXPECTED_HEAD = "n8h9i0j1k2l3"


class TicketMigrationError(Exception):
    """Only fixed reason codes may leave the maintenance boundary."""


@dataclass(frozen=True)
class TicketMigrationReport:
    tenant_id: str
    mode: str
    scanned: int
    eligible: int
    migrated: int
    sources: list[dict[str, str]]

    def as_dict(self) -> dict:
        return asdict(self)


@contextmanager
def maintenance_privacy():
    # Standalone CLI only: SQL JSON CAS parameters and async driver worker logs
    # can carry the old plaintext. Disable process logging, including workers,
    # for this short maintenance scope, then restore the previous threshold.
    previous = logging.root.manager.disable
    logging.disable(sys.maxsize)
    try:
        yield
    finally:
        logging.disable(previous)


async def _replace_config(session, source, previous, config) -> None:
    result = await session.exec(
        update(AlertSource)
        .where(
            AlertSource.id == source.id,
            AlertSource.tenant_id == source.tenant_id,
            cast(AlertSource.config_json, Text) == cast(literal(previous, type_=JSON), Text),
        )
        .values(config_json=config)
        .execution_options(synchronize_session=False)
    )
    if result.rowcount != 1:
        raise TicketMigrationError("source_configuration_changed")


async def _audit(session, source, ref) -> None:
    now = datetime.now(UTC)
    operation = uuid4().hex
    execution = ExecutionEnvelope(
        tenant_id=source.tenant_id,
        task_id=stable_platform_id("task", "ticket-secret-migration", operation),
        run_id=stable_platform_id("run", "ticket-secret-migration", operation),
        correlation_id=source.id,
        actor=IdentityRef(kind="service", id="ticket-secret-migration", tenant_id=source.tenant_id),
        workload=IdentityRef(kind="service", id="ticket-secret-migration", tenant_id=source.tenant_id),
        occurred_at=now,
    )
    await AuditEventRepository.append_in_session(
        session,
        AuditEvent(
            tenant_id=source.tenant_id,
            event_id=stable_platform_id("event", "ticket-secret-migration", operation),
            event_type="secret.migrated",
            action="ticket.secret.manage",
            outcome="succeeded",
            execution=execution,
            resource_id=source.id,
            payload={"secret_ref_id": ref.id},
            recorded_at=now,
        ),
    )


async def _classify(session, source) -> str:
    config = source.config_json
    if not isinstance(config, dict):
        raise TicketMigrationError("invalid_source_configuration")
    if "ticket" not in config or config["ticket"] == {}:
        return "no_ticket"
    ticket = config["ticket"]
    if not isinstance(ticket, dict):
        raise TicketMigrationError("invalid_ticket_configuration")
    if "secret_ref" in ticket:
        try:
            ref = ticket_secret_ref(ticket, source.tenant_id, source.id)
            if ticket.get("provider", "webhook") != "webhook":
                raise ValueError
            row = (
                await session.exec(
                    select(PlatformTicketSecretRecord).where(
                        PlatformTicketSecretRecord.id == ref.id,
                        PlatformTicketSecretRecord.tenant_id == source.tenant_id,
                        PlatformTicketSecretRecord.source_id == source.id,
                        PlatformTicketSecretRecord.purpose == ref.purpose,
                        PlatformTicketSecretRecord.version == ref.version,
                    )
                )
            ).first()
            if row is None:
                raise ValueError
            # Disabled refs are valid migrated storage. Never activate them.
            TicketSecretRepository._decode(row, ref, os.getenv("DEERFLOW_SECRETS_ENCRYPTION_KEY"))
        except (ValueError, PermissionError, TypeError):
            raise TicketMigrationError("reference_or_key_unavailable") from None
        return "already_referenced"
    if ticket.get("provider", "webhook") != "webhook":
        return "unsupported_provider"
    try:
        _validate_material(ticket.get("webhook_url"), ticket.get("headers", {}))
    except (ValueError, TypeError):
        raise TicketMigrationError("invalid_legacy_credentials") from None
    return "eligible"


async def migrate_ticket_secret_refs(session_factory, tenant_id: str, *, apply: bool = False, source_ids: tuple[str, ...] = (), limit: int = 100) -> TicketMigrationReport:
    """Use only in a standalone maintenance process, never in the Gateway.

    Dry-run rolls back its read transaction; apply commits one entire selected
    tenant batch. No partial success, secret values, or driver errors are returned.
    """
    if not isinstance(tenant_id, str) or not tenant_id.strip() or len(tenant_id) > 255:
        raise TicketMigrationError("invalid_tenant")
    if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 1000:
        raise TicketMigrationError("invalid_limit")
    if any(not isinstance(value, str) or not value.strip() or len(value) > 255 for value in source_ids):
        raise TicketMigrationError("invalid_source_selection")
    commit_started = False
    committed = False
    with maintenance_privacy():
        try:
            async with session_factory() as session:
                async with session.begin():
                    heads = (await session.exec(text("SELECT version_num FROM alembic_version"))).scalars().all()
                    if heads != [EXPECTED_HEAD]:
                        raise TicketMigrationError("schema_head_mismatch")
                    statement = select(AlertSource).where(AlertSource.tenant_id == tenant_id).order_by(AlertSource.id).limit(limit + 1)
                    if source_ids:
                        statement = statement.where(AlertSource.id.in_(source_ids))
                    if apply:
                        statement = statement.with_for_update()
                    sources = (await session.exec(statement)).all()
                    if len(sources) > limit:
                        raise TicketMigrationError("batch_limit_exceeded")
                    if source_ids and {source.id for source in sources} != set(source_ids):
                        raise TicketMigrationError("source_selection_unavailable")
                    states = [(source, await _classify(session, source)) for source in sources]
                    eligible = [source for source, state in states if state == "eligible"]
                    if eligible:
                        try:
                            encrypt_text_strict("ticket-migration-preflight", os.getenv("DEERFLOW_SECRETS_ENCRYPTION_KEY"))
                        except ValueError:
                            raise TicketMigrationError("encryption_key_unavailable") from None
                    if apply:
                        repository = TicketSecretRepository()
                        for source in eligible:
                            previous = deepcopy(source.config_json)
                            config = deepcopy(previous)
                            ticket = config["ticket"]
                            ref = await repository.create(session, tenant_id, source.id, ticket["webhook_url"], ticket.get("headers", {}))
                            ticket.pop("webhook_url")
                            ticket.pop("headers", None)
                            ticket["secret_ref"] = ref.model_dump(mode="json")
                            await _replace_config(session, source, previous, config)
                            await _audit(session, source, ref)
                    report = TicketMigrationReport(
                        tenant_id=tenant_id,
                        mode="apply" if apply else "dry-run",
                        scanned=len(sources),
                        eligible=len(eligible),
                        migrated=len(eligible) if apply else 0,
                        sources=[{"source_id": source.id, "status": "migrated" if apply and state == "eligible" else state} for source, state in states],
                    )
                    if not apply:
                        await session.rollback()
                    else:
                        commit_started = True
                committed = True
                return report
        except TicketMigrationError:
            raise
        except Exception:
            if committed:
                return report
            if commit_started:
                raise TicketMigrationError("commit_outcome_unknown") from None
            raise TicketMigrationError("storage_or_audit_unavailable") from None
