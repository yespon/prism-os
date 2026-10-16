"""Native binary readers must honor the same controlled diagnosis Policy boundary."""

# ruff: noqa: F811 -- pytest fixture imports are resolved by name.
from pathlib import Path
from types import SimpleNamespace

import pytest
from test_file_access_boundaries import configured, durable_sqlite, owned_runtime, scoped_client, selected_runtime  # noqa: F401
from test_governed_ticket import ticket_setup  # noqa: F401

from app.alerting import governed_read_tool as reads
from deerflow.tools.builtins.office_docx import create_docx, office_docx_tool


def invoke_controlled(scope, runtime, operation):
    def handler(_request):
        return operation()

    for middleware in reversed(getattr(reads, "governed_read_middleware", lambda _: [])(scope)):
        downstream = handler

        def handler(request, middleware=middleware, downstream=downstream):
            return middleware.wrap_tool_call(request, downstream)

    return handler(SimpleNamespace(tool_call={"id": runtime.tool_call_id, "name": "office_docx"}))


def test_critical_policy_failure_blocks_native_docx_content(owned_runtime, monkeypatch):
    *_, runtime = owned_runtime
    path = Path(runtime.state["thread_data"]["outputs_path"]) / "protected.docx"
    path.write_bytes(create_docx({"paragraphs": ["PRIVATE_BINARY_READER_MARKER"]}))
    scope = {**runtime.context, "incident_id": "incident-reader"}
    monkeypatch.setenv("PRISMOS_TRUSTED_GRAPH_CONTEXT", "required")
    monkeypatch.setenv("PRISMOS_GOVERNED_TICKET_TENANT", "tenant-a")
    monkeypatch.setenv("PRISMOS_GOVERNED_TICKET_ACTION", "ticket.create")
    attempted = []

    async def active(*_args):
        return True

    async def existing(*_args):
        return None

    async def unavailable(*_args, **_kwargs):
        attempted.append(True)
        raise RuntimeError("critical Policy audit unavailable")

    monkeypatch.setattr(reads, "active_requester", active)
    monkeypatch.setattr(reads.PolicyDecisionRepository, "get_by_request", existing)
    monkeypatch.setattr(reads.PolicyService, "evaluate_and_record", unavailable)
    result = invoke_controlled(scope, runtime, lambda: office_docx_tool.func(runtime, "inspect", source_path="/mnt/user-data/outputs/protected.docx"))
    assert result["status"] == "unavailable", "Binary inspection returned data despite critical Policy failure"
    assert "PRIVATE_BINARY_READER_MARKER" not in str(result)
    assert attempted == [True]


@pytest.mark.anyio
async def test_binary_read_records_policy_and_result_and_keeps_ordinary_tasks(owned_runtime, ticket_setup, monkeypatch):
    *_, runtime = owned_runtime
    output = Path(runtime.state["thread_data"]["outputs_path"])
    for name in ("one.docx", "two.docx"):
        (output / name).write_bytes(create_docx({"paragraphs": ["AUTHORIZED_CONTENT"]}))
    scope = {**runtime.context, "incident_id": "incident-1"}
    monkeypatch.setenv("PRISMOS_TRUSTED_GRAPH_CONTEXT", "required")
    monkeypatch.setenv("PRISMOS_GOVERNED_TICKET_TENANT", "tenant-a")
    monkeypatch.setenv("PRISMOS_GOVERNED_TICKET_ACTION", "ticket.create")
    make, _, _, _, _, decisions, audits, _, _ = ticket_setup
    adapter = make("allow")
    monkeypatch.setattr(reads, "PolicyService", lambda: adapter._policy)
    monkeypatch.setattr(reads, "PolicyDecisionRepository", lambda: decisions)
    monkeypatch.setattr(reads, "AuditEventRepository", lambda: audits)

    async def active(*_):
        return True

    monkeypatch.setattr(reads, "active_requester", active)
    for name in ("one.docx", "two.docx"):
        result = invoke_controlled(scope, runtime, lambda: office_docx_tool.func(runtime, "inspect", source_path="/mnt/user-data/outputs/" + name))
        assert result["status"] == "ok" and "AUTHORIZED_CONTENT" in str(result)
    events = await audits.list_recent("tenant-a")
    assert sum(e.event_type == "action.policy_evaluated" for e in events) == 2
    assert sum(e.event_type == "action.read_result" and e.outcome == "succeeded" for e in events) == 4  # inspect reads and rechecks current access for each source
    assert all("AUTHORIZED_CONTENT" not in e.model_dump_json() for e in events)
    assert len({e.policy_decision_id for e in events}) == 2

    # The private middleware scope must be reset even while canary is enabled.
    async def failed(*_, **__):
        raise AssertionError("Ordinary Office task unexpectedly needs diagnosis Policy")

    monkeypatch.setattr(reads.PolicyService(), "evaluate_and_record", failed)
    assert office_docx_tool.func(runtime, "inspect", source_path="/mnt/user-data/outputs/one.docx")["status"] == "ok"


@pytest.mark.parametrize("change", ["user_id", "tenant_id", "thread_id", "agent_id", "call_id"])
def test_reader_scope_rejects_identity_mismatch_and_resets_after_error(owned_runtime, monkeypatch, change):
    from app.alerting.governed_native_reads import GovernedReadMiddleware, requires_governed_read
    from deerflow.runtime import ExecutionTrustError

    *_, runtime = owned_runtime
    scope = {**runtime.context, "incident_id": "incident-1"}
    monkeypatch.setenv("PRISMOS_TRUSTED_GRAPH_CONTEXT", "required")
    monkeypatch.setenv("PRISMOS_GOVERNED_TICKET_TENANT", "tenant-a")
    monkeypatch.setenv("PRISMOS_GOVERNED_TICKET_ACTION", "ticket.create")
    context = {**runtime.context, change: "other"} if change != "call_id" else runtime.context
    request = SimpleNamespace(tool_call={"id": None if change == "call_id" else "valid"})
    with pytest.raises(ExecutionTrustError):
        GovernedReadMiddleware(scope).wrap_tool_call(request, lambda _: requires_governed_read(context, "read_bytes", "/file.docx"))
    assert not requires_governed_read(runtime.context, "read_bytes", "/file.docx")


@pytest.mark.anyio
async def test_async_middleware_carries_scope_through_nested_worker_without_double_guard(monkeypatch):
    from app.alerting.governed_native_reads import GovernedReadMiddleware, recorded_read, requires_governed_read
    from app.runtime_adapters import _run_async

    scope = {"tenant_id": "tenant-a", "user_id": "user-a", "thread_id": "thread-a", "incident_id": "incident-1"}
    monkeypatch.setenv("PRISMOS_TRUSTED_GRAPH_CONTEXT", "required")
    monkeypatch.setenv("PRISMOS_GOVERNED_TICKET_TENANT", "tenant-a")
    monkeypatch.setenv("PRISMOS_GOVERNED_TICKET_ACTION", "ticket.create")

    async def nested():
        assert requires_governed_read(scope, "read_bytes", "/one")
        with recorded_read(scope, "call-a", "/one"):

            async def second():
                assert not requires_governed_read(scope, "read_bytes", "/one")
                assert requires_governed_read(scope, "read_bytes", "/two")

            _run_async(second())

    async def handler(_):
        _run_async(nested())

    await GovernedReadMiddleware(scope).awrap_tool_call(SimpleNamespace(tool_call={"id": "call-a"}), handler)
    assert not requires_governed_read(scope, "read_bytes", "/one")
