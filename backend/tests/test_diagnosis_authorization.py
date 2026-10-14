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
        owned = await trust.ThreadBindingRepository(factory).get(args[0], "tenant-a", "user-a")
        assert owned.agent_name == "collision-agent"
        assert calls[0][1]["metadata"]["owner_user_id"] == "user-a"
        assert calls[0][1]["metadata"]["owner_tenant_id"] == "tenant-a"
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
    monkeypatch.setattr(graph, "get_agent_context_provider", lambda: runtime_adapters._load_agent_context)
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


@pytest.mark.parametrize("change", ["agent", "skill", "incident", "disabled_skill", "consume_severity"])
def test_auto_diagnosis_keeps_configuration_in_current_graph_and_refreshes_incident(delegated, configured, monkeypatch, change):
    from types import SimpleNamespace

    import langgraph_sdk
    from test_lead_agent_model_resolution import _make_app_config, _make_model

    import deerflow.tools as tools
    from app import runtime_adapters
    from app.alerting import ingest
    from app.integrations import agent_skill_references as refs
    from app.models.alerting import Incident
    from app.platform.execution import trust
    from deerflow.agents.lead_agent import agent as graph
    from deerflow.agents.lead_agent import prompt as template
    from deerflow.database import session as session_module
    from deerflow.database.models import TenantSkill

    http, factory, config = delegated
    _, _, root, resources = configured
    requests, models, graphs = [], [], []
    monkeypatch.setattr(session_module, "get_session_factory", lambda: factory)
    monkeypatch.setattr(trust, "get_session_factory", lambda: factory)
    monkeypatch.setattr(runtime_adapters, "get_session_factory", lambda: factory)
    monkeypatch.setenv("PRISMOS_TRUSTED_GRAPH_CONTEXT", "required")
    monkeypatch.setattr(graph, "load_runtime_adapters", lambda: None)
    monkeypatch.setattr(graph, "get_execution_validator", lambda: runtime_adapters._consume_graph_capability)
    monkeypatch.setattr(graph, "get_agent_context_provider", lambda: runtime_adapters._load_agent_context)
    monkeypatch.setattr(graph, "get_skill_prompt_provider", lambda: runtime_adapters._current_skill_prompt)
    monkeypatch.setattr(graph, "load_agent_config", lambda *args, **kwargs: pytest.fail("Native diagnosis used a name cache"))
    monkeypatch.setattr(graph, "get_app_config", lambda: _make_app_config([_make_model("safe", supports_thinking=False)]))
    monkeypatch.setattr(graph, "load_enabled_tenant_model_names", lambda tenant: ["safe"])
    monkeypatch.setattr(graph, "_build_middlewares", lambda *args, **kwargs: [])
    monkeypatch.setattr(graph, "create_chat_model", lambda **kwargs: models.append(kwargs) or object())
    monkeypatch.setattr(graph, "create_agent", lambda **kwargs: kwargs)
    monkeypatch.setattr(tools, "get_available_tools", lambda **kwargs: [])
    monkeypatch.setattr(template, "_get_memory_context", lambda *args, **kwargs: "")
    monkeypatch.setattr(template, "get_agent_soul", lambda *args, **kwargs: pytest.fail("Native diagnosis used a name soul"))
    monkeypatch.setattr(template, "get_deferred_tools_prompt_section", lambda: "")

    async def change_after_thread(**kwargs):
        async with factory() as writer:
            if change == "agent":
                row = await writer.get(CustomAgent, "shared-id")
                row.system_prompt = "CURRENT SHARED SOUL"
            elif change == "incident":
                row = await writer.get(Incident, "fresh-incident")
                row.title = "Current incident title"
            elif change == "disabled_skill":
                row = (await writer.exec(select(TenantSkill).where(TenantSkill.user_id == "__tenant_shared_skill__:tenant-a"))).scalars().one()
                row.enabled = False
            else:
                row = None
            if row is not None:
                writer.add(row)
                await writer.commit()
        if change == "skill":
            from pathlib import Path
            async with factory() as reader:
                row = (await reader.exec(select(TenantSkill).where(TenantSkill.user_id == "__tenant_shared_skill__:tenant-a"))).scalars().one()
                path = Path(row.install_dir) / "SKILL.md"
            path.write_text(path.read_text().replace("SHARED ONLY", "CURRENT SHARED CONTENT"))
        return {"thread_id": "fresh-thread"}

    async def execute(*args, **kwargs):
        requests.append(kwargs)
        if change == "consume_severity":
            async with factory() as writer:
                row = await writer.get(Incident, "fresh-incident")
                row.severity = "warning"
                writer.add(row)
                await writer.commit()
        built = graph.make_lead_agent({"context": kwargs["context"] | {"model_name": "safe"}})
        graphs.append(built)
        return {"messages": [{"type": "ai", "content": "Current authorized configuration"}]}

    monkeypatch.setattr(langgraph_sdk, "get_client", lambda **kwargs: SimpleNamespace(threads=SimpleNamespace(create=change_after_thread), runs=SimpleNamespace(wait=execute)))

    async def scenario():
        async with factory() as session:
            agent = await session.get(CustomAgent, "shared-id")
            agent.skills = ["collision"]
            agent.meta_info = {refs.KEY: {"version": 1, "mode": "selected", "resources": [resources["tenant"]], "legacy_names": []}}
            source = await session.get(AlertSource, "source-id")
            selected = dict(source.config_json["analysis_trigger"])
            selected.update(mode="conditional", conditions={"severity": ["critical"]})
            source.config_json = {"analysis_trigger": selected}
            incident = Incident(id="fresh-incident", tenant_id="tenant-a", incident_key="INC-FRESH", severity="critical", title="Old incident title")
            session.add(agent)
            session.add(source)
            session.add(incident)
            await session.commit()
        await ingest._schedule_agent_diagnosis(incident, "tenant-a", "shared-id", "source-id")
        async with factory() as session:
            return await session.get(Incident, "fresh-incident")

    result = asyncio.run(scenario())
    assert len(requests) == 1
    assert len(models) == (0 if change in {"disabled_skill", "consume_severity"} else 1)
    assert result.diagnosis_status == ("failed" if change in {"disabled_skill", "consume_severity"} else "completed")
    human = requests[0]["input"]["messages"][0]["content"]
    assert "SHARED SOUL" not in human and "SHARED ONLY" not in human
    assert "CURRENT SHARED CONTENT" not in human
    if change == "incident":
        assert "Current incident title" in human and "Old incident title" not in human
    if graphs:
        assert ("CURRENT SHARED SOUL" if change == "agent" else "SHARED SOUL") in graphs[0]["system_prompt"]
        assert ("CURRENT SHARED CONTENT" if change == "skill" else "SHARED ONLY") in graphs[0]["system_prompt"]
        if change == "skill":
            assert "SHARED ONLY" not in graphs[0]["system_prompt"]


