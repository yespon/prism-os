"""PrismOS integrations for the standalone DeerFlow harness runtime."""

from __future__ import annotations

import asyncio
import concurrent.futures
import uuid
from copy import deepcopy
from types import SimpleNamespace

from sqlalchemy import select

from app.agent.prompts import TERMINAL_AGENT_SYSTEM_PROMPT
from app.agent.terminal_tools import get_terminal_tools, set_terminal_context
from app.alerting.governed_ticket_tool import governed_ticket_tools
from app.models.agents import CustomAgent
from app.platform.execution.trust import ExecutionCapabilityRepository
from deerflow.database.session import get_session_factory
from deerflow.runtime import (
    ExecutionTrustError,
    NativeAgentContext,
    register_agent_config_provider,
    register_agent_context_provider,
    register_agent_identity_provider,
    register_agent_persistence_provider,
    register_execution_validator,
    register_file_access_provider,
    register_governed_action_provider,
    register_skill_command_provider,
    register_skill_file_provider,
    register_skill_prompt_provider,
    register_terminal_agent_provider,
)


def _run_async(coro):
    """Run an async provider from synchronous LangGraph callbacks."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        return executor.submit(asyncio.run, coro).result()


def _load_agent(name: str, user_id: str | None, tenant_id: str | None) -> CustomAgent | None:
    async def _query() -> CustomAgent | None:
        session_factory = get_session_factory()
        async with session_factory() as session:
            statement = select(CustomAgent).where(
                CustomAgent.tenant_id == tenant_id,
                CustomAgent.user_id.in_([user_id, "tenant-shared"]),
                CustomAgent.name == name,
            )
            result = await session.exec(statement)
            agents = result.scalars().all()
            for agent in agents:
                if agent.user_id == user_id:
                    return agent
            return agents[0] if agents else None

    return _run_async(_query())


async def verify_native_selection(session, tenant_id, user_id, agent_name, agent_id, source_id=None, source_revision=None, *, diagnosis_incident_id=None):
    from deerflow.database.models import Tenant, TenantMembership

    agent = await session.get(CustomAgent, agent_id, populate_existing=True)
    member = (await session.exec(select(TenantMembership).where(TenantMembership.tenant_id == tenant_id, TenantMembership.user_id == user_id, TenantMembership.status == "active").execution_options(populate_existing=True))).scalars().first()
    tenant = await session.get(Tenant, tenant_id, populate_existing=True)
    if agent is None or agent.tenant_id != tenant_id or agent.name != agent_name or not agent.enabled or agent.user_id not in {user_id, "tenant-shared"} or member is None or tenant is None or tenant.status != "active":
        raise ExecutionTrustError("Native Agent selection unavailable")
    from app.integrations.actor_authorization import verify_current_account

    verify_current_account(user_id)
    severity = None
    if diagnosis_incident_id is not None:
        from app.models.alerting import Incident

        incident = (await session.exec(select(Incident).where(Incident.id == diagnosis_incident_id, Incident.tenant_id == tenant_id).execution_options(populate_existing=True))).scalars().first()
        if incident is None:
            raise ExecutionTrustError("Current diagnosis incident unavailable")
        severity = incident.severity
    if source_id is not None:
        from app.alerting.diagnosis_authorization import current_authorization

        await current_authorization(session, source_id, tenant_id, agent_id, expected_actor=user_id, expected_revision=source_revision, severity=severity)


async def verify_runtime_selection(session, context):
    """Recheck the original owner and protected diagnosis facts at tool use."""
    from app.integrations.file_access import verify_thread

    binding = await verify_thread(session, context.get("tenant_id"), context.get("user_id"), context.get("thread_id"))
    if binding.agent_name is not None and binding.agent_name != (context.get("agent_name") or "__default__"):
        raise ExecutionTrustError("Current thread Agent unavailable")
    source = context.get("diagnosis_source_id")
    revision = context.get("diagnosis_source_revision")
    incident = context.get("diagnosis_incident_id")
    if source is not None and (not isinstance(revision, str) or not revision or not incident):
        raise ExecutionTrustError("Protected automatic diagnosis context incomplete")
    if source is None and revision is not None:
        raise ExecutionTrustError("Protected diagnosis source unavailable")
    if not context.get("agent_id"):
        if context.get("agent_name") not in {None, "__default__"} or source is not None or incident is not None:
            raise ExecutionTrustError("Current Agent selection incomplete")
        return
    await verify_native_selection(session, context.get("tenant_id"), context.get("user_id"), context.get("agent_name"), context.get("agent_id"), source, revision, diagnosis_incident_id=incident)
    if incident is not None:
        from app.alerting.diagnosis_run_control import DiagnosisStopRequested
        from app.models.alerting import Incident

        current = await session.get(Incident, incident, populate_existing=True)
        if current.diagnosis_status == "cancelled" or (current.diagnosis_status == "failed" and (current.diagnosis_error or "").startswith("cancel_requested:")):
            raise DiagnosisStopRequested("Diagnosis cancellation requested")
        if current.thread_id is not None and current.thread_id != context.get("thread_id"):
            raise ExecutionTrustError("Diagnosis thread has been replaced")


def _load_agent_by_id(name, user_id, tenant_id, agent_id):
    async def load():
        async with get_session_factory()() as session:
            await verify_native_selection(session, tenant_id, user_id, name, agent_id)
            return await session.get(CustomAgent, agent_id)

    return _run_async(load())

def _load_agent_context(name, user_id, tenant_id, agent_id, skill_name=None, resource_id=None, *, diagnosis_source_id=None, diagnosis_source_revision=None, diagnosis_incident_id=None):
    from app.integrations.agent_skill_references import current_skill_prompt
    from app.integrations.skill_reference_transactions import begin_reference_transaction

    async def load():
        for _ in range(3):
            async with get_session_factory()() as session:
                await begin_reference_transaction(session, tenant_id)
                await verify_native_selection(session, tenant_id, user_id, name, agent_id, diagnosis_source_id, diagnosis_source_revision, diagnosis_incident_id=diagnosis_incident_id)
                record = await session.get(CustomAgent, agent_id)
                values = deepcopy(record.model_dump())
                section = await current_skill_prompt(session, name, tenant_id, user_id, skill_name, resource_id, selected_agent_id=agent_id)
                # Re-read current authority after assembling file content. A
                # non-participating writer must not silently create a hybrid.
                await verify_native_selection(session, tenant_id, user_id, name, agent_id, diagnosis_source_id, diagnosis_source_revision, diagnosis_incident_id=diagnosis_incident_id)
                if record.model_dump() == values:
                    return NativeAgentContext(SimpleNamespace(**values), section)
        raise ExecutionTrustError("Native Agent configuration changed during assembly")

    try:
        return _run_async(load())
    except Exception:
        raise ExecutionTrustError("Current native Agent context or use authorization is unavailable") from None


def _list_agents(user_id: str | None, tenant_id: str | None) -> list[CustomAgent]:
    async def _query() -> list[CustomAgent]:
        session_factory = get_session_factory()
        async with session_factory() as session:
            statement = select(CustomAgent).where(CustomAgent.tenant_id == tenant_id, CustomAgent.user_id == user_id).order_by(CustomAgent.name)
            result = await session.exec(statement)
            return list(result.scalars().all())

    return _run_async(_query())


def _persist_agent(*, agent_name: str, soul: str, description: str, user_id: str | None, tenant_id: str | None) -> None:
    async def _create() -> None:
        session_factory = get_session_factory()
        async with session_factory() as session:
            session.add(
                CustomAgent(
                    id=str(uuid.uuid4()),
                    tenant_id=tenant_id or "default",
                    user_id=user_id or "unknown",
                    name=agent_name,
                    description=description,
                    system_prompt=soul,
                    enabled=True,
                    created_by=user_id,
                )
            )
            await session.commit()

    _run_async(_create())


async def _consume_graph_capability(token, tenant_id, user_id, thread_id, agent_name):
    from app.integrations.file_access import verify_thread

    async with get_session_factory()() as session:
        binding = await verify_thread(session, tenant_id, user_id, thread_id)
        if binding.agent_name is not None and binding.agent_name != (agent_name or "__default__"):
            raise ExecutionTrustError("Current thread Agent unavailable")
    return await ExecutionCapabilityRepository(get_session_factory(), native_selection_validator=verify_native_selection).consume(token, tenant_id, user_id, thread_id, agent_name, include_selection=True, include_context=True)


def _current_skill_prompt(agent_name, tenant_id, user_id, skill_name=None, resource_id=None, agent_id=None):
    if not tenant_id and not agent_id:
        return None
    from app.integrations.agent_skill_references import current_skill_prompt

    async def load():
        async with get_session_factory()() as session:
            return await current_skill_prompt(session, agent_name, tenant_id, user_id, skill_name, resource_id, selected_agent_id=agent_id)

    try:
        return _run_async(load())
    except Exception:
        raise ExecutionTrustError("Current Agent Skill choice or use authorization is unavailable") from None


def _scoped_context(context):
    """Resolve old named executions once; pin the original identity per use."""
    if not context.get("tenant_id") and not context.get("agent_id"):
        return None
    protected = dict(context)
    if not protected.get("agent_id") and protected.get("agent_name") not in {None, "__default__"}:
        async def resolve():
            from app.integrations.file_access import verify_thread

            async with get_session_factory()() as session:
                await verify_thread(session, protected.get("tenant_id"), protected.get("user_id"), protected.get("thread_id"))
                rows = (await session.exec(select(CustomAgent).where(
                    CustomAgent.tenant_id == protected.get("tenant_id"),
                    CustomAgent.user_id.in_([protected.get("user_id"), "tenant-shared"]),
                    CustomAgent.name == protected.get("agent_name"),
                ))).scalars().all()
                agent = next((row for row in rows if row.user_id == protected.get("user_id")), rows[0] if rows else None)
                if agent is None:
                    raise ExecutionTrustError("Current named Agent unavailable")
                return agent.id
        protected["agent_id"] = _run_async(resolve())
    return protected


def _current_skill_member(context, operation, path, container_prefix):
    context = _scoped_context(context)
    if context is None:
        return None
    from app.integrations.agent_skill_members import current_member
    from app.integrations.skill_reference_transactions import begin_reference_transaction

    async def load():
        async with get_session_factory()() as session:
            tenant, actor = context.get("tenant_id"), context.get("user_id")
            await begin_reference_transaction(session, tenant)
            await verify_runtime_selection(session, context)
            from app.integrations.agent_skill_references import current_skill_resources

            record = await session.get(CustomAgent, context["agent_id"]) if context.get("agent_id") else None
            values = deepcopy(record.model_dump()) if record is not None else None
            before = await current_skill_resources(session, context.get("agent_name"), tenant, actor, selected_agent_id=context.get("agent_id"), include_snapshot=True)
            result = await current_member(session, context, operation, path, container_prefix)
            await verify_runtime_selection(session, context)
            after = await current_skill_resources(session, context.get("agent_name"), tenant, actor, selected_agent_id=context.get("agent_id"), include_snapshot=True)
            if before != after or (record.model_dump() if record is not None else None) != values:
                raise ExecutionTrustError("Current Skill selection changed during access")
            return result

    try:
        return _run_async(load())
    except Exception:
        raise ExecutionTrustError("Current selected Skill member access unavailable") from None


def _current_skill_command(context, command, provider, thread_data, env):
    context = _scoped_context(context)
    if context is None:
        return None
    from tempfile import TemporaryDirectory

    from app.integrations.agent_skill_references import current_skill_resources
    from app.integrations.skill_command_views import materialize
    from app.integrations.skill_reference_transactions import begin_reference_transaction
    from deerflow.config.paths import get_paths

    tenant, actor, agent_id = context.get("tenant_id"), context.get("user_id"), context.get("agent_id")
    name, thread_id = context.get("agent_name"), context.get("thread_id")
    paths = get_paths()
    if not thread_id:
        raise ExecutionTrustError("Owned execution thread unavailable")
    expected_paths = {key + "_path": str(getattr(paths, "sandbox_" + ("work" if key == "workspace" else key) + "_dir")(actor, thread_id, tenant_id=tenant)) for key in ("workspace", "uploads", "outputs")}
    if thread_data != expected_paths:
        raise ExecutionTrustError("Command directories differ from the current execution owner")
    for path in expected_paths.values():
        from pathlib import Path
        if Path(path).resolve() != Path(path):
            raise ExecutionTrustError("Owned command directory contains an alias")
    async def snapshot(destination=None):
        async with get_session_factory()() as session:
            await begin_reference_transaction(session, tenant)
            await verify_runtime_selection(session, context)
            record = await session.get(CustomAgent, agent_id) if agent_id else None
            values = deepcopy(record.model_dump()) if record is not None else None
            resources = await materialize(session, context, destination) if destination is not None else await current_skill_resources(session, name, tenant, actor, selected_agent_id=agent_id, include_snapshot=True)
            await verify_runtime_selection(session, context)
            if (record.model_dump() if record is not None else None) != values:
                raise ExecutionTrustError("Command configuration changed during assembly")
            return values, resources

    try:
        import os
        from pathlib import Path

        initial = _run_async(snapshot())
        if initial[1] is None:
            return None
        paths.ensure_thread_dirs(actor, thread_id, tenant_id=tenant)
        view_parent = paths.base_dir / ".scoped-command-views"
        if view_parent.resolve() != view_parent:
            raise ExecutionTrustError("Command view parent contains an alias")
        view_parent.mkdir(mode=0o700, exist_ok=True)
        if view_parent.stat().st_uid != os.getuid() or view_parent.stat().st_mode & 0o077:
            raise ExecutionTrustError("Command view parent is not private")
        with TemporaryDirectory(prefix="lease-", dir=view_parent) as view:
            Path(view).chmod(0o755)
            before = _run_async(snapshot(Path(view)))
            if before != initial:
                raise ExecutionTrustError("Command authority changed before publication")

            def validate():
                if _run_async(snapshot()) != before:
                    raise ExecutionTrustError("Current command configuration or resources changed")

            return provider.execute_scoped_command(command, view, expected_paths, env=env, validate=validate)
    except Exception:
        raise ExecutionTrustError("Current scoped command access unavailable or changed; inspect outputs and any external effects") from None


def _current_file_access(context, state, operation, path):
    from app.integrations.file_access import runtime_file_access

    return _run_async(runtime_file_access(context, state, operation, path, get_session_factory()))


def _authorize_terminal_context(context):
    from app.services.terminal.access import verify_terminal_access

    async def verify():
        await verify_terminal_access(context)
        for target in context.get("selected_assets", []):
            if not isinstance(target, dict) or not target.get("id"):
                raise ExecutionTrustError("Current terminal target unavailable")
            await verify_terminal_access(context, target["id"])
    _run_async(verify())


def register_runtime_adapters() -> None:
    """Install host providers, including after an explicit runtime reset."""
    register_agent_config_provider(_load_agent, _list_agents)
    register_agent_identity_provider(_load_agent_by_id)
    register_agent_context_provider(_load_agent_context)
    register_agent_persistence_provider(_persist_agent)
    register_terminal_agent_provider(
        get_tools=get_terminal_tools,
        set_context=set_terminal_context,
        system_prompt=TERMINAL_AGENT_SYSTEM_PROMPT,
        authorize=_authorize_terminal_context,
    )
    register_governed_action_provider(governed_ticket_tools)
    register_execution_validator(_consume_graph_capability)
    register_skill_prompt_provider(_current_skill_prompt)
    register_skill_file_provider(_current_skill_member)
    register_file_access_provider(_current_file_access)
    register_skill_command_provider(_current_skill_command)


register_runtime_adapters()
