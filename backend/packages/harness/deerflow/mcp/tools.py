"""Load MCP tools using langchain-mcp-adapters."""

import asyncio
import atexit
import concurrent.futures
import logging
from collections.abc import Callable
from typing import Any

from langchain_core.tools import BaseTool

from deerflow.config.tenant_context import get_current_tenant_id, get_current_user_id
from deerflow.database.user_config_store import load_user_config_payload
from deerflow.mcp.client import build_servers_config_from_dict
from deerflow.mcp.oauth import build_oauth_tool_interceptor_from_dict, get_initial_oauth_headers_from_dict

logger = logging.getLogger(__name__)

# Global thread pool for sync tool invocation in async environments
_SYNC_TOOL_EXECUTOR = concurrent.futures.ThreadPoolExecutor(max_workers=10, thread_name_prefix="mcp-sync-tool")

# Register shutdown hook for the global executor
atexit.register(lambda: _SYNC_TOOL_EXECUTOR.shutdown(wait=False))


def _make_sync_tool_wrapper(coro: Callable[..., Any], tool_name: str) -> Callable[..., Any]:
    """Build a synchronous wrapper for an asynchronous tool coroutine.

    Args:
        coro: The tool's asynchronous coroutine.
        tool_name: Name of the tool (for logging).

    Returns:
        A synchronous function that correctly handles nested event loops.
    """

    def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        try:
            if loop is not None and loop.is_running():
                # Use global executor to avoid nested loop issues and improve performance
                future = _SYNC_TOOL_EXECUTOR.submit(asyncio.run, coro(*args, **kwargs))
                return future.result()
            else:
                return asyncio.run(coro(*args, **kwargs))
        except Exception as e:
            logger.error(f"Error invoking MCP tool '{tool_name}' via sync wrapper: {e}", exc_info=True)
            raise

    return sync_wrapper


async def get_mcp_tools(
    user_id: str | None = None,
    tenant_id: str | None = None,
    server_names: frozenset[str] | None = None,
) -> list[BaseTool]:
    """Get all tools from enabled MCP servers.

    Args:
        user_id: Current user ID. Defaults to contextvars value if not provided.
        tenant_id: Current tenant ID. Defaults to contextvars value if not provided.
        server_names: Exact MCP server names allowed for this Agent. None keeps
            the legacy unrestricted caller behavior; an empty set loads none.

    Returns:
        List of LangChain tools from all enabled MCP servers.
    """
    if server_names is not None and not server_names:
        return []

    try:
        from langchain_mcp_adapters.client import MultiServerMCPClient
    except ImportError:
        logger.warning("langchain-mcp-adapters not installed. Install it to enable MCP tools: pip install langchain-mcp-adapters")
        return []

    if user_id is None:
        user_id = get_current_user_id()
    if tenant_id is None:
        tenant_id = get_current_tenant_id()

    # Load user config payload from database (returns (app_payload, ext_payload) tuple)
    payload_result = load_user_config_payload(user_id, tenant_id)
    if not payload_result:
        logger.info("No user config payload found in database")
        return []

    _app_payload, ext_payload = payload_result

    # Get MCP servers from the extensions payload
    mcp_servers = ext_payload.get("mcpServers") or ext_payload.get("mcp_servers", {})
    if server_names is not None:
        mcp_servers = {name: config for name, config in mcp_servers.items() if name in server_names}

    if not mcp_servers:
        logger.info("No MCP servers configured in database")
        return []

    servers_config = build_servers_config_from_dict(mcp_servers)

    if not servers_config:
        logger.info("No enabled MCP servers configured")
        return []

    try:
        # Create the multi-server MCP client
        logger.info(f"Initializing MCP client with {len(servers_config)} server(s)")

        # Inject initial OAuth headers for server connections (tool discovery/session init)
        initial_oauth_headers = await get_initial_oauth_headers_from_dict(mcp_servers)
        for server_name, auth_header in initial_oauth_headers.items():
            if server_name not in servers_config:
                continue
            if servers_config[server_name].get("transport") in ("sse", "http"):
                existing_headers = dict(servers_config[server_name].get("headers", {}))
                existing_headers["Authorization"] = auth_header
                servers_config[server_name]["headers"] = existing_headers

        tool_interceptors = []
        oauth_interceptor = build_oauth_tool_interceptor_from_dict(mcp_servers)
        if oauth_interceptor is not None:
            tool_interceptors.append(oauth_interceptor)

        client = MultiServerMCPClient(servers_config, tool_interceptors=tool_interceptors, tool_name_prefix=True)

        # Get all tools from all servers
        tools = await client.get_tools()
        logger.info(f"Successfully loaded {len(tools)} tool(s) from MCP servers")
        
        # Patch tools to support sync invocation, as deerflow client streams synchronously
        for tool in tools:
            if getattr(tool, "func", None) is None and getattr(tool, "coroutine", None) is not None:
                tool.func = _make_sync_tool_wrapper(tool.coroutine, tool.name)

        return tools

    except Exception as e:
        logger.error(f"Failed to load MCP tools: {e}", exc_info=True)
        return []
