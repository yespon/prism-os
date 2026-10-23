"""Cached MCP tools retain native authority before dispatch and result delivery."""

from copy import deepcopy
from types import SimpleNamespace

import pytest
from sqlalchemy import select
from test_file_access_boundaries import configured, durable_sqlite, scoped_client, selected_runtime  # noqa: F401
from test_file_access_boundaries import owned_runtime as owned_fixture

from app.integrations import mcp_access
from app.models.agents import CustomAgent
from app.models.governance import PlatformThreadBindingRecord
from deerflow.database.models import TenantMembership
from deerflow.mcp.authorization import configuration_fingerprint, guard_mcp_tool
from deerflow.mcp.tools import _make_sync_tool_wrapper

owned_runtime = owned_fixture


@pytest.fixture
def guarded_environment(owned_runtime, monkeypatch):
    factory, _, _, _, runtime = owned_runtime
    config = {"enabled": True, "type": "http", "url": "https://test.invalid/mcp", "headers": {"Authorization": "Bearer test-secret"}}
    monkeypatch.setattr(mcp_access, "get_session_factory", lambda: factory)
    monkeypatch.setattr(mcp_access, "load_user_config_payload", lambda *_: ({}, {"mcpServers": {"ops": config}}))
    monkeypatch.setattr("deerflow.runtime.get_mcp_tool_authorizer", lambda: mcp_access.authorize_mcp_tool)
    monkeypatch.setattr("langgraph.runtime.get_runtime", lambda: SimpleNamespace(context=runtime.context))
    binding = {"tenant_id": runtime.context["tenant_id"], "user_id": runtime.context["user_id"], "server_name": "ops", "configuration_sha256": configuration_fingerprint("ops", config)}
    return factory, runtime, config, binding


async def select_server(factory, runtime):
    async with factory() as session:
        agent = await session.get(CustomAgent, runtime.context["agent_id"])
        agent.tool_groups = ["ops"]
        session.add(agent)
        await session.commit()


@pytest.mark.anyio
async def test_current_mcp_owner_can_execute_and_receive_result(guarded_environment):
    factory, runtime, _, binding = guarded_environment
    await select_server(factory, runtime)
    calls = []

    async def rpc():
        calls.append("real-function")
        return {"result": "CURRENT_AUTHORIZED_DATA"}

    tool = guard_mcp_tool(SimpleNamespace(coroutine=rpc), binding)
    assert await tool.coroutine() == {"result": "CURRENT_AUTHORIZED_DATA"}
    assert calls == ["real-function"]


@pytest.mark.anyio
@pytest.mark.parametrize("when", ["before", "after"])
@pytest.mark.parametrize("change", ["disabled", "connection", "groups", "member", "agent", "thread"])
async def test_cached_tool_denies_current_changes_without_replay(guarded_environment, change, when):
    factory, runtime, config, binding = guarded_environment
    await select_server(factory, runtime)
    calls = []

    async def revoke():
        if change == "disabled":
            config["enabled"] = False
        elif change == "connection":
            config["headers"]["Authorization"] = "Bearer rotated-secret"
        else:
            async with factory() as session:
                if change in {"groups", "agent"}:
                    record = await session.get(CustomAgent, runtime.context["agent_id"])
                    if change == "groups":
                        record.tool_groups = []
                    else:
                        record.enabled = False
                elif change == "member":
                    record = (await session.exec(select(TenantMembership))).scalars().one()
                    record.status = "inactive"
                else:
                    record = (await session.exec(select(PlatformThreadBindingRecord))).scalars().one()
                    record.user_id = "other-owner"
                session.add(record)
                await session.commit()

    async def rpc():
        calls.append("executed-once")
        if when == "after":
            await revoke()
        return {"private": "DO_NOT_DELIVER_REVOKED_RESULT"}

    tool = guard_mcp_tool(SimpleNamespace(coroutine=rpc), binding)
    if when == "before":
        await revoke()
    with pytest.raises(PermissionError):
        await tool.coroutine()
    assert calls == ([] if when == "before" else ["executed-once"])


def test_connection_fingerprint_tracks_runtime_fields_without_exporting_secrets():
    original = {"type": "http", "url": "https://test.invalid/mcp", "headers": {"Authorization": "private-value"}}
    enriched = {**original, "health_status": "connected", "description": "Updated label"}
    assert configuration_fingerprint("ops", original) == configuration_fingerprint("ops", enriched)
    changed = deepcopy(original)
    changed["headers"]["Authorization"] = "new-value"
    assert configuration_fingerprint("ops", original) != configuration_fingerprint("ops", changed)
    assert "private-value" not in configuration_fingerprint("ops", original)


