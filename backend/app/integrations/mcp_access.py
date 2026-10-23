"""Recheck native identity, current Agent selection and the exact MCP connection."""

import asyncio

from app.models.agents import CustomAgent
from deerflow.database.session import get_session_factory
from deerflow.database.user_config_store import load_user_config_payload
from deerflow.mcp.authorization import configuration_fingerprint
from deerflow.runtime import ExecutionTrustError


async def authorize_mcp_tool(context, binding):
    from app.runtime_adapters import _scoped_context, verify_runtime_selection

    if any(not context.get(key) or context.get(key) != binding.get(key) for key in ("tenant_id", "user_id")):
        raise ExecutionTrustError("Current MCP actor unavailable")
    # Preserve the existing ordinary/legacy named execution entry. Resolve its
    # identity using the original host seam, then pin it through this call.
    protected = await asyncio.to_thread(_scoped_context, context)
    if protected is None:
        raise ExecutionTrustError("Current MCP execution unavailable")
    context.update(protected)
    # Protected incident scope is host-private, including in child/sync workers.
    # Do not let an incomplete SDK context drop source/revocation constraints.
    from app.alerting.governed_native_reads import _scope

    frame = _scope.get()
    if frame:
        scope = frame[0]
        if any(context.get(key) != scope.get(key) for key in ("tenant_id", "user_id", "thread_id")):
            raise ExecutionTrustError("Current protected MCP scope unavailable")
        if scope.get("agent_id") is not None and context.get("agent_id") != scope["agent_id"]:
            raise ExecutionTrustError("Current protected MCP Agent unavailable")
        for key in ("diagnosis_source_id", "diagnosis_source_revision", "diagnosis_incident_id"):
            context[key] = scope.get(key)
        if scope.get("incident_id"):
            context["diagnosis_incident_id"] = scope["incident_id"]
    server = binding.get("server_name")
    if not isinstance(server, str) or not server:
        raise ExecutionTrustError("Current MCP server unavailable")
    async with get_session_factory()() as session:
        await verify_runtime_selection(session, context)
        if context.get("agent_id"):
            agent = await session.get(CustomAgent, context["agent_id"], populate_existing=True)
            if agent is None or (agent.tool_groups is not None and server not in agent.tool_groups):
                raise ExecutionTrustError("Current Agent MCP selection unavailable")
    # Do not keep the authorization transaction open during discovery/RPC.
    payload = await asyncio.to_thread(load_user_config_payload, context["user_id"], context["tenant_id"])
    if not payload:
        raise ExecutionTrustError("Current MCP configuration unavailable")
    configurations = payload[1].get("mcpServers") or payload[1].get("mcp_servers") or {}
    current = configurations.get(server)
    if not isinstance(current, dict) or not current.get("enabled", True):
        raise ExecutionTrustError("Current MCP server unavailable")
    if configuration_fingerprint(server, current) != binding.get("configuration_sha256"):
        raise ExecutionTrustError("MCP connection changed; reload tools before executing")