@pytest.mark.parametrize("change", ["removed", "tenant", "severity", "retargeted_token"])
def test_source_incident_capability_rechecks_current_incident_and_keeps_action_authority_separate(delegated, change):
    from app.models.alerting import Incident

    http, factory, config = delegated

    async def seed():
        async with factory() as session:
            source = await session.get(AlertSource, "source-id")
            selected = dict(source.config_json["analysis_trigger"])
            selected.update(mode="conditional", conditions={"severity": ["critical"]})
            source.config_json = {"analysis_trigger": selected}
            session.add(source)
            session.add(Incident(id="cap-incident", tenant_id="tenant-a", incident_key="INC-CAP", severity="critical"))
            await session.commit()
            return authorization.revision(source.config_json)

    source_revision = asyncio.run(seed())
    repo = _repository(factory)
    token = asyncio.run(repo.issue("tenant-a", "user-a", "thread", "collision-agent", agent_id="shared-id", diagnosis_source_id="source-id", diagnosis_source_revision=source_revision, diagnosis_incident_id="cap-incident"))
    if change == "retargeted_token":
        payload = json.loads(base64.urlsafe_b64decode(token.split(".", 1)[1] + "=="))
        payload["diagnosis_incident_id"] = "another-incident"
        tampered = "prismos-native-v1." + base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode()).decode().rstrip("=")
        with pytest.raises(ExecutionTrustError):
            asyncio.run(repo.consume(tampered, "tenant-a", "user-a", "thread", "collision-agent", include_selection=True))
        consumed = asyncio.run(repo.consume(token, "tenant-a", "user-a", "thread", "collision-agent", include_selection=True))
        assert consumed == {"incident_id": None, "agent_id": "shared-id"}
        with pytest.raises(ExecutionTrustError):
            asyncio.run(repo.consume(token, "tenant-a", "user-a", "thread", "collision-agent"))
    else:
        async def alter():
            async with factory() as session:
                incident = await session.get(Incident, "cap-incident")
                if change == "removed":
                    await session.delete(incident)
                elif change == "tenant":
                    incident.tenant_id = "tenant-b"
                    session.add(incident)
                else:
                    incident.severity = "warning"
                    session.add(incident)
                await session.commit()
        asyncio.run(alter())
        with pytest.raises(ExecutionTrustError):
            asyncio.run(repo.consume(token, "tenant-a", "user-a", "thread", "collision-agent"))
        with pytest.raises(ExecutionTrustError):
            asyncio.run(repo.issue("tenant-a", "user-a", "another-thread", "collision-agent", agent_id="shared-id", diagnosis_source_id="source-id", diagnosis_source_revision=source_revision, diagnosis_incident_id="cap-incident"))


