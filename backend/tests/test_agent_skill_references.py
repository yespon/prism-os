"""Actual native configuration and current scoped Skill read authorization."""

import asyncio

import pytest
from sqlalchemy import select
from test_skill_reference_transactions import durable_sqlite, prepare  # noqa: F401
from test_skill_reference_transactions import scoped_client as scoped_fixture

from app.integrations import agent_skill_references as refs
from app.models.agents import CustomAgent
from deerflow.database.models import Tenant, TenantMembership, TenantSkill

scoped_client = scoped_fixture


@pytest.fixture
def configured(scoped_client, monkeypatch, native_identity):
    native_identity("user-a")
    http, factory, root = prepare(scoped_client, monkeypatch)
    # This fixture owns real membership facts, including later withdrawal.
    # Synthetic request headers must never recreate or rewrite those facts.
    import resource_test_identity

    async def preserve_fixed_membership(request, factory):
        return None

    monkeypatch.setattr(resource_test_identity, "persist_fixture_identity", preserve_fixed_membership)
    monkeypatch.setattr(refs, "get_skills_root_path", lambda: root)

    async def members():
        async with factory() as session:
            session.add(Tenant(id="tenant-a", name="A", slug="a"))
            session.add(TenantMembership(tenant_id="tenant-a", user_id="user-a", role="tenant_admin"))
            await session.commit()

    asyncio.run(members())
    resources = {r["scope"]: {k: r[k] for k in ["name", "scope", "resource_id"]} for r in http.get("/api/skills/available").json()["skills"]}
    return http, factory, root, resources


def create(http, resources, mode="selected"):
    return http.post("/api/agents", json={"name": "selected-agent", "system_prompt": "Agent body", "skill_binding_mode": mode, "skill_resources": resources})


def prompt(factory, **kwargs):
    async def read():
        async with factory() as session:
            return await refs.current_skill_prompt(session, "selected-agent", "tenant-a", "user-a", **kwargs)

    return asyncio.run(read())


def test_same_name_personal_selection_injects_only_the_selected_verified_body(configured):
    http, factory, root, resources = configured
    created = create(http, [resources["personal"]])
    assert created.status_code == 201, created.text
    body = prompt(factory)
    assert "PERSONAL ONLY" in body and "PUBLIC ONLY" not in body and "SHARED ONLY" not in body
    assert resources["personal"]["resource_id"] in body and "/custom/tenant-a/user-a/collision/SKILL.md" in body
    assert http.delete("/api/skills/personal/collision").status_code == 409


def test_concrete_public_reference_does_not_block_unrelated_same_name_native_deletion(configured):
    http, factory, root, resources = configured
    assert create(http, [resources["global"]]).status_code == 201
    assert http.delete("/api/skills/personal/collision").status_code == 204
    assert "PUBLIC ONLY" in prompt(factory)


@pytest.mark.parametrize("change", ["removed", "disabled", "generation", "membership", "directory"])
def test_use_rechecks_native_instance_and_permissions_without_public_fallback(configured, change):
    http, factory, root, resources = configured
    assert create(http, [resources["personal"]]).status_code == 201

    async def mutate():
        from datetime import timedelta

        async with factory() as session:
            row = (await session.exec(select(TenantSkill).where(TenantSkill.user_id == "user-a"))).scalars().one()
            if change == "removed":
                await session.delete(row)
            elif change == "disabled":
                row.enabled = False
                session.add(row)
            elif change == "generation":
                row.created_at += timedelta(seconds=1)
                session.add(row)
            elif change == "directory":
                row.install_dir = str(root / "custom/tenant-a/user-b/collision")
                session.add(row)
            else:
                member = (await session.exec(select(TenantMembership))).scalars().one()
                member.status = "inactive"
                session.add(member)
            await session.commit()

    asyncio.run(mutate())
    with pytest.raises((refs.HTTPException, ValueError, OSError)):
        prompt(factory)


def test_shared_conversion_cannot_carry_creator_personal_selection(configured):
    http, factory, root, resources = configured
    created = create(http, [resources["personal"]]).json()
    response = http.put("/api/agents/selected-agent", headers={"x-tenant-role": "tenant_admin"}, json={"is_shared": True, "expected_agent_id": created["id"], "expected_revision": created["revision"]})
    assert response.status_code == 403
    assert not http.get("/api/agents/selected-agent").json()["is_shared"]


