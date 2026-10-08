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
    monkeypatch.setattr(lead_agent, "_validate_execution_context", lambda _config: scope)
    monkeypatch.setattr(lead_agent, "load_runtime_adapters", lambda: None)
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
    assert built["tools"] == [action_tool, governed_read]
    assert "create_governed_incident_ticket" in built["system_prompt"]
    assert seen == [scope]
    monkeypatch.setattr(lead_agent, "_validate_execution_context", lambda _config: None)
    unscoped = lead_agent.make_lead_agent({"context": {
        "thread_id": "thread-2", "tenant_id": "tenant-a", "user_id": "user-1", "agent_name": "diagnosis",
    }})
    assert unscoped["tools"] == [ungoverned_read]
    assert "create_governed_incident_ticket" not in unscoped["system_prompt"]
    assert seen == [scope]