@pytest.mark.parametrize("selected_id,change", [
    ("shared-id", None), ("personal-id", None), ("shared-id", "agent"), ("shared-id", "incident"),
    ("shared-id", "disabled"), ("shared-id", "membership"), ("shared-id", "incident_tenant"), ("shared-id", "incident_removed"),
])
def test_actual_manual_diagnosis_stream_uses_current_native_identity(delegated, monkeypatch, selected_id, change):
    from types import SimpleNamespace

    import langgraph_sdk

    from app import runtime_adapters
    from app.gateway.routers import alerts
    from app.models.alerting import Incident
    from app.platform.execution import trust

    http, factory, config = delegated
    manager = alerts.DiagnosisTaskManager()
    monkeypatch.setattr(alerts, "diagnosis_task_manager", manager)
    monkeypatch.setattr(alerts, "get_session_factory", lambda: factory)
    monkeypatch.setattr(trust, "get_session_factory", lambda: factory)
    monkeypatch.setattr(runtime_adapters, "get_session_factory", lambda: factory)
    monkeypatch.setenv("PRISMOS_TRUSTED_GRAPH_CONTEXT", "off")
    http.app.include_router(alerts.router)
    requests = []

    async def thread(**kwargs):
        if change:
            async with factory() as writer:
                if change in {"agent", "disabled"}:
                    row = await writer.get(CustomAgent, selected_id)
                    if change == "agent":
                        row.system_prompt = "CURRENT MANUAL SOUL"
                    else:
                        row.enabled = False
                elif change == "membership":
                    row = (await writer.exec(select(TenantMembership))).scalars().one()
                    row.status = "inactive"
                else:
                    row = await writer.get(Incident, "manual-incident")
                    if change == "incident":
                        row.title = "Current manual incident"
                    elif change == "incident_tenant":
                        row.tenant_id = "tenant-b"
                    else:
                        await writer.delete(row)
                if change != "incident_removed":
                    writer.add(row)
                await writer.commit()
        return {"thread_id": "manual-thread"}

    async def stream(*args, **kwargs):
        requests.append(kwargs)
        context = kwargs["context"]
        if "agent_id" in context:
            selected = await _repository(factory).consume(context["prismos_execution_capability"], "tenant-a", "user-a", "manual-thread", context["agent_name"], include_selection=True)
            requests[-1]["consumed_selection"] = selected
            requests[-1]["current_soul"] = runtime_adapters._load_agent_by_id(context["agent_name"], "user-a", "tenant-a", selected["agent_id"]).system_prompt
        yield SimpleNamespace(event="messages-tuple", data=[{"type": "ai", "id": "manual-message", "content": "Verified manual output"}, {}])

    client = SimpleNamespace(threads=SimpleNamespace(create=thread, get_state=lambda *args: None), runs=SimpleNamespace(stream=stream))
    monkeypatch.setattr(langgraph_sdk, "get_client", lambda **kwargs: client)

    async def seed():
        async with factory() as session:
            session.add(Incident(id="manual-incident", tenant_id="tenant-a", incident_key="INC-MANUAL", severity="warning", title="Old manual incident"))
            await session.commit()
    asyncio.run(seed())
    response = http.post("/api/incidents/manual-incident/diagnose", params={"agent_id": selected_id})
    assert response.status_code == 200, response.text
    allowed = change in {None, "agent", "incident"}
    assert len(requests) == (1 if allowed else 0)
    if allowed:
        context = requests[0]["context"]
        assert context["agent_id"] == selected_id and context["diagnosis_incident_id"] == "manual-incident"
        assert requests[0]["consumed_selection"] == {"incident_id": "manual-incident", "agent_id": selected_id}
        human = requests[0]["input"]["messages"][0]["content"]
        assert "SHARED SOUL" not in human and "PERSONAL SOUL" not in human
        if change == "agent":
            assert requests[0]["current_soul"] == "CURRENT MANUAL SOUL"
        if change == "incident":
            assert "Current manual incident" in human and "Old manual incident" not in human
    else:
        assert "RUN_ERROR" in response.text
    if change == "incident_tenant":
        async def foreign_state():
            async with factory() as session:
                return await session.get(Incident, "manual-incident")
        foreign = asyncio.run(foreign_state())
        assert foreign.tenant_id == "tenant-b" and foreign.diagnosis_status is None


