"""Pinned-source behavior and host authorization/persistence contract tests."""

from __future__ import annotations

import asyncio
import hashlib
import os

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from prismos_octop.catalog import get_template, list_personas, list_templates, render_persona
from prismos_octop.upstream.chunk import chunk_text
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from app.gateway.routers import agent_catalog, agents
from app.models.agents import CustomAgent
from deerflow.database.session import get_session


@pytest.fixture
def catalog_client():
    engine = create_async_engine("sqlite+aiosqlite://", connect_args={"check_same_thread": False})

    async def initialize():
        async with engine.begin() as connection:
            await connection.run_sync(SQLModel.metadata.create_all)

    asyncio.run(initialize())
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    app = FastAPI()

    @app.middleware("http")
    async def identity(request: Request, call_next):
        request.state.user_id = request.headers.get("x-user-id", "user-a") or None
        request.state.tenant_id = request.headers.get("x-tenant-id", "tenant-a") or None
        request.state.tenant_role = request.headers.get("x-tenant-role", "tenant_member")
        return await call_next(request)

    async def session():
        async with factory() as value:
            yield value

    app.dependency_overrides[get_session] = session
    app.include_router(agent_catalog.router)
    app.include_router(agents.router)
    with TestClient(app) as client:
        yield client, factory
    asyncio.run(engine.dispose())


def test_complete_pinned_catalog_and_personas():
    for locale in ("zh", "en"):
        summaries = list_templates(locale)
        assert len(summaries) > 100
        assert len({entry["id"] for entry in summaries}) == len(summaries)
        assert {entry["kind"] for entry in summaries} == {"expert", "subagent"}
        for entry in summaries:
            full = get_template(entry["id"], locale)
            assert full["system_prompt"].strip()
            assert full["revision"] == os.getenv("PRISMOS_OCTOP_EXPECTED_REVISION", "eb28011249c02cafd389b2d424294c6c1b9cf422")
    personas = list_personas()
    assert len(personas) == 16
    assert {p["code"] for p in personas} == {"INTJ", "INTP", "ENTJ", "ENTP", "INFJ", "INFP", "ENFJ", "ENFP", "ISTJ", "ISFJ", "ESTJ", "ESFJ", "ISTP", "ISFP", "ESTP", "ESFP"}
    assert "INTJ" in render_persona("INTJ", "zh")


def test_template_paths_are_identifiers_not_files(catalog_client):
    client, _ = catalog_client
    assert client.get("/api/agent-catalog/templates/expert:missing").status_code == 404
    assert client.post("/api/agents", json={"name": "invalid-template", "template_id": "../SOUL.md"}).status_code == 404
    assert client.get("/api/agent-catalog/templates?locale=invalid").status_code == 422


def test_catalog_requires_identity_and_tenant(catalog_client):
    client, _ = catalog_client
    for path in ("templates", "personas", "status"):
        assert client.get("/api/agent-catalog/" + path, headers={"x-user-id": ""}).status_code == 401
        assert client.get("/api/agent-catalog/" + path, headers={"x-tenant-id": ""}).status_code == 400


def test_template_creates_real_tenant_scoped_agent_and_records_source(catalog_client):
    client, factory = catalog_client
    response = client.post("/api/agents", json={"name": "pinned-expert", "template_id": "expert:general-assistant", "persona_mbti": "intj"})
    assert response.status_code == 201
    assert "INTJ" in response.json()["system_prompt"]
    assert response.json()["skills"] == [] and response.json()["tool_groups"] == []
    assert client.get("/api/agents/pinned-expert", headers={"x-user-id": "user-b"}).status_code == 404
    assert client.get("/api/agents/pinned-expert", headers={"x-tenant-id": "tenant-b"}).status_code == 404

    async def load():
        async with factory() as session:
            result = await session.exec(select(CustomAgent).where(CustomAgent.name == "pinned-expert"))
            return result.scalars().one()

    saved = asyncio.run(load())
    source = saved.meta_info["octop_source"]
    assert saved.tenant_id == "tenant-a" and saved.user_id == "user-a"
    assert source["template_id"] == "expert:general-assistant"
    assert source["persona_mbti"] == "INTJ"
    assert source["effective_prompt_sha256"] == hashlib.sha256(saved.system_prompt.encode()).hexdigest()
    assert source["bundled_resources_installed"] is False
    assert client.post("/api/agents", json={"name": "pinned-expert", "template_id": "expert:general-assistant"}).status_code == 409


