"""Native source confirmation and original one-use capability selection facts."""

import asyncio
import base64
import json

import pytest
from sqlalchemy import select
from test_agent_skill_references import configured as reference_configuration
from test_agent_skill_references import scoped_client as shared_client
from test_skill_reference_transactions import durable_sqlite  # noqa: F401

from app.alerting import diagnosis_authorization as authorization
from app.models.agents import CustomAgent
from app.models.alerting import AlertSource
from app.platform.execution.trust import ExecutionCapabilityRepository
from deerflow.database.models import TenantMembership
from deerflow.runtime import ExecutionTrustError

scoped_client = shared_client
configured = reference_configuration


def _repository(factory):
    from app.runtime_adapters import verify_native_selection

    return ExecutionCapabilityRepository(factory, native_selection_validator=verify_native_selection)


@pytest.fixture
def delegated(configured):
    http, factory, root, resources = configured

    async def seed():
        async with factory() as session:
            agent = CustomAgent(id="shared-id", tenant_id="tenant-a", user_id="tenant-shared", name="collision-agent", system_prompt="SHARED SOUL", enabled=True)
            private = CustomAgent(id="personal-id", tenant_id="tenant-a", user_id="user-a", name="collision-agent", system_prompt="PERSONAL SOUL", enabled=True)
            session.add(agent)
            session.add(private)
            await session.commit()
        async with factory() as session:
            config = await authorization.configure(session, "tenant-a", "user-a", {"analysis_trigger": {"mode": "auto", "diagnosis_agent_id": "shared-id", authorization.KEY: {"actor_id": "forged"}}}, confirm=True)
            session.add(AlertSource(id="source-id", tenant_id="tenant-a", name="delegated-source", config_json=config, created_by="unrelated-creator"))
            await session.commit()
        return config

    return http, factory, asyncio.run(seed())


def run(factory, operation):
    async def execute():
        async with factory() as session:
            return await operation(session)

    return asyncio.run(execute())


def test_configuration_uses_confirming_admin_not_client_or_creator(delegated):
    http, factory, config = delegated
    assert config["analysis_trigger"][authorization.KEY] == {"version": 1, "actor_id": "user-a", "agent_id": "shared-id"}
    actor, agent = run(factory, lambda session: authorization.current_authorization(session, "source-id", "tenant-a", "shared-id"))
    assert actor == "user-a" and agent.id == "shared-id" and actor != agent.user_id


@pytest.mark.parametrize("change", ["member", "role", "disabled", "unshared", "source", "binding", "revision"])
def test_dispatch_rejects_withdrawn_or_changed_current_authority(delegated, change):
    http, factory, config = delegated
    expected = authorization.revision(config)

    async def alter():
        async with factory() as session:
            source = await session.get(AlertSource, "source-id")
            agent = await session.get(CustomAgent, "shared-id")
            member = (await session.exec(select(TenantMembership))).scalars().one()
            if change == "member":
                member.status = "inactive"
                session.add(member)
            elif change == "role":
                member.role = "tenant_member"
                session.add(member)
            elif change == "disabled":
                agent.enabled = False
                session.add(agent)
            elif change == "unshared":
                agent.user_id = "user-b"
                session.add(agent)
            elif change == "source":
                source.status = "disabled"
                session.add(source)
            else:
                current = dict(source.config_json)
                trigger = dict(current["analysis_trigger"])
                if change == "binding":
                    trigger["diagnosis_agent_id"] = "personal-id"
                else:
                    trigger["model"] = "changed-model"
                current["analysis_trigger"] = trigger
                source.config_json = current
                session.add(source)
            await session.commit()

    asyncio.run(alter())
    with pytest.raises(ExecutionTrustError):
        run(factory, lambda session: authorization.current_authorization(session, "source-id", "tenant-a", "shared-id", expected_actor="user-a", expected_revision=expected))


