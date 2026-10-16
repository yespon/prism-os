"""Actual child executor preserves native authority and private scoped read context."""

import importlib.util
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest
from langchain.tools import ToolRuntime
from langchain_core.messages import AIMessage
from test_file_access_boundaries import configured, durable_sqlite, scoped_client, selected_runtime  # noqa: F401
from test_file_access_boundaries import owned_runtime as parent_runtime

from deerflow.subagents.config import SubagentConfig
from deerflow.tools.builtins.office_docx import office_docx_tool

owned_runtime = parent_runtime


@pytest.fixture
def real_executor(monkeypatch):
    path = Path(__file__).resolve().parents[1] / "packages/harness/deerflow/subagents/executor.py"
    spec = importlib.util.spec_from_file_location("prismos_child_executor_actual", path)
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, spec.name, module)
    spec.loader.exec_module(module)
    yield module
    module._scheduler_pool.shutdown(wait=True)
    module._execution_pool.shutdown(wait=True)


@pytest.mark.anyio
@pytest.mark.parametrize("revoked", [False, True])
async def test_child_native_context_writes_owned_docx_without_weakening_file_guard(real_executor, owned_runtime, monkeypatch, revoked):
    factory, *_, runtime = owned_runtime
    observed = []

    class Child:
        async def astream(self, state, config, context, **_):
            observed.append(context)
            child = ToolRuntime(state=state, config=config, context=context, stream_writer=lambda _: None, tool_call_id="child-native", store=None)
            if revoked:
                from sqlalchemy import select

                from deerflow.database.models import TenantMembership

                async with factory() as session:
                    member = (await session.exec(select(TenantMembership))).scalars().one()
                    member.status = "inactive"
                    session.add(member)
                    await session.commit()
            result = office_docx_tool.func(child, "create", output_path="/mnt/user-data/outputs/child.docx", document={"paragraphs": ["CHILD_AUTHORIZED_RESULT"]})
            assert result["status"] == ("unavailable" if revoked else "ok")
            yield {"messages": [AIMessage(content="Created owned document")]}

    cfg = SubagentConfig("general-purpose", "test", "test")
    executor = real_executor.SubagentExecutor(
        cfg, [], thread_id=runtime.context["thread_id"], user_id=runtime.context["user_id"], tenant_id=runtime.context["tenant_id"], thread_data=runtime.state["thread_data"], execution_context=runtime.context
    )
    monkeypatch.setattr(executor, "_create_agent", lambda: Child())
    result = await executor._aexecute("Create document")
    assert result.status == real_executor.SubagentStatus.COMPLETED, result.error
    assert observed == [runtime.context]
    assert (Path(runtime.state["thread_data"]["outputs_path"]) / "child.docx").is_file() is not revoked


def test_child_cannot_retarget_parent_identity(real_executor):
    cfg = SubagentConfig("general-purpose", "test", "test")
    with pytest.raises(ValueError, match="retarget"):
        real_executor.SubagentExecutor(cfg, [], tenant_id="tenant-a", execution_context={"tenant_id": "tenant-b"})


def test_private_governed_read_scope_crosses_both_pools_without_leaking(real_executor, monkeypatch):
    from app.alerting.governed_native_reads import GovernedReadMiddleware, governed_read_middleware
    from deerflow.database import subagent_store

    monkeypatch.setattr(subagent_store, "persist_subagent_run", lambda **_: None)
    monkeypatch.setenv("PRISMOS_TRUSTED_GRAPH_CONTEXT", "required")
    monkeypatch.setenv("PRISMOS_GOVERNED_TICKET_TENANT", "tenant-a")
    monkeypatch.setenv("PRISMOS_GOVERNED_TICKET_ACTION", "ticket.create")
    observed = []

    class Child:
        async def astream(self, state, **_):
            observed.append(bool(governed_read_middleware(None)))
            yield {"messages": [AIMessage(content="finished")]}

    executor = real_executor.SubagentExecutor(SubagentConfig("general-purpose", "test", "test"), [])
    monkeypatch.setattr(executor, "_create_agent", lambda: Child())
    scope = {"tenant_id": "tenant-a", "user_id": "user-a", "thread_id": "thread-a", "incident_id": "incident-a"}
    request = SimpleNamespace(tool_call={"id": "parent-call"})
    GovernedReadMiddleware(scope).wrap_tool_call(request, lambda _: executor.execute_async("controlled", task_id="controlled"))
    executor.execute_async("ordinary", task_id="ordinary")
    for _ in range(500):
        results = [real_executor.get_background_task_result(key) for key in ["controlled", "ordinary"]]
        if all(r and r.status in {real_executor.SubagentStatus.COMPLETED, real_executor.SubagentStatus.FAILED} for r in results):
            break
        time.sleep(0.01)
    assert all(r.status == real_executor.SubagentStatus.COMPLETED for r in results)
    assert sorted(observed) == [False, True]
    assert governed_read_middleware(None) == []