def test_legacy_roundtrip_keeps_selection_and_new_name_requires_explicit_reselection(configured):
    http, factory, root, resources = configured
    assert create(http, [resources["personal"]]).status_code == 201
    assert http.put("/api/agents/selected-agent", json={"skills": ["collision"], "description": "new"}).status_code == 200
    assert "PERSONAL ONLY" in prompt(factory)
    updated = http.put("/api/agents/selected-agent", json={"skills": ["collision", "unknown-name"]})
    assert updated.status_code == 200 and updated.json()["skill_binding_mode"] == "unresolved"
    with pytest.raises(refs.HTTPException):
        prompt(factory)
    assert http.put("/api/agents/selected-agent", json={"skill_binding_mode": "selected", "skill_resources": [resources["personal"]]}).status_code == 200
    assert "PERSONAL ONLY" in prompt(factory)


def test_explicit_zero_is_distinct_from_dynamic_all_and_same_name_needs_an_id(configured):
    http, factory, root, resources = configured
    assert create(http, [], "all").status_code == 201
    all_body = prompt(factory)
    assert all(value["resource_id"] in all_body for value in resources.values())
    assert "PUBLIC ONLY" not in all_body  # Multi-source catalogs keep progressive loading.
    with pytest.raises(refs.HTTPException):
        prompt(factory, skill_name="collision")
    selected = prompt(factory, skill_name="collision", resource_id=resources["personal"]["resource_id"])
    assert "PERSONAL ONLY" in selected and "PUBLIC ONLY" not in selected
    assert http.put("/api/agents/selected-agent", json={"skill_binding_mode": "selected", "skill_resources": []}).status_code == 200
    assert "ONLY" not in prompt(factory)


def test_stale_agent_configuration_is_rejected_before_replacing_selected_sources(configured):
    http, factory, root, resources = configured
    original = create(http, [resources["personal"]]).json()
    assert http.put("/api/agents/selected-agent", json={"description": "Current", "expected_revision": original["revision"]}).status_code == 200
    rejected = http.put("/api/agents/selected-agent", json={"skill_resources": [resources["global"]], "expected_agent_id": original["id"], "expected_revision": original["revision"]})
    assert rejected.status_code == 409
    assert "PERSONAL ONLY" in prompt(factory)


def test_confirmed_reference_metadata_coexists_with_original_presentation(configured):
    http, factory, root, resources = configured
    assert create(http, [resources["personal"]]).status_code == 201
    assert http.put("/api/agents/selected-agent", json={"welcome_message": "Welcome", "persona_mbti": "INTJ"}).status_code == 200

    async def stored():
        async with factory() as session:
            return (await session.exec(select(CustomAgent))).scalars().one().meta_info

    meta = asyncio.run(stored())
    assert refs.KEY in meta and "agent_presentation" in meta and "octop_source" in meta


def test_actual_prompt_uses_snapshot_without_loading_same_name_catalog(configured, monkeypatch):
    from deerflow.agents.lead_agent import prompt as template

    http, factory, root, resources = configured
    assert create(http, [resources["personal"]]).status_code == 201
    main = root / "custom/tenant-a/user-a/collision/SKILL.md"
    main.write_text(main.read_text() + "\nSNAPSHOT INSTRUCTIONS\n")
    snapshot = prompt(factory)
    monkeypatch.setattr(template, "load_skills", lambda **kwargs: pytest.fail("Concrete choice fell back to a name catalog"))
    monkeypatch.setattr(template, "_get_memory_context", lambda *args, **kwargs: "")
    monkeypatch.setattr(template, "get_agent_soul", lambda *args, **kwargs: "Agent")
    monkeypatch.setattr(template, "get_deferred_tools_prompt_section", lambda: "")
    rendered = template.apply_prompt_template(agent_name="selected-agent", skill_section_override=snapshot)
    assert "SNAPSHOT INSTRUCTIONS" in rendered and "PUBLIC ONLY" not in rendered


