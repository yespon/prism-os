"""Automatic diagnosis authorization stored in the original source configuration."""

import hashlib
import json

from fastapi import HTTPException
from sqlalchemy import select

from app.models.agents import CustomAgent
from app.models.alerting import AlertSource
from deerflow.database.models import Tenant, TenantMembership
from deerflow.runtime import ExecutionTrustError

KEY = "diagnosis_authorization"


def trigger(config):
    value = (config or {}).get("analysis_trigger", {})
    if not isinstance(value, dict):
        raise HTTPException(400, "Analysis trigger must be an object")
    return dict(value)


async def configure(session, tenant_id, actor_id, proposed, previous=None, *, confirm=False):
    """Ignore client authorization fields; only an authenticated admin confirms."""
    result = dict(proposed or {})
    selected = trigger(result)
    old = trigger(previous)
    incoming_grant = selected.pop(KEY, None)
    del incoming_grant
    old_grant = old.pop(KEY, None)
    agent_id = selected.get("diagnosis_agent_id")
    if not agent_id:
        result["analysis_trigger"] = selected
        return result
    if not confirm and selected == old:
        if isinstance(old_grant, dict):
            selected[KEY] = old_grant
        result["analysis_trigger"] = selected
        return result
    agent = (await session.exec(select(CustomAgent).where(CustomAgent.id == agent_id, CustomAgent.tenant_id == tenant_id, CustomAgent.user_id == "tenant-shared", CustomAgent.enabled.is_(True)))).scalars().first()
    if agent is None:
        raise HTTPException(400, "Automatic diagnosis requires a current shared Agent")
    if confirm or selected != old:
        if not actor_id or actor_id == "tenant-shared":
            raise HTTPException(401, "Current configuration administrator is required")
        from app.integrations.file_access import verify_member
        from deerflow.database.tenant_service import tenant_role_has_admin_capability

        await verify_member(session, tenant_id, actor_id)
        current_member = (await session.exec(select(TenantMembership).where(TenantMembership.tenant_id == tenant_id, TenantMembership.user_id == actor_id).execution_options(populate_existing=True))).scalars().first()
        if current_member is None or not tenant_role_has_admin_capability(current_member.role):
            raise HTTPException(403, "Current source administrator required")
        selected[KEY] = {"version": 1, "actor_id": actor_id, "agent_id": agent.id}
    elif isinstance(old_grant, dict):
        selected[KEY] = old_grant
    result["analysis_trigger"] = selected
    return result


def revision(config):
    return hashlib.sha256(json.dumps(trigger(config), sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


async def current_authorization(session, source_id, tenant_id, agent_id, *, expected_actor=None, expected_revision=None, severity=None):
    """Re-read original source, current admin membership and selected Agent."""
    source = (await session.exec(select(AlertSource).where(AlertSource.id == source_id, AlertSource.tenant_id == tenant_id, AlertSource.status == "active").execution_options(populate_existing=True))).scalars().first()
    if source is None:
        raise ExecutionTrustError("Diagnosis source is unavailable")
    selected = trigger(source.config_json)
    grant = selected.get(KEY)
    if (
        selected.get("mode", "conditional") == "manual"
        or selected.get("diagnosis_agent_id") != agent_id
        or not isinstance(grant, dict)
        or set(grant) != {"version", "actor_id", "agent_id"}
        or grant.get("version") != 1
        or grant.get("agent_id") != agent_id
        or not isinstance(grant.get("actor_id"), str)
        or not grant["actor_id"]
        or grant["actor_id"] == "tenant-shared"
    ):
        raise ExecutionTrustError("Confirm automatic diagnosis authorization in the source configuration")
    if severity is not None:
        from app.alerting.ai_analysis import should_auto_analyze
        if not should_auto_analyze(source.config_json, severity):
            raise ExecutionTrustError("Incident no longer meets the automatic diagnosis condition")
    actor_id = grant["actor_id"]
    from app.integrations.actor_authorization import verify_current_account

    verify_current_account(actor_id)
    if (expected_actor is not None and actor_id != expected_actor) or (expected_revision is not None and revision(source.config_json) != expected_revision):
        raise ExecutionTrustError("Automatic diagnosis source authorization changed")
    member = (
        (
            await session.exec(
                select(TenantMembership)
                .where(TenantMembership.tenant_id == tenant_id, TenantMembership.user_id == actor_id, TenantMembership.status == "active")
                .execution_options(populate_existing=True)
            )
        )
        .scalars()
        .first()
    )
    tenant = await session.get(Tenant, tenant_id, populate_existing=True)
    agent = await session.get(CustomAgent, agent_id, populate_existing=True)
    from deerflow.database.tenant_service import tenant_role_has_admin_capability

    if member is None or not tenant_role_has_admin_capability(member.role) or tenant is None or tenant.status != "active" or agent is None or agent.tenant_id != tenant_id or agent.user_id != "tenant-shared" or not agent.enabled:
        raise ExecutionTrustError("Automatic diagnosis authorization is no longer current")
    return actor_id, agent
