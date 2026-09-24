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

    monkeypatch.setattr(trust, "ExecutionCapabilityRepository", FakeCapabilities)
    lead_agent._validate_execution_context({"context": {
        "thread_id": "thread-1", "tenant_id": "tenant-a", "user_id": "user-1",
        "agent_name": "diagnosis", "prismos_execution_capability": "server-token",
    }})
    assert calls == [("server-token", "tenant-a", "user-1", "thread-1", "diagnosis")]
    lead_agent._validate_execution_context({})  # Assistant schema discovery has no Run context.