def test_host_provider_rechecks_disabled_instance_and_masks_failure(configured, monkeypatch):
    from app import runtime_adapters
    from deerflow.runtime import ExecutionTrustError

    http, factory, root, resources = configured
    monkeypatch.setattr(runtime_adapters, "get_session_factory", lambda: factory)
    assert create(http, [resources["personal"]]).status_code == 201
    assert "PERSONAL ONLY" in runtime_adapters._current_skill_prompt("selected-agent", "tenant-a", "user-a")
    assert http.patch("/api/skills/personal/collision", json={"enabled": False, "expected_resource_id": resources["personal"]["resource_id"]}).status_code == 200
    with pytest.raises(ExecutionTrustError):
        runtime_adapters._current_skill_prompt("selected-agent", "tenant-a", "user-a")


def test_graph_checks_actual_current_source_before_model_creation(configured, monkeypatch):
    from test_lead_agent_model_resolution import _make_app_config, _make_model

    import deerflow.tools as tools
    from app import runtime_adapters
    from deerflow.agents.lead_agent import agent as graph
    from deerflow.agents.lead_agent import prompt as template
    from deerflow.config.agents_config import AgentConfig

    http, factory, root, resources = configured
    assert create(http, [resources["personal"]]).status_code == 201
    monkeypatch.setattr(runtime_adapters, "get_session_factory", lambda: factory)
    monkeypatch.setattr(graph, "_validate_execution_context", lambda config: None)  # Trust is covered by the original capability contracts.
    monkeypatch.setattr(graph, "load_agent_config", lambda *args, **kwargs: AgentConfig(name="selected-agent", skills=["collision"]))
    monkeypatch.setattr(graph, "get_skill_prompt_provider", lambda: runtime_adapters._current_skill_prompt)
    monkeypatch.setattr(graph, "get_app_config", lambda: _make_app_config([_make_model("safe", supports_thinking=False)]))
    monkeypatch.setattr(graph, "load_enabled_tenant_model_names", lambda tenant: ["safe"])
    monkeypatch.setattr(graph, "_build_middlewares", lambda *args, **kwargs: [])
    monkeypatch.setattr(tools, "get_available_tools", lambda **kwargs: [])
    monkeypatch.setattr(template, "_get_memory_context", lambda *args, **kwargs: "")
    monkeypatch.setattr(template, "get_agent_soul", lambda *args, **kwargs: "Agent")
    monkeypatch.setattr(template, "get_deferred_tools_prompt_section", lambda: "")
    model_calls = []
    monkeypatch.setattr(graph, "create_chat_model", lambda **kwargs: model_calls.append(kwargs) or object())
    monkeypatch.setattr(graph, "create_agent", lambda **kwargs: kwargs)
    config = {"context": {"tenant_id": "tenant-a", "user_id": "user-a", "agent_name": "selected-agent", "model_name": "safe", "thinking_enabled": False}}
    result = graph.make_lead_agent(config)
    assert "PERSONAL ONLY" in result["system_prompt"] and "PUBLIC ONLY" not in result["system_prompt"]
    model_calls.clear()
    assert http.patch("/api/skills/personal/collision", json={"enabled": False, "expected_resource_id": resources["personal"]["resource_id"]}).status_code == 200
    with pytest.raises(runtime_adapters.ExecutionTrustError):
        graph.make_lead_agent(config)
    assert not model_calls


def test_corrupt_null_binding_is_not_treated_as_legacy_and_can_be_explicitly_repaired(configured):
    http, factory, root, resources = configured
    assert create(http, [resources["personal"]]).status_code == 201

    async def corrupt():
        async with factory() as session:
            agent = (await session.exec(select(CustomAgent))).scalars().one()
            meta = dict(agent.meta_info)
            meta[refs.KEY] = None
            agent.meta_info = meta
            session.add(agent)
            await session.commit()

    asyncio.run(corrupt())
    with pytest.raises(ValueError):
        prompt(factory)
    response = http.put("/api/agents/selected-agent", json={"skill_binding_mode": "selected", "skill_resources": [resources["personal"]]})
    assert response.status_code == 200
    assert "PERSONAL ONLY" in prompt(factory)