def test_native_capability_cannot_be_retargeted_and_is_single_use(delegated):
    http, factory, config = delegated
    repo = _repository(factory)
    token = asyncio.run(repo.issue("tenant-a", "user-a", "thread", "collision-agent", agent_id="shared-id", diagnosis_source_id="source-id", diagnosis_source_revision=authorization.revision(config)))
    payload = json.loads(base64.urlsafe_b64decode(token.split(".", 1)[1] + "=" * (-len(token.split(".", 1)[1]) % 4)))
    payload["agent_id"] = "personal-id"
    forged = "prismos-native-v1." + base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
    with pytest.raises(ExecutionTrustError):
        asyncio.run(repo.consume(forged, "tenant-a", "user-a", "thread", "collision-agent", include_selection=True))
    selected = asyncio.run(repo.consume(token, "tenant-a", "user-a", "thread", "collision-agent", include_selection=True))
    assert selected == {"incident_id": None, "agent_id": "shared-id"}
    with pytest.raises(ExecutionTrustError):
        asyncio.run(repo.consume(token, "tenant-a", "user-a", "thread", "collision-agent", include_selection=True))


def test_capability_rechecks_source_after_issue_and_does_not_consume_rejected_claim(delegated):
    http, factory, config = delegated
    repo = _repository(factory)
    token = asyncio.run(repo.issue("tenant-a", "user-a", "thread", "collision-agent", agent_id="shared-id", diagnosis_source_id="source-id", diagnosis_source_revision=authorization.revision(config)))

    async def revoke():
        async with factory() as session:
            source = await session.get(AlertSource, "source-id")
            source.status = "disabled"
            session.add(source)
            await session.commit()

    asyncio.run(revoke())
    with pytest.raises(ExecutionTrustError):
        asyncio.run(repo.consume(token, "tenant-a", "user-a", "thread", "collision-agent", include_selection=True))


def test_native_loader_uses_protected_shared_id_despite_personal_same_name(delegated, monkeypatch):
    from app import runtime_adapters

    http, factory, config = delegated
    monkeypatch.setattr(runtime_adapters, "get_session_factory", lambda: factory)
    selected = runtime_adapters._load_agent_by_id("collision-agent", "user-a", "tenant-a", "shared-id")
    assert selected.id == "shared-id" and selected.system_prompt == "SHARED SOUL"


def test_current_authorization_reloads_cached_records_in_the_same_session(delegated):
    http, factory, config = delegated

    async def check():
        async with factory() as session:
            await authorization.current_authorization(session, "source-id", "tenant-a", "shared-id")
            async with factory() as writer:
                row = await writer.get(AlertSource, "source-id")
                row.status = "disabled"
                writer.add(row)
                await writer.commit()
            with pytest.raises(ExecutionTrustError):
                await authorization.current_authorization(session, "source-id", "tenant-a", "shared-id")

    asyncio.run(check())


