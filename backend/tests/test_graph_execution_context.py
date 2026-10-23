import pytest

from app.platform.execution import trust
from deerflow.agents.lead_agent import agent as lead_agent


def test_graph_rejects_naked_and_conflicting_identity_before_loading_tools(monkeypatch) -> None:
    monkeypatch.setenv("PRISMOS_TRUSTED_GRAPH_CONTEXT", "required")
    calls = []
    monkeypatch.setattr(lead_agent, "load_runtime_adapters", lambda: calls.append("tools"))
    with pytest.raises(trust.ExecutionTrustError, match="required"):
        lead_agent.make_lead_agent({"context": {
            "thread_id": "thread-1", "tenant_id": "tenant-a", "user_id": "user-1",
        }})
    assert calls == []
    with pytest.raises(trust.ExecutionTrustError, match="required"):
        lead_agent.make_lead_agent({"context": {"is_bootstrap": True}})
    with pytest.raises(trust.ExecutionTrustError, match="conflicting"):
        lead_agent.make_lead_agent({
            "context": {"thread_id": "thread-1", "tenant_id": "tenant-a", "user_id": "user-1"},
            "configurable": {"tenant_id": "tenant-b"},
        })
    assert calls == []


def test_graph_consumes_matching_trusted_context(monkeypatch) -> None:
    monkeypatch.setenv("PRISMOS_TRUSTED_GRAPH_CONTEXT", "required")
    calls = []

    class FakeCapabilities:
        async def consume(self, token, tenant_id, user_id, thread_id, agent_name):
            calls.append((token, tenant_id, user_id, thread_id, agent_name))

    monkeypatch.setattr(lead_agent, "load_runtime_adapters", lambda: None)
    monkeypatch.setattr(lead_agent, "get_execution_validator", lambda: FakeCapabilities().consume)
    lead_agent._validate_execution_context({"context": {
        "thread_id": "thread-1", "tenant_id": "tenant-a", "user_id": "user-1",
        "agent_name": "diagnosis", "prismos_execution_capability": "server-token",
    }})
    assert calls == [("server-token", "tenant-a", "user-1", "thread-1", "diagnosis")]
    lead_agent._validate_execution_context({})  # Assistant schema discovery has no Run context.