def test_template_cannot_grant_shared_creation(catalog_client):
    client, _ = catalog_client
    body = {"name": "shared-template", "template_id": "expert:general-assistant", "is_shared": True}
    assert client.post("/api/agents", json=body).status_code == 403
    assert client.post("/api/agents", json=body, headers={"x-tenant-role": "tenant_admin"}).status_code == 201


def test_manual_creation_compatibility_and_invalid_persona(catalog_client):
    client, _ = catalog_client
    body = {"name": "manual", "system_prompt": "Existing custom instructions"}
    response = client.post("/api/agents", json=body)
    assert response.status_code == 201 and response.json()["system_prompt"] == body["system_prompt"]
    assert client.post("/api/agents", json={"name": "invalid-persona", "system_prompt": "hello", "persona_mbti": "ZZZZ"}).status_code == 422


def test_status_describes_actual_integrated_scope(catalog_client):
    client, _ = catalog_client
    response = client.get("/api/agent-catalog/status")
    assert response.status_code == 200
    status = response.json()
    assert status["integrity_verified"] and status["personas"] == 16
    assert status["mode"] == "prompt_templates"
    assert status["automatic_resource_installation"] is False
    summaries = client.get("/api/agent-catalog/templates").json()["templates"]
    assert all("system_prompt" not in entry for entry in summaries)


def test_imported_chunker_preserves_overlap_and_validates_inputs():
    assert chunk_text("abcdefghij", size=5, overlap=2) == ["abcde", "defgh", "ghij"]
    with pytest.raises(ValueError):
        chunk_text("abc", size=1, overlap=1)


def test_template_reaches_existing_runtime_prompt(catalog_client, monkeypatch):
    from deerflow import runtime
    from deerflow.agents.lead_agent import prompt as runtime_prompt
    from deerflow.config.agents_config import load_agent_config
    from deerflow.config.tenant_context import tenant_context

    # Preserve all provider registrations across this test's adapter import.
    for attribute in ("_agent_loader", "_agent_lister", "_agent_persister", "_terminal_provider", "_governed_action_provider", "_execution_validator"):
        monkeypatch.setattr(runtime, attribute, getattr(runtime, attribute))
    from app import runtime_adapters

    client, factory = catalog_client
    body = {"name": "runtime-template", "template_id": "expert:general-assistant", "persona_mbti": "INTJ", "model": "configured-model", "tool_groups": ["read"], "skills": []}
    created = client.post("/api/agents", json=body)
    assert created.status_code == 201
    monkeypatch.setattr(runtime_adapters, "get_session_factory", lambda: factory)
    monkeypatch.setattr(runtime, "_agent_loader", runtime_adapters._load_agent)
    monkeypatch.setattr(runtime, "_agent_lister", runtime_adapters._list_agents)
    monkeypatch.setattr(runtime_prompt, "_get_memory_context", lambda *args, **kwargs: "")
    monkeypatch.setattr(runtime_prompt, "get_skills_prompt_section", lambda *args: "")
    monkeypatch.setattr(runtime_prompt, "get_deferred_tools_prompt_section", lambda: "")
    load_agent_config.cache_clear()
    try:
        with tenant_context("user-a", tenant_id="tenant-a"):
            config = load_agent_config("runtime-template", user_id="user-a")
            assert config.system_prompt == created.json()["system_prompt"]
            assert config.model == body["model"] and config.tool_groups == ["read"]
            assembled = runtime_prompt.apply_prompt_template(agent_name="runtime-template", user_id="user-a")
            assert "<soul>\n" + config.system_prompt + "\n</soul>" in assembled
        assert runtime_adapters._load_agent("runtime-template", "user-b", "tenant-a") is None
        assert runtime_adapters._load_agent("runtime-template", "user-a", "tenant-b") is None
    finally:
        load_agent_config.cache_clear()