@pytest.mark.parametrize("mismatch", ["agent", "actor"])
def test_manual_reconnect_does_not_attach_to_other_native_identity_or_actor(delegated, monkeypatch, mismatch):
    from types import SimpleNamespace

    import langgraph_sdk

    from app.alerting.diagnosis_sse import StreamState
    from app.gateway.routers import alerts
    from app.models.alerting import Incident

    http, factory, config = delegated
    manager = alerts.DiagnosisTaskManager()
    manager._identities["busy-incident"] = ("tenant-a", "user-a" if mismatch == "agent" else "other-user", "personal-id" if mismatch == "agent" else "shared-id")
    manager._stream_states["busy-incident"] = StreamState()
    manager._stream_states["busy-incident"].full_text_buffer = "PRIVATE LIVE BUFFER"
    manager._thread_ids["busy-incident"] = "other-thread"
    status = SimpleNamespace(done=False)
    manager._tasks["busy-incident"] = SimpleNamespace(done=lambda: status.done)
    monkeypatch.setattr(alerts, "diagnosis_task_manager", manager)
    monkeypatch.setattr(alerts, "get_session_factory", lambda: factory)
    http.app.include_router(alerts.router)
    checkpoints = []

    async def get_state(thread):
        checkpoints.append(thread)
        status.done = True
        return {}

    monkeypatch.setattr(langgraph_sdk, "get_client", lambda **kwargs: SimpleNamespace(threads=SimpleNamespace(get_state=get_state)))

    async def seed():
        async with factory() as session:
            session.add(Incident(id="busy-incident", tenant_id="tenant-a", incident_key="INC-BUSY", diagnosis_status="running"))
            await session.commit()
    asyncio.run(seed())
    response = http.post("/api/incidents/busy-incident/diagnose", params={"agent_id": "shared-id"})
    assert response.status_code == 409 and "PRIVATE LIVE BUFFER" not in response.text
    assert checkpoints == []