def test_verified_diagnosis_scope_adds_host_action_tool_to_agent(monkeypatch) -> None:
    from types import SimpleNamespace

    from deerflow import tools as tool_module

    scope = {"tenant_id": "tenant-a", "user_id": "user-1", "thread_id": "thread-1",
             "agent_name": "diagnosis", "incident_id": "incident-1"}
    action_tool = SimpleNamespace(name="create_governed_incident_ticket")
    governed_read = SimpleNamespace(name="read_file")
    ungoverned_read = SimpleNamespace(name="read_file")
    seen = []
    read_middleware = object()
    middleware_scopes = []
    monkeypatch.setattr(lead_agent, "get_execution_middleware_provider", lambda: lambda found: middleware_scopes.append(found) or [read_middleware])
    monkeypatch.setattr(lead_agent, "_validate_execution_context", lambda _config: scope)
    monkeypatch.setattr(lead_agent, "load_runtime_adapters", lambda: None)
    # This standalone tool-selection contract has no host Agent/Skill database.
    monkeypatch.setattr(lead_agent, "get_skill_prompt_provider", lambda: None)
    monkeypatch.setattr(lead_agent, "get_governed_action_provider", lambda: lambda found: seen.append(found) or [action_tool, governed_read])
    monkeypatch.setattr(lead_agent, "load_enabled_tenant_model_names", lambda _tenant: ["model-1"])
    monkeypatch.setattr(lead_agent, "load_agent_config", lambda *_args, **_kwargs:
                        SimpleNamespace(model="model-1", skills=[], tool_groups=[]))
    monkeypatch.setattr(lead_agent, "_resolve_model_name", lambda *_args, **_kwargs: "model-1")
    monkeypatch.setattr(lead_agent, "get_app_config", lambda: SimpleNamespace(
        get_model_config=lambda _name: SimpleNamespace(supports_thinking=True)))
    monkeypatch.setattr(lead_agent, "create_chat_model", lambda **_kwargs: object())
    monkeypatch.setattr(lead_agent, "_build_middlewares", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(lead_agent, "apply_prompt_template", lambda **_kwargs: "prompt")
    monkeypatch.setattr(lead_agent, "create_agent", lambda **kwargs: kwargs)
    monkeypatch.setattr(tool_module, "get_available_tools", lambda **_kwargs: [ungoverned_read])
    built = lead_agent.make_lead_agent({"context": {
        "thread_id": "thread-1", "tenant_id": "tenant-a", "user_id": "user-1", "agent_name": "diagnosis",
    }})
    assert built["middleware"] == [read_middleware]
    assert middleware_scopes == [scope]
    assert built["tools"] == [action_tool, governed_read]
    assert "create_governed_incident_ticket" in built["system_prompt"]
    assert seen == [scope]
    monkeypatch.setattr(lead_agent, "_validate_execution_context", lambda _config: None)
    unscoped = lead_agent.make_lead_agent({"context": {
        "thread_id": "thread-2", "tenant_id": "tenant-a", "user_id": "user-1", "agent_name": "diagnosis",
    }})
    assert unscoped["middleware"] == []
    assert middleware_scopes == [scope]
    assert unscoped["tools"] == [ungoverned_read]
    assert "create_governed_incident_ticket" not in unscoped["system_prompt"]
    assert seen == [scope]


@pytest.mark.parametrize("access", ["threads.create_run", "threads.update", "assistants.read"])
def test_history_exception_cannot_authorize_run_or_state_write(monkeypatch, access):
    from langgraph_sdk.runtime import _ExecutionRuntime, _ReadRuntime
    monkeypatch.setenv("PRISMOS_TRUSTED_GRAPH_CONTEXT", "required")
    runtime = (_ExecutionRuntime if access == "threads.create_run" else _ReadRuntime)(access_context=access, store=None)
    with pytest.raises(trust.ExecutionTrustError, match="identity required"):
        lead_agent.make_lead_agent({"configurable": {"thread_id": "thread-1", "__is_for_execution__": False}}, runtime)
    with pytest.raises(trust.ExecutionTrustError, match="identity required"):
        lead_agent.make_lead_agent({"configurable": {"thread_id": "thread-1", "__is_for_execution__": False}, "runtime": {"access_context": "threads.read"}})


def test_sdk_history_materialization_does_not_consume_capability_or_reload_paused_agent(monkeypatch):
    from langgraph_sdk.runtime import _ReadRuntime
    sentinel = object()
    seen = []
    monkeypatch.setenv("PRISMOS_TRUSTED_GRAPH_CONTEXT", "required")
    monkeypatch.setattr(lead_agent, "_make_history_agent", lambda cfg: seen.append(cfg) or sentinel)
    monkeypatch.setattr(lead_agent, "_validate_execution_context", lambda _: pytest.fail("History consumed an execution capability"))
    config = {"configurable": {"thread_id": "thread-1"}}
    assert lead_agent.make_lead_agent(config, _ReadRuntime(access_context="threads.read", store=None)) is sentinel
    assert seen == [config]


def test_sdk_read_factory_preserves_pending_task_topology_without_model_request(monkeypatch):
    from types import SimpleNamespace

    from langchain.tools import tool
    from langchain_core.messages import AIMessage
    from langchain_openai import ChatOpenAI
    from langgraph.checkpoint.memory import InMemorySaver
    from langgraph_api._factory_utils import classify_factory, invoke_factory
    from langgraph_sdk.runtime import _ReadRuntime

    from deerflow import tools as tool_module

    @tool
    def inspect_owned_document() -> str:
        """Inspect the owned document."""
        pytest.fail('State inspection executed a tool')
    monkeypatch.setattr(lead_agent, '_validate_execution_context', lambda _: None)
    monkeypatch.setattr(lead_agent, 'load_runtime_adapters', lambda: None)
    monkeypatch.setattr(lead_agent, 'get_skill_prompt_provider', lambda: None)
    monkeypatch.setattr(lead_agent, 'get_governed_action_provider', lambda: None)
    monkeypatch.setattr(lead_agent, 'load_agent_config', lambda *_, **__: None)
    monkeypatch.setattr(lead_agent, '_resolve_model_name', lambda *_, **__: 'unit-model')
    monkeypatch.setattr(lead_agent, 'get_app_config', lambda: SimpleNamespace(get_model_config=lambda _: SimpleNamespace(supports_thinking=False, supports_vision=False)))
    monkeypatch.setattr(lead_agent, '_create_summarization_middleware', lambda _: None)
    monkeypatch.setattr(lead_agent, 'get_title_config', lambda: SimpleNamespace(enabled=False))
    monkeypatch.setattr(lead_agent, 'create_chat_model', lambda **_: ChatOpenAI(model='unit-model', api_key='local-unit-no-network'))
    monkeypatch.setattr(lead_agent, 'apply_prompt_template', lambda **_: 'unit topology')
    monkeypatch.setattr(tool_module, 'get_available_tools', lambda **_: [inspect_owned_document])
    executed = lead_agent.make_lead_agent({'configurable': {}})
    classify_factory(lead_agent.make_lead_agent, 'unit-read-factory')
    read = invoke_factory(lead_agent.make_lead_agent, 'unit-read-factory', {'configurable': {}}, _ReadRuntime(access_context='threads.read', store=None))
    assert set(executed.nodes) == set(read.nodes)
    assert set(executed.channels) == set(read.channels)
    saver = InMemorySaver()
    executed.checkpointer = read.checkpointer = saver
    config = {'configurable': {'thread_id': 'unit-pending-history'}}
    executed.update_state(config, {'messages': [AIMessage(content='', tool_calls=[{'name': 'inspect_owned_document', 'args': {}, 'id': 'call-pending'}])]}, as_node='model')
    expected = executed.get_state(config)
    actual = read.get_state(config)
    assert expected.next and actual.next == expected.next
    assert actual.values['messages'] == expected.values['messages']
