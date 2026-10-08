"""Tenant-admin ticket SecretRef lifecycle; secret input never enters a DTO."""

import json
import os
from copy import deepcopy
from datetime import UTC, datetime
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy import JSON, Text, cast, literal, update
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.alerting.ticket_secrets import TicketSecretRepository
from app.gateway.authorization import require_tenant_admin
from app.models.alerting import AlertSource
from app.models.governance import PlatformTicketSecretRecord
from app.platform.audit.repository import AuditEventRepository
from app.platform.contracts import AuditEvent, ExecutionEnvelope, IdentityRef, SecretRef, stable_platform_id
from deerflow.database.session import get_session

router = APIRouter(prefix="/api/alert-sources", tags=["ticket-secrets"])


def _body_schema(*, rotate: bool) -> dict:
    properties = {
        "webhook_url": {"type": "string", "maxLength": 8192},
        "headers": {"type": "object", "maxProperties": 64, "additionalProperties": {"type": "string"}},
    }
    required = ["webhook_url"]
    if rotate:
        properties["expected_ref_id"] = {"type": "string", "maxLength": 255}
        required.append("expected_ref_id")
    return {"requestBody": {"required": True, "content": {"application/json": {"schema": {
        "type": "object", "additionalProperties": False, "required": required, "properties": properties,
    }}}}}


class TicketSecretStatus(BaseModel):
    secret_ref: SecretRef | None = None
    active: bool = False


def _tenant(request: Request) -> str:
    tenant = require_tenant_admin(request)
    if not getattr(request.state, "user_id", None):
        raise HTTPException(status_code=401, detail="Authenticated user required")
    if os.getenv("PRISMOS_TICKET_SECRET_ADMIN_TENANT", "") != tenant:
        raise HTTPException(status_code=503, detail="Ticket secret management is disabled")
    return tenant


async def _source(session: AsyncSession, tenant: str, source_id: str) -> AlertSource:
    source = (await session.exec(select(AlertSource).where(
        AlertSource.id == source_id, AlertSource.tenant_id == tenant,
    ).with_for_update())).first()
    if source is None:
        raise HTTPException(status_code=404, detail="Alert source not found")
    return source


def _ref(source: AlertSource) -> SecretRef | None:
    try:
        value = (source.config_json or {}).get("ticket", {}).get("secret_ref")
        if value is None:
            return None
        ref = SecretRef.model_validate(value)
        if ref.tenant_id != source.tenant_id or ref.source_id != source.id:
            raise ValueError
        return ref
    except (ValueError, TypeError, AttributeError):
        raise HTTPException(status_code=409, detail="Invalid stored ticket secret binding") from None


async def _input(request: Request, *, rotate: bool) -> dict:
    # Manual parsing avoids FastAPI validation errors echoing secret input.
    body = await request.body()
    if len(body) > 64 * 1024:
        raise HTTPException(status_code=413, detail="Ticket secret input too large")
    try:
        value = json.loads(body)
    except (ValueError, UnicodeError):
        raise HTTPException(status_code=400, detail="Invalid ticket secret input") from None
    allowed = {"webhook_url", "headers"} | ({"expected_ref_id"} if rotate else set())
    if not isinstance(value, dict) or set(value) - allowed or not isinstance(value.get("webhook_url"), str):
        raise HTTPException(status_code=400, detail="Invalid ticket secret input")
    if rotate and not isinstance(value.get("expected_ref_id"), str):
        raise HTTPException(status_code=400, detail="Current reference ID required")
    value.setdefault("headers", {})
    return value


async def _audit(session: AsyncSession, request: Request, source: AlertSource, ref: SecretRef, operation: str,
                 previous_ref: SecretRef | None = None) -> None:
    now = datetime.now(UTC)
    operation_id = uuid4().hex
    execution = ExecutionEnvelope(
        tenant_id=source.tenant_id,
        task_id=stable_platform_id("task", "ticket-secret-admin", operation_id),
        run_id=stable_platform_id("run", "ticket-secret-admin", operation_id), correlation_id=source.id,
        actor=IdentityRef(kind="user", id=request.state.user_id, tenant_id=source.tenant_id),
        workload=IdentityRef(kind="service", id="ticket-secret-admin", tenant_id=source.tenant_id), occurred_at=now,
    )
    await AuditEventRepository.append_in_session(session, AuditEvent(
        tenant_id=source.tenant_id, event_id=stable_platform_id("event", "ticket-secret-admin", operation_id),
        event_type=f"secret.{operation}", action="ticket.secret.manage", outcome="succeeded",
        execution=execution, resource_id=source.id,
        payload={"secret_ref_id": ref.id, "previous_ref_id": previous_ref.id if previous_ref else None}, recorded_at=now,
    ))