@pytest.mark.parametrize("change", [None, "source", "role", "severity", "revision"])
def test_actual_auto_dispatch_uses_real_admin_and_stops_after_async_authority_changes(delegated, monkeypatch, change):
    from types import SimpleNamespace

    import langgraph_sdk

    from app.alerting import ingest
    from app.models.alerting import Incident
    from app.platform.execution import trust
    from deerflow.database import session as session_module

    http, factory, config = delegated
    calls = []
    monkeypatch.setattr(session_module, "get_session_factory", lambda: factory)
    monkeypatch.setattr(trust, "get_session_factory", lambda: factory)
    monkeypatch.setenv("PRISMOS_TRUSTED_GRAPH_CONTEXT", "required")

    async def thread(**kwargs):
        calls.append(("thread", kwargs))
        if change is not None:
            async with factory() as writer:
                if change == "source":
                    row = await writer.get(AlertSource, "source-id")
                    row.status = "disabled"
                elif change == "role":
                    row = (await writer.exec(select(TenantMembership))).scalars().one()
                    row.role = "tenant_member"
                elif change == "severity":
                    row = await writer.get(Incident, "incident-id")
                    row.severity = "warning"
                    # Preserve the initially confirmed conditional source so
                    # the incident change, rather than a source change, rejects.
                else:
                    row = await writer.get(AlertSource, "source-id")
                    changed = dict(row.config_json)
                    selected = dict(changed["analysis_trigger"])
                    selected["model"] = "changed"
                    changed["analysis_trigger"] = selected
                    row.config_json = changed
                writer.add(row)
                await writer.commit()
        return {"thread_id": "runtime-thread"}

    async def execute(*args, **kwargs):
        calls.append(("run", kwargs))
        context = kwargs["context"]
        assert context["user_id"] == "user-a" and context["agent_id"] == "shared-id"
        chosen = await _repository(factory).consume(context["prismos_execution_capability"], "tenant-a", "user-a", "runtime-thread", "collision-agent", include_selection=True)
        assert chosen["agent_id"] == "shared-id"
        return {"messages": [{"type": "ai", "content": "Verified diagnosis"}]}

    client = SimpleNamespace(threads=SimpleNamespace(create=thread), runs=SimpleNamespace(wait=execute))
    monkeypatch.setattr(langgraph_sdk, "get_client", lambda **kwargs: client)

    async def scenario():
        async with factory() as session:
            source = await session.get(AlertSource, "source-id")
            selected = dict(source.config_json["analysis_trigger"])
            selected.update(mode="conditional", conditions={"severity": ["critical"]})
            source.config_json = {"analysis_trigger": selected}
            incident = Incident(id="incident-id", tenant_id="tenant-a", incident_key="INC-TEST", severity="critical", title="Actual dispatch")
            session.add(source)
            session.add(incident)
            await session.commit()
        await ingest._schedule_agent_diagnosis(incident, "tenant-a", "shared-id", "source-id")
        async with factory() as session:
            return await session.get(Incident, "incident-id")

    result = asyncio.run(scenario())
    assert len([name for name, _ in calls if name == "run"]) == (1 if change is None else 0)
    assert result.diagnosis_status == ("completed" if change is None else "failed")
    if change is None:
        assert result.agent_id == "shared-id" and result.diagnosis_result == "Verified diagnosis"


def test_actual_source_api_rejects_forged_actor_and_retains_authority_on_unrelated_updates(delegated):
    from app.gateway.routers import alerts

    http, factory, config = delegated
    http.app.include_router(alerts.router)
    assert http.post("/api/alert-sources", json={"name": "denied", "diagnosis_agent_id": "shared-id"}).status_code == 403
    response = http.post(
        "/api/alert-sources",
        headers={"x-tenant-role": "tenant_admin"},
        json={"name": "configured-http", "ai_analysis_enabled": True, "diagnosis_agent_id": "shared-id", "config_json": {"analysis_trigger": {authorization.KEY: {"version": 1, "actor_id": "other-user", "agent_id": "shared-id"}}}},
    )
    assert response.status_code == 201, response.text
    body = response.json()
    source_id = body["id"]
    assert body["config_json"]["analysis_trigger"][authorization.KEY]["actor_id"] == "user-a"
    updated = http.put("/api/alert-sources/" + source_id, headers={"x-tenant-role": "tenant_admin"}, json={"name": "renamed"})
    assert updated.status_code == 200
    assert updated.json()["config_json"]["analysis_trigger"][authorization.KEY] == body["config_json"]["analysis_trigger"][authorization.KEY]
    cleared = http.put("/api/alert-sources/" + source_id, headers={"x-tenant-role": "tenant_admin"}, json={"diagnosis_agent_id": ""})
    assert cleared.status_code == 200 and authorization.KEY not in cleared.json()["config_json"]["analysis_trigger"]


def test_unrelated_source_update_can_disable_a_source_with_an_unavailable_agent(delegated):
    from app.gateway.routers import alerts

    http, factory, config = delegated
    http.app.include_router(alerts.router)

    async def disable():
        async with factory() as session:
            agent = await session.get(CustomAgent, "shared-id")
            agent.enabled = False
            session.add(agent)
            await session.commit()

    asyncio.run(disable())
    response = http.put("/api/alert-sources/source-id", headers={"x-tenant-role": "tenant_admin"}, json={"status": "disabled"})
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "disabled"