@pytest.mark.anyio
async def test_sync_mcp_bridge_preserves_private_actor_and_graph_context():
    from contextvars import ContextVar

    from deerflow.config.tenant_context import get_current_tenant_id, tenant_context

    private = ContextVar("mcp-private-test", default=None)

    async def rpc():
        return get_current_tenant_id(), private.get()

    token = private.set("TRUSTED_HOST_CONTEXT")
    try:
        with tenant_context(user_id="user-a", tenant_id="tenant-a"):
            assert _make_sync_tool_wrapper(rpc, "probe")() == ("tenant-a", "TRUSTED_HOST_CONTEXT")
    finally:
        private.reset(token)


def test_parallel_event_loops_discover_without_cross_loop_lock_failure(monkeypatch):
    import asyncio
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    from deerflow.mcp import cache

    monkeypatch.setattr(cache, "_mcp_tools_cache", {})
    monkeypatch.setattr(cache, "_cache_initialized", {})
    gate = Barrier(3)

    async def load(**kwargs):
        await asyncio.sleep(0.04)
        return [SimpleNamespace(name="selected")]

    monkeypatch.setattr("deerflow.mcp.tools.get_mcp_tools", load)

    def worker(index):
        gate.wait(timeout=3)
        return asyncio.run(asyncio.wait_for(cache.initialize_mcp_tools("tenant-a", "user-a", frozenset({str(index)})), timeout=2))

    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = [pool.submit(worker, index) for index in range(3)]
        assert all(future.result(timeout=4)[0].name == "selected" for future in futures)


@pytest.mark.anyio
async def test_same_loop_same_selection_still_deduplicates_discovery(monkeypatch):
    import asyncio

    from deerflow.mcp import cache

    monkeypatch.setattr(cache, "_mcp_tools_cache", {})
    monkeypatch.setattr(cache, "_cache_initialized", {})
    calls = []

    async def load(**kwargs):
        calls.append(kwargs)
        await asyncio.sleep(0.02)
        return [SimpleNamespace(name="selected")]

    monkeypatch.setattr("deerflow.mcp.tools.get_mcp_tools", load)
    selected = frozenset({"ops"})
    first, second = await asyncio.gather(cache.initialize_mcp_tools("tenant-a", "user-a", selected), cache.initialize_mcp_tools("tenant-a", "user-a", selected))
    assert first is second and len(calls) == 1


@pytest.mark.anyio
async def test_mcp_post_dispatch_authorization_store_failure_withholds_result(monkeypatch):
    checks, calls = [], []

    async def authorize(context, binding):
        checks.append(context)
        if len(checks) == 2:
            raise RuntimeError("authorization storage unavailable")

    async def rpc():
        calls.append("executed")
        return "PRIVATE_RESULT_MUST_NOT_ESCAPE"

    monkeypatch.setattr("deerflow.runtime.get_mcp_tool_authorizer", lambda: authorize)
    monkeypatch.setattr("langgraph.runtime.get_runtime", lambda: SimpleNamespace(context={"tenant_id": "tenant-a"}))
    guarded = guard_mcp_tool(SimpleNamespace(coroutine=rpc), {})
    with pytest.raises(PermissionError, match="do not automatically repeat"):
        await guarded.coroutine()
    assert calls == ["executed"] and len(checks) == 2


@pytest.mark.anyio
async def test_ordinary_named_mcp_context_resolves_identity_without_relaxing_authority(guarded_environment):
    factory, runtime, _, binding = guarded_environment
    await select_server(factory, runtime)
    runtime.context.pop("agent_id")

    async def rpc():
        return "ORDINARY_NAMED_RESULT"

    tool = guard_mcp_tool(SimpleNamespace(coroutine=rpc), binding)
    assert await tool.coroutine() == "ORDINARY_NAMED_RESULT"
    assert "agent_id" not in runtime.context


@pytest.mark.anyio
async def test_private_protected_mcp_scope_cannot_be_retargeted(guarded_environment):
    from app.alerting.governed_native_reads import _scope

    factory, runtime, _, binding = guarded_environment
    await select_server(factory, runtime)
    calls = []

    async def rpc():
        calls.append("must-not-execute")

    tool = guard_mcp_tool(SimpleNamespace(coroutine=rpc), binding)
    token = _scope.set(({**runtime.context, "thread_id": "foreign-thread"}, "protected-call"))
    try:
        with pytest.raises(PermissionError, match="protected MCP scope"):
            await tool.coroutine()
    finally:
        _scope.reset(token)
    assert calls == []