async def _write(source_id: str, request: Request, session: AsyncSession, *, rotate: bool) -> TicketSecretStatus:
    tenant = _tenant(request)
    value = await _input(request, rotate=rotate)
    try:
        source = await _source(session, tenant, source_id)
        previous = deepcopy(source.config_json)
        old_ref = _ref(source)
        if (rotate and (old_ref is None or old_ref.id != value["expected_ref_id"])) or (not rotate and old_ref is not None):
            raise HTTPException(status_code=409, detail="Ticket secret reference changed")
        repository = TicketSecretRepository()
        ref = await repository.create(session, tenant, source_id, value["webhook_url"], value["headers"])
        config = deepcopy(previous)
        ticket = config.setdefault("ticket", {})
        if not isinstance(ticket, dict) or ticket.get("provider", "webhook") != "webhook":
            raise ValueError
        ticket.pop("webhook_url", None)
        ticket.pop("headers", None)
        ticket["secret_ref"] = ref.model_dump(mode="json")
        # Compare the complete stored JSON, including on SQLite where row locks are unavailable.
        result = await session.exec(update(AlertSource).where(
            AlertSource.id == source_id, AlertSource.tenant_id == tenant,
            cast(AlertSource.config_json, Text) == cast(literal(previous, type_=JSON), Text),
        ).values(config_json=config).execution_options(synchronize_session=False))
        if result.rowcount != 1:
            raise HTTPException(status_code=409, detail="Alert source configuration changed")
        if old_ref is not None:
            await repository.disable(session, tenant, source_id, old_ref)
        await _audit(session, request, source, ref, "rotated" if rotate else "created", old_ref)
        await session.commit()
        return TicketSecretStatus(secret_ref=ref, active=True)
    except HTTPException:
        await session.rollback()
        raise
    except (ValueError, PermissionError) as exc:
        await session.rollback()
        code = 503 if str(exc) == "secret encryption key required" else 400
        raise HTTPException(status_code=code, detail="Ticket secret input or storage unavailable") from None
    except Exception:
        await session.rollback()
        raise HTTPException(status_code=503, detail="Ticket secret storage unavailable") from None


@router.post("/{source_id}/ticket-secret", response_model=TicketSecretStatus, status_code=201,
             openapi_extra=_body_schema(rotate=False))
async def create_ticket_secret(source_id: str, request: Request, session: AsyncSession = Depends(get_session)):
    return await _write(source_id, request, session, rotate=False)


@router.put("/{source_id}/ticket-secret", response_model=TicketSecretStatus,
            openapi_extra=_body_schema(rotate=True))
async def rotate_ticket_secret(source_id: str, request: Request, session: AsyncSession = Depends(get_session)):
    return await _write(source_id, request, session, rotate=True)


@router.get("/{source_id}/ticket-secret", response_model=TicketSecretStatus)
async def ticket_secret_status(source_id: str, request: Request, session: AsyncSession = Depends(get_session)):
    tenant = _tenant(request)
    source = await _source(session, tenant, source_id)
    ref = _ref(source)
    if ref is None:
        return TicketSecretStatus()
    row = (await session.exec(select(PlatformTicketSecretRecord).where(
        PlatformTicketSecretRecord.id == ref.id, PlatformTicketSecretRecord.tenant_id == tenant,
        PlatformTicketSecretRecord.source_id == source_id, PlatformTicketSecretRecord.version == ref.version,
        PlatformTicketSecretRecord.purpose == ref.purpose,
    ))).first()
    if row is None:
        raise HTTPException(status_code=409, detail="Ticket secret unavailable")
    return TicketSecretStatus(secret_ref=ref, active=row.active)


@router.delete("/{source_id}/ticket-secret", response_model=TicketSecretStatus)
async def disable_ticket_secret(source_id: str, request: Request, expected_ref_id: str = Query(...),
                                session: AsyncSession = Depends(get_session)):
    tenant = _tenant(request)
    try:
        source = await _source(session, tenant, source_id)
        ref = _ref(source)
        if ref is None or ref.id != expected_ref_id:
            raise HTTPException(status_code=409, detail="Ticket secret reference changed")
        await TicketSecretRepository().disable(session, tenant, source_id, ref)
        await _audit(session, request, source, ref, "disabled")
        await session.commit()
        return TicketSecretStatus(secret_ref=ref, active=False)
    except HTTPException:
        await session.rollback()
        raise
    except Exception:
        await session.rollback()
        raise HTTPException(status_code=503, detail="Ticket secret storage unavailable") from None