@pytest.mark.parametrize("withdraw", ["membership", "tenant"])
def test_manual_diagnosis_http_rejects_current_identity_before_thread_creation(delegated, monkeypatch, withdraw):
    from types import SimpleNamespace

    import langgraph_sdk

    from app.gateway.routers import alerts
    from app.models.alerting import Incident
    from deerflow.database.models import Tenant

    http, factory, config = delegated
    monkeypatch.setattr(alerts, "diagnosis_task_manager", alerts.DiagnosisTaskManager())
    monkeypatch.setattr(alerts, "get_session_factory", lambda: factory)
    http.app.include_router(alerts.router)
    creations = []

    async def create(**kwargs):
        creations.append(kwargs)
        return {"thread_id": "should-not-exist"}

    monkeypatch.setattr(langgraph_sdk, "get_client", lambda **kwargs: SimpleNamespace(threads=SimpleNamespace(create=create)))

    async def seed():
        async with factory() as session:
            session.add(Incident(id="denied-incident", tenant_id="tenant-a", incident_key="INC-DENIED"))
            if withdraw == "membership":
                row = (await session.exec(select(TenantMembership))).scalars().one()
            else:
                row = await session.get(Tenant, "tenant-a")
            row.status = "inactive"
            session.add(row)
            await session.commit()
    asyncio.run(seed())
    response = http.post("/api/incidents/denied-incident/diagnose", params={"agent_id": "shared-id"})
    assert response.status_code == 403 and creations == []


@pytest.mark.parametrize("ownership", ["native-own", "native-foreign", "legacy-own", "legacy-foreign"])
def test_manual_retry_cancels_only_a_proven_owned_previous_thread(delegated, monkeypatch, ownership):
    from types import SimpleNamespace

    import langgraph_sdk

    from app.gateway.routers import alerts
    from app.models.alerting import Incident
    from app.platform.execution.trust import ThreadBindingRepository

    http, factory, config = delegated
    monkeypatch.setattr(alerts, "diagnosis_task_manager", alerts.DiagnosisTaskManager())
    monkeypatch.setattr(alerts, "get_session_factory", lambda: factory)
    http.app.include_router(alerts.router)
    cancellations, metadata_reads = [], []

    async def create(**kwargs):
        return {"thread_id": "new-owned-thread"}

    async def previous(thread_id):
        metadata_reads.append(thread_id)
        return {"metadata": {"owner_user_id": "user-a" if ownership.endswith("own") else "other-user", "owner_tenant_id": "tenant-a"}}

    async def running(thread_id, **kwargs):
        return [{"run_id": "previous-run"}]

    async def cancel(thread_id, run_id, **kwargs):
        cancellations.append((thread_id, run_id))

    async def stream(*args, **kwargs):
        context = kwargs["context"]
        chosen = await _repository(factory).consume(context["prismos_execution_capability"], "tenant-a", "user-a", "new-owned-thread", "collision-agent", include_selection=True)
        assert chosen["agent_id"] == "shared-id"
        yield SimpleNamespace(event="metadata", data={})

    monkeypatch.setattr(langgraph_sdk, "get_client", lambda **kwargs: SimpleNamespace(threads=SimpleNamespace(create=create, get=previous), runs=SimpleNamespace(stream=stream, list=running, cancel=cancel)))

    async def seed():
        async with factory() as session:
            session.add(Incident(id="retry-incident", tenant_id="tenant-a", incident_key="INC-RETRY", thread_id="previous-thread", diagnosis_status="failed"))
            await session.commit()
        if ownership.startswith("native"):
            await ThreadBindingRepository(factory).create("previous-thread", "tenant-a", "user-a" if ownership.endswith("own") else "other-user")
    asyncio.run(seed())
    response = http.post("/api/incidents/retry-incident/diagnose", params={"agent_id": "shared-id"})
    assert response.status_code == 200 and "RUN_FINISHED" in response.text and "RUN_ERROR" not in response.text
    assert cancellations == ([("previous-thread", "previous-run")] if ownership.endswith("own") else [])
    assert metadata_reads == (["previous-thread"] if ownership.startswith("legacy") else [])
    binding = asyncio.run(ThreadBindingRepository(factory).get("new-owned-thread", "tenant-a", "user-a"))
    assert binding.agent_name == "collision-agent"


