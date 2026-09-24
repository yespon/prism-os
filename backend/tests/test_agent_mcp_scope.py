"""M1 Agent MCP server selection must be enforced before tool discovery."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from deerflow.config.agents_config import _db_agent_to_config
from deerflow.config.tool_search_config import ToolSearchConfig
from deerflow.mcp import cache
from deerflow.mcp.tools import get_mcp_tools
from deerflow.tools import tools as registry
from deerflow.tools.builtins.tool_search import get_deferred_registry


def _servers():
    return {
        "ops": {"enabled": True, "transport": "stdio", "command": "true"},
        "ops_prod": {"enabled": True, "transport": "stdio", "command": "true"},
    }


def test_mcp_loader_selects_exact_server_before_discovery() -> None:
    client = MagicMock()
    client.get_tools = AsyncMock(return_value=[SimpleNamespace(name="ops_ping", func=lambda: None)])
    with (
        patch("langchain_mcp_adapters.client.MultiServerMCPClient", return_value=client) as constructor,
        patch("deerflow.mcp.tools.load_user_config_payload", return_value=({}, {"mcpServers": _servers()})),
        patch("deerflow.mcp.tools.get_initial_oauth_headers_from_dict", new_callable=AsyncMock, return_value={}) as oauth_headers,
        patch("deerflow.mcp.tools.build_oauth_tool_interceptor_from_dict", return_value=None) as oauth_interceptor,
    ):
        tools = asyncio.run(get_mcp_tools(user_id="user-a", tenant_id="tenant-a", server_names=frozenset({"ops"})))
    assert [tool.name for tool in tools] == ["ops_ping"]
    assert set(constructor.call_args.args[0]) == {"ops"}
    assert set(oauth_headers.call_args.args[0]) == {"ops"}
    assert set(oauth_interceptor.call_args.args[0]) == {"ops"}
    client.get_tools.assert_awaited_once()


def test_empty_mcp_selection_never_loads_servers() -> None:
    with patch("deerflow.mcp.tools.load_user_config_payload") as load:
        assert asyncio.run(get_mcp_tools(server_names=frozenset())) == []
    load.assert_not_called()


def test_custom_agent_empty_groups_remain_explicit_empty() -> None:
    agent = SimpleNamespace(
        id="agent-1", name="diagnosis", description="", model=None,
        tool_groups=[], system_prompt="", skills=[], enabled=True, tags=[],
    )
    assert _db_agent_to_config(agent).tool_groups == []


def test_mcp_cache_isolated_by_server_selection(monkeypatch) -> None:
    cache._mcp_tools_cache.clear()
    cache._cache_initialized.clear()
    monkeypatch.setattr(cache, "_check_cross_process_invalidation", lambda: None)
    monkeypatch.setattr(cache, "get_current_tenant_id", lambda: "tenant-a")
    monkeypatch.setattr(cache, "get_current_user_id", lambda: "user-a")
    calls = []

    async def load(*, user_id, tenant_id, server_names):
        calls.append((user_id, tenant_id, server_names))
        return [SimpleNamespace(name=name) for name in sorted(server_names)]

    monkeypatch.setattr("deerflow.mcp.tools.get_mcp_tools", load)
    ops = frozenset({"ops"})
    prod = frozenset({"ops_prod"})
    asyncio.run(cache.initialize_mcp_tools("tenant-a", "user-a", ops))
    asyncio.run(cache.initialize_mcp_tools("tenant-a", "user-a", prod))
    assert [tool.name for tool in cache.get_cached_mcp_tools(server_names=ops)] == ["ops"]
    assert [tool.name for tool in cache.get_cached_mcp_tools(server_names=prod)] == ["ops_prod"]
    assert len(calls) == 2
    monkeypatch.setattr(cache, "_bump_cache_version", lambda: None)
    cache.reset_mcp_tools_cache()
    assert cache._mcp_tools_cache == {}
    asyncio.run(cache.initialize_mcp_tools("tenant-a", "user-a", ops))
    assert len(calls) == 3
    cache._mcp_tools_cache.clear()
    cache._cache_initialized.clear()


def test_registry_limits_mcp_and_deferred_search_to_selected_server(monkeypatch) -> None:
    config = SimpleNamespace(models=[], tool_search=ToolSearchConfig(enabled=True))
    monkeypatch.setattr(registry, "get_app_config", lambda: config)
    monkeypatch.setattr(registry, "DEFAULT_COMMUNITY_TOOLS", [])
    monkeypatch.setattr(registry, "BUILTIN_TOOLS", [])
    selections = []

    def cached(*, server_names):
        selections.append(server_names)
        return [SimpleNamespace(name=f"{name}_ping", description="ping") for name in sorted(server_names or {"ops", "ops_prod"})]

    monkeypatch.setattr("deerflow.mcp.cache.get_cached_mcp_tools", cached)
    selected = registry.get_available_tools(groups=["ops"])
    assert [tool.name for tool in selected if tool.name != "tool_search"] == ["ops_ping"]
    assert [entry.name for entry in get_deferred_registry().entries] == ["ops_ping"]
    assert selections == [frozenset({"ops"})]

    assert registry.get_available_tools(groups=[]) == []
    assert get_deferred_registry() is None
    assert selections == [frozenset({"ops"})]

    unrestricted = registry.get_available_tools(groups=None)
    assert {tool.name for tool in unrestricted if tool.name != "tool_search"} == {
        "ops_ping", "ops_prod_ping"
    }
    assert selections[-1] is None
    assert {entry.name for entry in get_deferred_registry().entries} == {
        "ops_ping", "ops_prod_ping"
    }


def test_named_agent_passes_empty_mcp_selection_to_registry(monkeypatch) -> None:
    from deerflow.agents.lead_agent import agent as lead_agent
    from deerflow.config.agents_config import AgentConfig

    model = SimpleNamespace(name="model-1", supports_thinking=False, supports_vision=False)
    config = SimpleNamespace(models=[model], get_model_config=lambda name: model)
    calls = []
    monkeypatch.setattr(lead_agent, "load_runtime_adapters", lambda: None)
    monkeypatch.setattr(lead_agent, "get_app_config", lambda: config)
    monkeypatch.setattr(
        lead_agent, "load_agent_config",
        lambda *args, **kwargs: AgentConfig(name="diagnosis", tool_groups=[]),
    )
    monkeypatch.setattr(lead_agent, "_build_middlewares", lambda *args, **kwargs: [])
    monkeypatch.setattr(lead_agent, "create_chat_model", lambda **kwargs: object())
    monkeypatch.setattr(lead_agent, "apply_prompt_template", lambda **kwargs: "prompt")
    monkeypatch.setattr(lead_agent, "create_agent", lambda **kwargs: kwargs)
    monkeypatch.setattr(
        "deerflow.tools.get_available_tools",
        lambda **kwargs: calls.append(kwargs) or [],
    )

    lead_agent.make_lead_agent({"context": {"agent_name": "diagnosis", "model_name": "model-1"}})
    assert calls[0]["groups"] == []


def test_empty_custom_agent_mcp_selection_keeps_builtin_tools(monkeypatch) -> None:
    builtin = SimpleNamespace(name="read_file")
    config = SimpleNamespace(models=[], tool_search=ToolSearchConfig(enabled=False))
    monkeypatch.setattr(registry, "get_app_config", lambda: config)
    monkeypatch.setattr(registry, "DEFAULT_COMMUNITY_TOOLS", [])
    monkeypatch.setattr(registry, "BUILTIN_TOOLS", [builtin])
    monkeypatch.setattr(
        "deerflow.mcp.cache.get_cached_mcp_tools",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("MCP lookup should be skipped")),
    )
    assert registry.get_available_tools(groups=[]) == [builtin]


def test_unknown_selected_server_does_not_discover_any_tools() -> None:
    with (
        patch("deerflow.mcp.tools.load_user_config_payload", return_value=({}, {"mcpServers": _servers()})),
        patch("langchain_mcp_adapters.client.MultiServerMCPClient") as constructor,
    ):
        tools = asyncio.run(get_mcp_tools(server_names=frozenset({"missing"})))
    assert tools == []
    constructor.assert_not_called()
