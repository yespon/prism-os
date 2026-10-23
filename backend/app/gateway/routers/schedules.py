"""Schedule API: definitions CRUD, run-now, occurrence history (R3)."""

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request

from app.gateway.authorization import require_tenant_context
from app.scheduling import ScheduleService, SchedulingError

router = APIRouter(prefix="/api/schedules", tags=["schedules"])


def _service() -> ScheduleService:
    return ScheduleService()


def _definition_response(record) -> dict:
    return {
        "id": record.id, "tenant_id": record.tenant_id, "owner_user_id": record.owner_user_id,
        "name": record.name, "trigger_kind": record.trigger_kind, "cron_expr": record.cron_expr,
        "run_at": record.run_at, "interval_seconds": record.interval_seconds,
        "timezone": record.timezone, "agent_name": record.agent_name, "agent_id": record.agent_id,
        "prompt": record.prompt, "delivery_channel": record.delivery_channel,
        "delivery_target": record.delivery_target, "enabled": record.enabled,
        "created_at": record.created_at,
    }


def _occurrence_response(record) -> dict:
    return {
        "id": record.id, "schedule_id": record.schedule_id, "scheduled_at": record.scheduled_at,
        "run_id": record.run_id, "state": record.state, "started_at": record.started_at,
        "finished_at": record.finished_at,
    }


@router.get("")
async def list_schedules(request: Request, _ctx: None = Depends(require_tenant_context)) -> dict:
    tenant_id = request.state.tenant_id
    records = await _service().list_definitions(tenant_id)
    return {"schedules": [_definition_response(record) for record in records]}


@router.post("", status_code=201)
async def create_schedule(request: Request, body: dict, _ctx: None = Depends(require_tenant_context)) -> dict:
    tenant_id = request.state.tenant_id
    user_id = request.state.user_id
    run_at = body.get("run_at")
    parsed_run_at = None
    if run_at is not None:
        try:
            parsed_run_at = datetime.fromisoformat(str(run_at))
        except ValueError as error:
            raise HTTPException(400, "run_at must be an ISO-8601 datetime") from error
    try:
        record = await _service().create_definition(
            tenant_id, user_id,
            name=body.get("name") or "", trigger_kind=body.get("trigger_kind") or "",
            cron_expr=body.get("cron_expr"), run_at=parsed_run_at,
            interval_seconds=body.get("interval_seconds"),
            timezone=body.get("timezone", "Asia/Shanghai"),
            agent_name=body.get("agent_name") or "",
            agent_id=body.get("agent_id"), prompt=body.get("prompt") or "",
            delivery_channel=body.get("delivery_channel", "web"),
            delivery_target=body.get("delivery_target"),
        )
    except SchedulingError as error:
        raise HTTPException(400, str(error)) from error
    return _definition_response(record)


@router.post("/{schedule_id}/run-now", status_code=202)
async def run_now(schedule_id: str, request: Request, _ctx: None = Depends(require_tenant_context)) -> dict:
    """Trigger one immediate occurrence; collides with a same-slot trigger."""
    tenant_id = request.state.tenant_id
    service = _service()
    definitions = await service.list_definitions(tenant_id)
    definition = next((record for record in definitions if record.id == schedule_id), None)
    if definition is None:
        raise HTTPException(404, "schedule not found")
    occurrence, created = await service.claim_occurrence(tenant_id, schedule_id, datetime.now(UTC))
    return {
        "occurrence": _occurrence_response(occurrence),
        "will_execute": created and occurrence.state == "pending",
    }


@router.post("/{schedule_id}/enabled")
async def set_schedule_enabled(schedule_id: str, request: Request, body: dict,
                               _ctx: None = Depends(require_tenant_context)) -> dict:
    tenant_id = request.state.tenant_id
    user_id = request.state.user_id
    enabled = bool(body.get("enabled"))
    try:
        record = await _service().set_enabled(tenant_id, schedule_id, user_id, enabled)
    except SchedulingError as error:
        raise HTTPException(404 if "not found" in str(error) else 403, str(error)) from error
    return _definition_response(record)


@router.delete("/{schedule_id}", status_code=204)
async def delete_schedule(schedule_id: str, request: Request, _ctx: None = Depends(require_tenant_context)) -> None:
    tenant_id = request.state.tenant_id
    user_id = request.state.user_id
    try:
        await _service().delete_definition(tenant_id, schedule_id, user_id)
    except SchedulingError as error:
        raise HTTPException(404 if "not found" in str(error) else 403, str(error)) from error


@router.get("/{schedule_id}/occurrences")
async def list_occurrences(schedule_id: str, request: Request, _ctx: None = Depends(require_tenant_context)) -> dict:
    tenant_id = request.state.tenant_id
    records = await _service().list_occurrences(tenant_id, schedule_id)
    return {"occurrences": [_occurrence_response(record) for record in records]}