def test_manual_diagnosis_does_not_publish_a_foreign_thread_id_returned_by_sdk(delegated, monkeypatch):
    from types import SimpleNamespace

    import langgraph_sdk

    from app.gateway.routers import alerts
    from app.models.alerting import Incident
    from app.platform.execution.trust import ThreadBindingRepository

    http, factory, config = delegated
    manager = alerts.DiagnosisTaskManager()
    monkeypatch.setattr(alerts, "diagnosis_task_manager", manager)
    monkeypatch.setattr(alerts, "get_session_factory", lambda: factory)
    http.app.include_router(alerts.router)
    reads, runs = [], []

    async def create(**kwargs):
        return {"thread_id": "foreign-thread"}

    async def get_state(thread_id):
        reads.append(thread_id)
        return {"values": {"todos": [{"name": "FOREIGN CHECKPOINT"}]}}

    async def stream(*args, **kwargs):
        runs.append(kwargs)
        yield SimpleNamespace(event="metadata", data={})

    monkeypatch.setattr(langgraph_sdk, "get_client", lambda **kwargs: SimpleNamespace(threads=SimpleNamespace(create=create, get_state=get_state), runs=SimpleNamespace(stream=stream)))

    async def seed():
        async with factory() as session:
            session.add(Incident(id="collision-incident", tenant_id="tenant-a", incident_key="INC-COLLISION"))
            await session.commit()
        await ThreadBindingRepository(factory).create("foreign-thread", "tenant-b", "other-user")
    asyncio.run(seed())
    response = http.post("/api/incidents/collision-incident/diagnose", params={"agent_id": "shared-id"})
    assert response.status_code == 200 and "RUN_ERROR" in response.text
    assert "foreign-thread" not in response.text and "FOREIGN CHECKPOINT" not in response.text
    assert reads == runs == [] and manager.get_thread_id("collision-incident") is None


def test_manual_capability_cannot_bind_a_different_action_incident(delegated):
    http, factory, config = delegated
    with pytest.raises(ExecutionTrustError, match="selections differ"):
        asyncio.run(_repository(factory).issue("tenant-a", "user-a", "thread", "collision-agent", agent_id="shared-id", diagnosis_incident_id="diagnosis-incident", action_incident_id="other-action-incident"))


