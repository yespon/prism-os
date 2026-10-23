"""Optional host authorization around each cached MCP invocation and delivery."""

import hashlib
import json
from copy import deepcopy
from functools import wraps

from deerflow.mcp.client import build_server_params_from_dict


def configuration_fingerprint(name, configuration):
    connection = build_server_params_from_dict(name, configuration)
    oauth = configuration.get("oauth")
    if oauth and oauth.get("enabled", True):
        connection["oauth"] = oauth
    return hashlib.sha256(json.dumps(connection, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def guard_mcp_tool(tool, binding):
    original = getattr(tool, "coroutine", None)
    if original is None:
        return tool
    binding = deepcopy(binding)

    @wraps(original)
    async def guarded(*args, **kwargs):
        from langgraph.runtime import get_runtime

        from deerflow.runtime import get_mcp_tool_authorizer

        authorize = get_mcp_tool_authorizer()
        context = None
        if authorize:
            try:
                context = get_runtime().context
            except RuntimeError as error:
                raise PermissionError("Current MCP execution context unavailable") from error
            if not isinstance(context, dict):
                raise PermissionError("Current MCP execution context unavailable")
            context = dict(context)
            await authorize(context, binding)
        result = await original(*args, **kwargs)
        if authorize:
            try:
                await authorize(context, binding)
            except Exception as error:
                raise PermissionError("MCP execution completed but result authorization changed; do not automatically repeat the tool") from error
        return result

    tool.coroutine = guarded
    return tool
