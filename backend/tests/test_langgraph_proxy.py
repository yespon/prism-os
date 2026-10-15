import json
from types import SimpleNamespace

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession
from starlette.responses import Response

from app.gateway.routers import langgraph_proxy
from app.models import agents as _agent_models  # noqa: F401
from app.models import governance as _governance_models  # noqa: F401
from app.models.agents import CustomAgent
from app.platform.execution import trust
from app.platform.execution.trust import ExecutionCapabilityRepository, ExecutionTrustError

real_forward = langgraph_proxy._forward


@pytest.fixture
async def proxy_setup(tmp_path, monkeypatch, native_identity):
    native_identity("user-1")
    native_identity("user-2")
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'graph-proxy.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(SQLModel.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    monkeypatch.setattr(langgraph_proxy, "get_session_factory", lambda: factory)
    monkeypatch.setattr(trust, "get_session_factory", lambda: factory)
    monkeypatch.setenv("PRISMOS_TRUSTED_GRAPH_CONTEXT", "off")
    from deerflow.database.models import Tenant, TenantMembership

    async with factory() as session, session.begin():
        session.add(Tenant(id="tenant-a", name="A", slug="a"))
        session.add(Tenant(id="tenant-b", name="B", slug="b"))
        for tenant, actor in [("tenant-a", "user-1"), ("tenant-a", "user-2"), ("tenant-b", "user-1")]:
            session.add(TenantMembership(tenant_id=tenant, user_id=actor, role="member"))
        session.add(CustomAgent(id="agent-1", tenant_id="tenant-a", user_id="user-1", name="diagnosis", enabled=True))
        session.add(CustomAgent(id="agent-2", tenant_id="tenant-a", user_id="user-1", name="disabled", enabled=False))
    state = SimpleNamespace(threads={}, calls=[])

    async def forward(method, path, body, _request):
        state.calls.append((method, path, body))
        if method == "POST" and path == "threads":
            thread_id = body["thread_id"]
            state.threads[thread_id] = {"thread_id": thread_id, "metadata": body["metadata"]}
            return Response(json.dumps(state.threads[thread_id]), media_type="application/json")
        if method == "GET" and path.startswith("threads/") and path.count("/") == 1:
            row = state.threads.get(path.split("/")[1])
            return Response(json.dumps(row or {}), status_code=200 if row else 404, media_type="application/json")
        if path == "threads/search":
            return Response(json.dumps(list(state.threads.values())), media_type="application/json")
        return Response(json.dumps({"ok": True}), media_type="application/json")

    monkeypatch.setattr(langgraph_proxy, "_forward", forward)
    app = FastAPI()

    @app.middleware("http")
    async def authenticated_test_context(request, call_next):
        request.state.user_id = request.headers.get("x-test-user", "user-1")
        request.state.tenant_id = request.headers.get("x-test-tenant", "tenant-a")
        return await call_next(request)

    app.include_router(langgraph_proxy.router)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        yield client, state, factory
    await engine.dispose()


@pytest.mark.anyio
async def test_browser_identity_is_replaced_and_thread_agent_stays_bound(proxy_setup) -> None:
    client, state, _ = proxy_setup
    created = await client.post(
        "/api/langgraph/threads",
        json={"metadata": {"owner_user_id": "victim", "owner_tenant_id": "tenant-b"}},
    )
    assert created.status_code == 200
    thread_id = created.json()["thread_id"]
    assert created.json()["metadata"]["owner_user_id"] == "user-1"
    body = {
        "assistant_id": "lead_agent",
        "context": {
            "agent_name": "diagnosis",
            "user_id": "victim",
            "tenant_id": "tenant-b",
            "thread_id": "foreign",
            "is_bootstrap": True,
            "prismos_execution_capability": "forged",
            "diagnosis_incident_id": "victim-incident",
        },
        "config": {"configurable": {"user_id": "victim", "is_bootstrap": True, "diagnosis_incident_id": "victim-incident"}, "metadata": {"tenant_id": "tenant-b", "agent_name": "other", "diagnosis_incident_id": "victim-incident"}},
        "metadata": {"owner_user_id": "victim", "owner_tenant_id": "tenant-b", "diagnosis_incident_id": "victim-incident"},
    }
    run = await client.post(f"/api/langgraph/threads/{thread_id}/runs/stream", json=body)
    assert run.status_code == 200
    forwarded = state.calls[-1][2]
    for section in [forwarded["context"], forwarded["config"]["configurable"], forwarded["config"]["metadata"], forwarded["metadata"]]:
        assert "diagnosis_incident_id" not in section
    assert forwarded["context"]["user_id"] == "user-1"
    assert forwarded["context"]["tenant_id"] == "tenant-a"
    assert forwarded["context"]["thread_id"] == thread_id
    assert "is_bootstrap" not in forwarded["context"]
    assert "prismos_execution_capability" not in forwarded["context"]
    assert "user_id" not in forwarded["config"]["configurable"]
    assert "tenant_id" not in forwarded["config"]["metadata"]
    assert forwarded["metadata"]["owner_user_id"] == "user-1"
    assert forwarded["metadata"]["owner_tenant_id"] == "tenant-a"
    assert (
        await client.post(
            f"/api/langgraph/threads/{thread_id}/runs/stream",
            json={
                "assistant_id": "lead_agent",
                "context": {"agent_name": "other"},
            },
        )
    ).status_code == 403
    assert (
        await client.post(
            f"/api/langgraph/threads/{thread_id}/runs/stream",
            json={
                "assistant_id": "lead_agent",
                "context": {},
            },
        )
    ).status_code == 200
    assert state.calls[-1][2]["context"]["agent_name"] == "diagnosis"