def test_native_graph_does_not_mix_agent_configuration_with_later_skill_binding(delegated, configured, monkeypatch):
    from test_lead_agent_model_resolution import _make_app_config, _make_model

    import deerflow.tools as tools
    from app import runtime_adapters
    from app.integrations import agent_skill_references as refs
    from deerflow.agents.lead_agent import agent as graph
    from deerflow.agents.lead_agent import prompt as template

    http, factory, config = delegated
    _, _, root, resources = configured
    monkeypatch.setattr(runtime_adapters, "get_session_factory", lambda: factory)
    monkeypatch.setenv("PRISMOS_TRUSTED_GRAPH_CONTEXT", "required")
    monkeypatch.setattr(graph, "load_runtime_adapters", lambda: None)
    monkeypatch.setattr(graph, "get_execution_validator", lambda: runtime_adapters._consume_graph_capability)
    monkeypatch.setattr(graph, "get_agent_context_provider", lambda: runtime_adapters._load_agent_context)
    monkeypatch.setattr(graph, "get_skill_prompt_provider", lambda: runtime_adapters._current_skill_prompt)
    monkeypatch.setattr(graph, "get_app_config", lambda: _make_app_config([_make_model("old-model", supports_thinking=False), _make_model("new-model", supports_thinking=False)]))
    monkeypatch.setattr(graph, "load_enabled_tenant_model_names", lambda tenant: ["old-model", "new-model"])
    monkeypatch.setattr(graph, "_build_middlewares", lambda *args, **kwargs: [])
    monkeypatch.setattr(graph, "create_chat_model", lambda **kwargs: kwargs)
    monkeypatch.setattr(graph, "create_agent", lambda **kwargs: kwargs)
    groups = []
    monkeypatch.setattr(tools, "get_available_tools", lambda **kwargs: groups.append(kwargs["groups"]) or [])
    monkeypatch.setattr(template, "_get_memory_context", lambda *args, **kwargs: "")
    monkeypatch.setattr(template, "get_agent_soul", lambda *args, **kwargs: pytest.fail("Native soul fell back to name"))
    monkeypatch.setattr(template, "get_deferred_tools_prompt_section", lambda: "")

    async def seed():
        async with factory() as session:
            row = await session.get(CustomAgent, "shared-id")
            row.system_prompt = "OLD COHERENT SOUL"
            row.model = "old-model"
            row.tool_groups = ["old-group"]
            row.skills = ["collision"]
            row.meta_info = {refs.KEY: {"version": 1, "mode": "selected", "resources": [resources["tenant"]], "legacy_names": []}}
            session.add(row)
            await session.commit()
    asyncio.run(seed())
    original = graph._db_agent_to_config

    def edit_after_configuration_read(record):
        result = original(record)
        async def edit():
            async with factory() as writer:
                row = await writer.get(CustomAgent, "shared-id")
                row.system_prompt = "NEW COHERENT SOUL"
                row.model = "new-model"
                row.tool_groups = ["new-group"]
                row.skills = []
                row.meta_info = {refs.KEY: {"version": 1, "mode": "selected", "resources": [], "legacy_names": []}}
                writer.add(row)
                await writer.commit()
        asyncio.run(edit())
        return result
    monkeypatch.setattr(graph, "_db_agent_to_config", edit_after_configuration_read)
    token = asyncio.run(_repository(factory).issue("tenant-a", "user-a", "coherent-thread", "collision-agent", agent_id="shared-id"))
    built = graph.make_lead_agent({"context": {"tenant_id": "tenant-a", "user_id": "user-a", "thread_id": "coherent-thread", "agent_name": "collision-agent", "agent_id": "shared-id", "prismos_execution_capability": token}})
    assert built["model"]["name"] == "old-model" and groups == [["old-group"]]
    assert "OLD COHERENT SOUL" in built["system_prompt"] and "SHARED ONLY" in built["system_prompt"]
    assert "NEW COHERENT SOUL" not in built["system_prompt"]