@pytest.mark.anyio
@pytest.mark.parametrize("model_allowed", [True, False])
async def test_child_model_uses_parent_tenant_and_current_allowlist(real_executor, monkeypatch, model_allowed):
    from deerflow.agents.middlewares import tool_error_handling_middleware
    from deerflow.config.tenant_context import get_current_tenant_id, tenant_context
    from deerflow.database import user_config_store

    observed = []

    def allowed(tenant):
        assert tenant == "tenant-a" and get_current_tenant_id() == "tenant-a"
        return ["parent-model"] if model_allowed else ["other-model"]

    def model(**kwargs):
        observed.append((get_current_tenant_id(), kwargs["name"]))
        return object()

    class Child:
        async def astream(self, *_, **__):
            assert get_current_tenant_id() == "tenant-a"
            yield {"messages": [AIMessage(content="finished")]}

    monkeypatch.setattr(user_config_store, "load_enabled_tenant_model_names", allowed)
    monkeypatch.setattr(real_executor, "create_chat_model", model)

    def build(**kwargs):
        assert kwargs["checkpointer"] is False
        return Child()

    monkeypatch.setattr(real_executor, "create_agent", build)
    monkeypatch.setattr(tool_error_handling_middleware, "build_subagent_runtime_middlewares", lambda **_: [])
    monkeypatch.setattr("deerflow.runtime.get_execution_middleware_provider", lambda: None)
    executor = real_executor.SubagentExecutor(SubagentConfig("general-purpose", "test", "test"), [], parent_model="parent-model", tenant_id="tenant-a")
    with tenant_context(user_id="outer-user", tenant_id="outer"):
        result = await executor._aexecute("work")
        assert get_current_tenant_id() == "outer"
    assert result.status == (real_executor.SubagentStatus.COMPLETED if model_allowed else real_executor.SubagentStatus.FAILED)
    assert observed == ([("tenant-a", "parent-model")] if model_allowed else [])


@pytest.mark.anyio
async def test_background_child_does_not_use_parent_loop_bound_checkpointer(real_executor, monkeypatch):
    import asyncio
    from threading import get_ident

    from langgraph.checkpoint.memory import InMemorySaver
    from langgraph.graph import END, START, StateGraph

    from deerflow.agents.middlewares import tool_error_handling_middleware
    from deerflow.database import subagent_store

    parent_thread = get_ident()

    class ParentSaver(InMemorySaver):
        async def aget_tuple(self, *args, **kwargs):
            assert get_ident() == parent_thread, "Child inherited loop-bound parent saver"
            return await super().aget_tuple(*args, **kwargs)

        async def aput_writes(self, *args, **kwargs):
            assert get_ident() == parent_thread, "Child inherited loop-bound parent saver"
            return await super().aput_writes(*args, **kwargs)

    def build(**kwargs):
        async def child_node(state):
            assert get_ident() != parent_thread
            return {"messages": [AIMessage(content="CHILD_COMPLETED")]}

        graph = StateGraph(dict)
        graph.add_node("child", child_node)
        graph.add_edge(START, "child")
        graph.add_edge("child", END)
        return graph.compile(checkpointer=kwargs.get("checkpointer"))

    monkeypatch.setattr(real_executor, "create_chat_model", lambda **_: object())
    monkeypatch.setattr(real_executor, "create_agent", build)
    monkeypatch.setattr(tool_error_handling_middleware, "build_subagent_runtime_middlewares", lambda **_: [])
    monkeypatch.setattr("deerflow.runtime.get_execution_middleware_provider", lambda: None)
    monkeypatch.setattr(subagent_store, "persist_subagent_run", lambda **_: None)
    executor = real_executor.SubagentExecutor(SubagentConfig("general-purpose", "test", "test"), [])

    async def parent_node(state):
        executor.execute_async("work", task_id="loop-guard")
        for _ in range(500):
            result = real_executor.get_background_task_result("loop-guard")
            if result.status in {real_executor.SubagentStatus.COMPLETED, real_executor.SubagentStatus.FAILED}:
                break
            await asyncio.sleep(0.01)
        assert result.status == real_executor.SubagentStatus.COMPLETED, result.error
        assert result.result == "CHILD_COMPLETED"
        return {"messages": [AIMessage(content=result.result)]}

    graph = StateGraph(dict)
    graph.add_node("parent", parent_node)
    graph.add_edge(START, "parent")
    graph.add_edge("parent", END)
    parent = graph.compile(checkpointer=ParentSaver())
    final = await parent.ainvoke({"messages": []}, {"configurable": {"thread_id": "parent-loop"}})
    assert final["messages"][0].content == "CHILD_COMPLETED"