@pytest.mark.anyio
async def test_cross_tenant_disabled_agent_and_unlisted_run_endpoints_are_blocked(proxy_setup) -> None:
    client, state, _ = proxy_setup
    created = await client.post("/api/langgraph/threads", json={})
    thread_id = created.json()["thread_id"]
    other = {"x-test-user": "user-2"}
    assert (await client.get(f"/api/langgraph/threads/{thread_id}", headers=other)).status_code == 404
    assert (await client.get(f"/api/langgraph/threads/{thread_id}", headers={"x-test-tenant": "tenant-b"})).status_code == 404
    assert (
        await client.post(
            f"/api/langgraph/threads/{thread_id}/runs/stream",
            json={
                "assistant_id": "lead_agent",
                "context": {"agent_name": "disabled"},
            },
        )
    ).status_code == 403
    assert (await client.post(f"/api/langgraph/threads/{thread_id}/runs/crons", json={})).status_code == 403
    assert (await client.post(f"/api/langgraph/threads/{thread_id}", json={})).status_code == 403
    assert (await client.post("/api/langgraph/runs/stream", json={"assistant_id": "lead_agent"})).status_code == 403
    assert (await client.post("/api/langgraph/threads", json={"thread_id": "attacker-selected"})).status_code == 400
    assert not any(path == f"threads/{thread_id}/runs/crons" for _, path, _ in state.calls)


@pytest.mark.anyio
async def test_legacy_thread_requires_matching_owner_metadata(proxy_setup) -> None:
    client, state, _ = proxy_setup
    state.threads["old-thread"] = {
        "thread_id": "old-thread",
        "metadata": {
            "owner_user_id": "user-1",
            "owner_tenant_id": "tenant-a",
        },
    }
    assert (await client.get("/api/langgraph/threads/old-thread")).status_code == 200
    assert (await client.get("/api/langgraph/threads/old-thread", headers={"x-test-user": "user-2"})).status_code == 404
    assert (
        await client.post(
            "/api/langgraph/threads/old-thread/runs/stream",
            json={
                "assistant_id": "lead_agent",
                "context": {"agent_name": "diagnosis"},
            },
        )
    ).status_code == 200
    assert (
        await client.post(
            "/api/langgraph/threads/old-thread/runs/stream",
            json={
                "assistant_id": "lead_agent",
                "context": {},
            },
        )
    ).status_code == 200
    assert state.calls[-1][2]["context"]["agent_name"] == "diagnosis"
    assert (
        await client.post(
            "/api/langgraph/threads/old-thread/runs/stream",
            json={
                "assistant_id": "lead_agent",
                "context": {"agent_name": "disabled"},
            },
        )
    ).status_code == 403
    state.threads["unowned"] = {"thread_id": "unowned", "metadata": {}}
    assert (await client.get("/api/langgraph/threads/unowned")).status_code == 404