def test_native_context_coordinates_real_agent_edit_without_mixing_binding(configured, monkeypatch):
    import threading
    from concurrent.futures import ThreadPoolExecutor

    from app import runtime_adapters
    from app.gateway.routers import agents
    from app.integrations import agent_skill_references as refs

    http, factory, root, resources = configured
    created = http.post("/api/agents", json={"name": "coordinated-context", "system_prompt": "OLD COORDINATED SOUL", "skill_binding_mode": "selected", "skill_resources": [resources["personal"]]})
    assert created.status_code == 201, created.text
    identity = created.json()["id"]
    monkeypatch.setattr(runtime_adapters, "get_session_factory", lambda: factory)
    reading, release, writing = threading.Event(), threading.Event(), threading.Event()
    original_prompt = refs.current_skill_prompt
    original_transaction = agents.begin_reference_transaction

    async def pause(*args, **kwargs):
        reading.set()
        assert await asyncio.to_thread(release.wait, 5), "Context read release was not delivered"
        return await original_prompt(*args, **kwargs)

    async def writer_lock(*args, **kwargs):
        writing.set()
        await original_transaction(*args, **kwargs)

    monkeypatch.setattr(refs, "current_skill_prompt", pause)
    monkeypatch.setattr(agents, "begin_reference_transaction", writer_lock)
    with ThreadPoolExecutor(max_workers=2) as pool:
        reader = pool.submit(runtime_adapters._load_agent_context, "coordinated-context", "user-a", "tenant-a", identity)
        writer = None
        try:
            assert reading.wait(5)
            update = {"system_prompt": "NEW COORDINATED SOUL", "skill_binding_mode": "selected", "skill_resources": [],
                      "expected_agent_id": identity, "expected_revision": created.json()["revision"]}
            writer = pool.submit(http.put, "/api/agents/coordinated-context", json=update)
            assert writing.wait(5)
            assert not writer.done()
        finally:
            release.set()
        first = reader.result(10)
        result = writer.result(10)
    assert first.record.system_prompt == "OLD COORDINATED SOUL" and "PERSONAL ONLY" in first.skill_section
    assert result.status_code == 200, result.text
    next_context = runtime_adapters._load_agent_context("coordinated-context", "user-a", "tenant-a", identity)
    assert next_context.record.system_prompt == "NEW COORDINATED SOUL" and "PERSONAL ONLY" not in next_context.skill_section


@pytest.mark.parametrize("withdraw", ["source", "member", "incident", "severity"])
def test_native_context_rechecks_protected_authority_after_capability_consumption(delegated, monkeypatch, withdraw):
    from app import runtime_adapters
    from app.models.alerting import Incident

    http, factory, config = delegated
    monkeypatch.setattr(runtime_adapters, "get_session_factory", lambda: factory)

    async def issue():
        async with factory() as session:
            source = await session.get(AlertSource, "source-id")
            selected = dict(source.config_json["analysis_trigger"])
            selected.update(mode="conditional", conditions={"severity": ["critical"]})
            source.config_json = {"analysis_trigger": selected}
            session.add(source)
            session.add(Incident(id="context-incident", tenant_id="tenant-a", incident_key="INC-CONTEXT", severity="critical"))
            await session.commit()
            digest = authorization.revision(source.config_json)
        return await _repository(factory).issue("tenant-a", "user-a", "context-thread", "collision-agent", agent_id="shared-id", diagnosis_source_id="source-id", diagnosis_source_revision=digest, diagnosis_incident_id="context-incident")

    token = asyncio.run(issue())
    verified = asyncio.run(runtime_adapters._consume_graph_capability(token, "tenant-a", "user-a", "context-thread", "collision-agent"))
    assert verified["diagnosis_source_id"] == "source-id" and verified["diagnosis_incident_id"] == "context-incident"

    async def change():
        async with factory() as session:
            if withdraw == "source":
                row = await session.get(AlertSource, "source-id")
                row.status = "disabled"
            elif withdraw == "member":
                row = (await session.exec(select(TenantMembership))).scalars().one()
                row.status = "inactive"
            else:
                row = await session.get(Incident, "context-incident")
                if withdraw == "incident":
                    await session.delete(row)
                else:
                    row.severity = "warning"
            if withdraw != "incident":
                session.add(row)
            await session.commit()
    asyncio.run(change())
    with pytest.raises(ExecutionTrustError):
        runtime_adapters._load_agent_context("collision-agent", "user-a", "tenant-a", "shared-id", **{key: verified[key] for key in ["diagnosis_source_id", "diagnosis_source_revision", "diagnosis_incident_id"]})