def test_original_graph_uses_protected_shared_config_and_soul_not_personal_same_name(delegated, monkeypatch):
    from test_lead_agent_model_resolution import _make_app_config, _make_model

    import deerflow.tools as tools
    from app import runtime_adapters
    from deerflow.agents.lead_agent import agent as graph
    from deerflow.agents.lead_agent import prompt as template

    http, factory, config = delegated
    monkeypatch.setenv("PRISMOS_TRUSTED_GRAPH_CONTEXT", "required")
    monkeypatch.setattr(runtime_adapters, "get_session_factory", lambda: factory)
    monkeypatch.setattr(graph, "load_runtime_adapters", lambda: None)
    monkeypatch.setattr(graph, "get_execution_validator", lambda: runtime_adapters._consume_graph_capability)
    monkeypatch.setattr(graph, "get_agent_identity_provider", lambda: runtime_adapters._load_agent_by_id)
    monkeypatch.setattr(graph, "get_skill_prompt_provider", lambda: runtime_adapters._current_skill_prompt)
    monkeypatch.setattr(graph, "load_agent_config", lambda *args, **kwargs: pytest.fail("Protected ID fell back to a name cache"))
    monkeypatch.setattr(graph, "get_app_config", lambda: _make_app_config([_make_model("safe", supports_thinking=False)]))
    monkeypatch.setattr(graph, "load_enabled_tenant_model_names", lambda tenant: ["safe"])
    monkeypatch.setattr(graph, "_build_middlewares", lambda *args, **kwargs: [])
    monkeypatch.setattr(graph, "create_chat_model", lambda **kwargs: object())
    monkeypatch.setattr(graph, "create_agent", lambda **kwargs: kwargs)
    monkeypatch.setattr(tools, "get_available_tools", lambda **kwargs: [])
    monkeypatch.setattr(template, "_get_memory_context", lambda *args, **kwargs: "")
    monkeypatch.setattr(template, "get_agent_soul", lambda *args, **kwargs: pytest.fail("Protected soul fell back to name"))
    monkeypatch.setattr(template, "get_deferred_tools_prompt_section", lambda: "")
    token = asyncio.run(_repository(factory).issue("tenant-a", "user-a", "thread", "collision-agent", agent_id="shared-id"))
    built = graph.make_lead_agent({"context": {"tenant_id": "tenant-a", "user_id": "user-a", "thread_id": "thread", "agent_name": "collision-agent", "agent_id": "shared-id", "model_name": "safe", "prismos_execution_capability": token}})
    assert "SHARED SOUL" in built["system_prompt"] and "PERSONAL SOUL" not in built["system_prompt"]


def test_native_capability_cannot_be_used_for_bootstrap_or_forged_selection(delegated, monkeypatch):
    from app import runtime_adapters
    from deerflow.agents.lead_agent import agent as graph

    http, factory, config = delegated
    monkeypatch.setattr(runtime_adapters, "get_session_factory", lambda: factory)
    monkeypatch.setattr(graph, "load_runtime_adapters", lambda: None)
    monkeypatch.setattr(graph, "get_execution_validator", lambda: runtime_adapters._consume_graph_capability)
    monkeypatch.setenv("PRISMOS_TRUSTED_GRAPH_CONTEXT", "required")

    def context(token):
        return {"tenant_id": "tenant-a", "user_id": "user-a", "thread_id": "thread", "agent_name": "collision-agent", "agent_id": "shared-id", "prismos_execution_capability": token}

    token = asyncio.run(_repository(factory).issue("tenant-a", "user-a", "thread", "collision-agent", agent_id="shared-id"))
    forged = context(token)
    forged["agent_id"] = "personal-id"
    with pytest.raises(ExecutionTrustError):
        graph._validate_execution_context({"context": forged})
    token = asyncio.run(_repository(factory).issue("tenant-a", "user-a", "thread", "collision-agent", agent_id="shared-id"))
    boot = context(token)
    boot["is_bootstrap"] = True
    with pytest.raises(ExecutionTrustError, match="bootstrap"):
        graph.make_lead_agent({"context": boot})