@pytest.mark.anyio
async def test_proxy_issues_single_use_capability_for_graph(proxy_setup, monkeypatch) -> None:
    client, state, factory = proxy_setup
    monkeypatch.setenv("PRISMOS_TRUSTED_GRAPH_CONTEXT", "required")
    created = await client.post("/api/langgraph/threads", json={})
    thread_id = created.json()["thread_id"]
    response = await client.post(
        f"/api/langgraph/threads/{thread_id}/runs/stream",
        json={
            "assistant_id": "lead_agent",
            "context": {"agent_name": "diagnosis", "action_incident_id": "forged-incident", "prismos_action_incident_id": "forged-incident"},
        },
    )
    assert response.status_code == 200
    context = state.calls[-1][2]["context"]
    assert "action_incident_id" not in context and "prismos_action_incident_id" not in context
    token = context["prismos_execution_capability"]
    capabilities = ExecutionCapabilityRepository(factory)
    assert await capabilities.consume(token, "tenant-a", "user-1", thread_id, "diagnosis") is None
    with pytest.raises(ExecutionTrustError, match="replay"):
        await capabilities.consume(token, "tenant-a", "user-1", thread_id, "diagnosis")


@pytest.mark.anyio
async def test_agent_disabled_after_binding_blocks_next_run(proxy_setup) -> None:
    client, state, factory = proxy_setup
    created = await client.post("/api/langgraph/threads", json={})
    thread_id = created.json()["thread_id"]
    run_body = {"assistant_id": "lead_agent", "context": {"agent_name": "diagnosis"}}
    assert (await client.post(f"/api/langgraph/threads/{thread_id}/runs/stream", json=run_body)).status_code == 200
    async with factory() as session, session.begin():
        agent = await session.get(CustomAgent, "agent-1")
        agent.enabled = False
        session.add(agent)
    prior_calls = len(state.calls)
    assert (await client.post(f"/api/langgraph/threads/{thread_id}/runs/stream", json=run_body)).status_code == 403
    assert len(state.calls) == prior_calls


@pytest.mark.anyio
async def test_history_stream_stops_after_current_membership_withdrawal(proxy_setup, monkeypatch):
    from sqlalchemy import select
    from starlette.requests import Request

    from deerflow.database.models import TenantMembership

    _, _, factory = proxy_setup
    await trust.ThreadBindingRepository(factory).create("stream-thread", "tenant-a", "user-1")
    request = Request({"type": "http", "method": "GET", "path": "/", "headers": [], "query_string": b"", "state": {"tenant_id": "tenant-a", "user_id": "user-1"}})
    closed = []

    async def chunks():
        yield b"data: CURRENT\n\n"
        yield b"data: REVOKED SECRET\n\n"

    async def close():
        closed.append(True)

    upstream = SimpleNamespace(headers={"content-type": "text/event-stream"}, is_success=True, status_code=200, aiter_raw=chunks, aclose=close)
    client = SimpleNamespace(aclose=close)

    async def connect(*args, **kwargs):
        return upstream, client

    monkeypatch.setattr(langgraph_proxy, "_upstream", connect)
    response = await real_forward("GET", "threads/stream-thread/history", None, request)
    iterator = response.body_iterator
    assert await anext(iterator) == b"data: CURRENT\n\n"
    async with factory() as session:
        member = (await session.exec(select(TenantMembership).where(TenantMembership.user_id == "user-1", TenantMembership.tenant_id == "tenant-a"))).scalars().one()
        member.status = "inactive"
        session.add(member)
        await session.commit()
    with pytest.raises(StopAsyncIteration):
        await anext(iterator)
    assert len(closed) == 2


@pytest.mark.anyio
async def test_buffered_history_discards_result_when_membership_withdrawn_while_waiting(proxy_setup, monkeypatch):
    from fastapi import HTTPException
    from sqlalchemy import select
    from starlette.requests import Request

    from deerflow.database.models import TenantMembership

    _, _, factory = proxy_setup
    request = Request({"type": "http", "method": "GET", "path": "/", "headers": [], "query_string": b"", "state": {"tenant_id": "tenant-a", "user_id": "user-1"}})

    async def read():
        async with factory() as session:
            member = (await session.exec(select(TenantMembership).where(TenantMembership.user_id == "user-1", TenantMembership.tenant_id == "tenant-a"))).scalars().one()
            member.status = "inactive"
            session.add(member)
            await session.commit()
        return b"REVOKED HISTORY"

    closed = []

    async def close():
        closed.append(True)

    upstream = SimpleNamespace(headers={"content-type": "application/json"}, is_success=True, status_code=200, aread=read, aclose=close)
    client = SimpleNamespace(aclose=close)

    async def connect(*args, **kwargs):
        return upstream, client

    monkeypatch.setattr(langgraph_proxy, "_upstream", connect)
    with pytest.raises(HTTPException) as denied:
        await real_forward("GET", "threads/history-thread/history", None, request)
    assert denied.value.status_code == 403 and len(closed) == 2
