from datetime import UTC, datetime, timedelta
from hashlib import sha256
from types import SimpleNamespace

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel import SQLModel, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.alerting.governed_ticket import TicketActionAdapter, TicketTarget
from app.alerting.legacy_audit_delivery import LegacyAuditDeliveryService
from app.alerting.ticket_provider import TicketResult
from app.models import alerting as _alert_models  # noqa: F401
from app.models import governance as _governance_models  # noqa: F401
from app.models.alerting import Incident, IncidentAction
from app.platform.approval.repository import ApprovalRepository
from app.platform.approval.service import ApprovalService
from app.platform.audit.repository import AuditEventRepository
from app.platform.contracts import ExecutionEnvelope, IdentityRef
from app.platform.policy.evaluator import PolicyConfiguration, PolicyRule
from app.platform.policy.fact_writer import PolicyFactWriter
from app.platform.policy.repository import PolicyDecisionRepository
from app.platform.policy.service import PolicyService
from app.platform.submission.repository import ActionSubmissionRepository

NOW = datetime(2026, 9, 24, 10, 0, tzinfo=UTC)


@pytest.fixture
async def ticket_setup(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'governed-ticket.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(SQLModel.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    incident = Incident(
        id="incident-1", tenant_id="tenant-a", incident_key="INC-1", title="Alarm",
        severity="high", status="open", summary="Initial finding",
        first_seen_at=NOW, last_seen_at=NOW,
    )
    target = TicketTarget(
        incident=incident,
        config={"provider": "webhook", "webhook_url": "https://tickets.example/create"},
        signals=[],
    )
    state = SimpleNamespace(allowed=True, allowed_sequence=[], calls=[], linked=[], gateway_events=[])

    async def resolve(tenant_id, incident_id):
        assert (tenant_id, incident_id) == ("tenant-a", "incident-1")
        return target

    async def permission(_tenant, _actor):
        return state.allowed_sequence.pop(0) if state.allowed_sequence else state.allowed

    async def send(inc, config, signals, *, idempotency_key):
        state.calls.append(idempotency_key)
        return TicketResult(ticket_id="T-1", ticket_url="https://tickets.example/T-1", provider="webhook")

    async def link(_tenant, _incident, result):
        state.linked.append(result.ticket_id)
        incident.ticket_id = result.ticket_id

    async def member(user_id, tenant_id):
        return SimpleNamespace(role="admin" if user_id == "admin-1" else "member") if state.allowed else None

    async def tenant(tenant_id):
        return object() if tenant_id == "tenant-a" else None

    decisions = PolicyDecisionRepository(factory)
    approvals = ApprovalRepository(factory)
    submissions = ActionSubmissionRepository(factory)
    state.delivery = LegacyAuditDeliveryService(factory, gateway_writer=lambda event: state.gateway_events.append(event))
    approval_service = ApprovalService(approvals, decisions, member, tenant)
    policy = PolicyService(PolicyFactWriter(factory), decisions)
    execution = ExecutionEnvelope(
        tenant_id="tenant-a", task_id="task-1", run_id="run-1", correlation_id="alert-1",
        workload=IdentityRef(kind="workload", id="diagnosis-agent", tenant_id="tenant-a"),
        actor=IdentityRef(kind="user", id="user-1", tenant_id="tenant-a"), occurred_at=NOW,
    )

    def adapter(verdict="allow", *, enabled=True, sender=send, linker=link):
        config = PolicyConfiguration(
            policy_id="ticket-m1", version="v1",
            rules={"ticket.create": PolicyRule(risk_class="side_effect", verdict=verdict)},
        )
        return TicketActionAdapter(
            enabled_tenants=frozenset({"tenant-a"}) if enabled else frozenset(),
            configuration=config, policy=policy, approvals=approvals,
            approval_service=approval_service, submissions=submissions,
            resolve_target=resolve, check_permission=permission,
            send_ticket=sender, link_ticket=linker, deliveries=state.delivery,
        )

    yield adapter, execution, state, approvals, approval_service, decisions, AuditEventRepository(factory), submissions, incident
    await engine.dispose()


@pytest.mark.anyio
async def test_disabled_adapter_never_calls_provider(ticket_setup) -> None:
    make, execution, state, *_ = ticket_setup
    with pytest.raises(PermissionError, match="disabled"):
        await make(enabled=False).execute(execution, "request-1", "incident-1", at=NOW)
    assert state.calls == []


@pytest.mark.anyio
async def test_allow_submits_once_and_repeats_read_stored_fact(ticket_setup) -> None:
    make, execution, state, _, _, decisions, audits, submissions, _ = ticket_setup
    adapter = make("allow")
    first = await adapter.execute(execution, "request-1", "incident-1", at=NOW)
    second = await adapter.execute(execution, "request-1", "incident-1", at=NOW + timedelta(seconds=1))
    assert first.status == second.status == "submitted"
    assert first.idempotency_key == second.idempotency_key == state.calls[0]
    assert len(state.calls) == 1
    assert state.linked == ["T-1"]
    assert (await submissions.get("tenant-a", first.decision_id)).status == "submitted"
    assert (await audits.list_recent("tenant-a"))[0].event_type == "action.submitted"
    assert (await decisions.get_by_request("tenant-a", "request-1")).verdict == "allow"


@pytest.mark.anyio
@pytest.mark.parametrize("config_change", [
    {"headers": {"Authorization": "Bearer private-secret"}},
    {"headers": []},
    {"webhook_url": "https://user:private-secret@tickets.example/create"},
    {"webhook_url": "https://tickets.example/create?token=private-secret"},
    {"webhook_url": "http://tickets.example/create"},
])
async def test_inline_webhook_credentials_fail_before_policy_or_submission(ticket_setup, config_change) -> None:
    make, execution, state, _, _, decisions, _, _, _ = ticket_setup
    adapter = make("allow")
    target = await adapter._resolve_target("tenant-a", "incident-1")
    target.config.update(config_change)
    with pytest.raises(ValueError, match="credential-free HTTPS|inline webhook headers"):
        await adapter.execute(execution, "request-1", "incident-1", at=NOW)
    assert state.calls == []
    assert await decisions.get_by_request("tenant-a", "request-1") is None


@pytest.mark.anyio
async def test_approval_waits_then_consumes_before_single_submission(ticket_setup) -> None:
    make, execution, state, approvals, approval_service, _, _, _, _ = ticket_setup
    adapter = make("require_approval")
    waiting = await adapter.execute(execution, "request-1", "incident-1", at=NOW)
    assert waiting.status == "awaiting_approval" and state.calls == []
    await approval_service.review("tenant-a", waiting.approval_id, "admin-1", "approve", at=NOW + timedelta(minutes=1))
    submitted = await adapter.execute(execution, "request-1", "incident-1", at=NOW + timedelta(minutes=2))
    assert submitted.status == "submitted"
    assert (await approvals.get("tenant-a", waiting.approval_id))[0].status == "consumed"
    assert len(state.calls) == 1
    assert (await adapter.execute(execution, "request-1", "incident-1", at=NOW + timedelta(minutes=3))).status == "submitted"
    assert len(state.calls) == 1


@pytest.mark.anyio
async def test_timeout_stays_unknown_without_automatic_retry(ticket_setup) -> None:
    make, execution, state, _, _, _, audits, submissions, _ = ticket_setup

    async def timeout(*_args, **kwargs):
        state.calls.append(kwargs["idempotency_key"])
        raise TimeoutError("remote result unknown")

    adapter = make("allow", sender=timeout)
    first = await adapter.execute(execution, "request-1", "incident-1", at=NOW)
    second = await adapter.execute(execution, "request-1", "incident-1", at=NOW + timedelta(seconds=1))
    assert first.status == second.status == "unknown"
    assert len(state.calls) == 1
    assert (await submissions.get("tenant-a", first.decision_id)).status == "unknown"
    unknown = next(e for e in await audits.list_recent("tenant-a") if e.event_type == "action.submission_unknown")
    assert unknown.payload == {"reason_code": "provider_result_unknown"}


@pytest.mark.anyio
async def test_revocation_or_context_change_blocks_approved_action(ticket_setup) -> None:
    make, execution, state, _, approval_service, _, _, _, incident = ticket_setup
    adapter = make("require_approval")
    waiting = await adapter.execute(execution, "request-1", "incident-1", at=NOW)
    await approval_service.review("tenant-a", waiting.approval_id, "admin-1", "approve", at=NOW + timedelta(minutes=1))
    state.allowed = False
    with pytest.raises(PermissionError):
        await adapter.execute(execution, "request-1", "incident-1", at=NOW + timedelta(minutes=2))
    state.allowed = True
    incident.summary = "Changed after approval"
    with pytest.raises(ValueError, match="context"):
        await adapter.execute(execution, "request-1", "incident-1", at=NOW + timedelta(minutes=2))
    assert state.calls == []


@pytest.mark.anyio
async def test_destination_change_does_not_consume_approval(ticket_setup) -> None:
    make, execution, state, approvals, approval_service, _, _, _, _ = ticket_setup
    adapter = make("require_approval")
    waiting = await adapter.execute(execution, "request-1", "incident-1", at=NOW)
    await approval_service.review("tenant-a", waiting.approval_id, "admin-1", "approve", at=NOW + timedelta(minutes=1))
    original_resolver = adapter._resolve_target
    resolution_count = 0

    async def changed_after_policy(tenant_id, incident_id):
        nonlocal resolution_count
        resolution_count += 1
        target = await original_resolver(tenant_id, incident_id)
        if resolution_count == 2:
            return TicketTarget(target.incident, {**target.config, "headers": {"Authorization": "Bearer private-secret"}}, target.signals)
        return target

    adapter._resolve_target = changed_after_policy
    with pytest.raises(ValueError, match="inline webhook headers"):
        await adapter.execute(execution, "request-1", "incident-1", at=NOW + timedelta(minutes=2))
    assert resolution_count == 2
    assert (await approvals.get("tenant-a", waiting.approval_id))[0].status == "approved"
    assert state.calls == []


@pytest.mark.anyio
async def test_critical_audit_failure_prevents_external_submission(ticket_setup, monkeypatch) -> None:
    make, execution, state, _, _, decisions, audits, _, _ = ticket_setup

    async def failed_audit(*_args):
        raise RuntimeError("audit storage failed")

    monkeypatch.setattr(AuditEventRepository, "append_in_session", failed_audit)
    with pytest.raises(RuntimeError, match="audit storage"):
        await make("allow").execute(execution, "request-1", "incident-1", at=NOW)
    assert state.calls == []
    assert await decisions.get_by_request("tenant-a", "request-1") is None
    assert await audits.list_recent("tenant-a") == []


@pytest.mark.anyio
async def test_permission_revoked_immediately_before_claim_prevents_send(ticket_setup) -> None:
    make, execution, state, *_ = ticket_setup
    state.allowed_sequence = [True, False]
    with pytest.raises(PermissionError, match="authorization changed"):
        await make("allow").execute(execution, "request-1", "incident-1", at=NOW)
    assert state.calls == []


@pytest.mark.anyio
async def test_result_write_failure_stays_unknown_and_does_not_resend(ticket_setup, monkeypatch) -> None:
    make, execution, state, _, _, _, _, submissions, _ = ticket_setup

    async def failed_write(*_args, **_kwargs):
        raise RuntimeError("result database unavailable")

    monkeypatch.setattr(submissions, "mark_submitted", failed_write)
    adapter = make("allow")
    first = await adapter.execute(execution, "request-1", "incident-1", at=NOW)
    second = await adapter.execute(execution, "request-1", "incident-1", at=NOW + timedelta(seconds=1))
    assert first.status == second.status == "unknown"
    assert len(state.calls) == 1
    assert (await submissions.get("tenant-a", first.decision_id)).status == "unknown"


@pytest.mark.anyio
async def test_link_failure_preserves_submitted_fact_for_reconciliation(ticket_setup) -> None:
    make, execution, state, _, _, _, _, submissions, _ = ticket_setup

    async def failed_link(*_args):
        raise RuntimeError("incident update failed")

    result = await make("allow", linker=failed_link).execute(execution, "request-1", "incident-1", at=NOW)
    assert result.status == "submitted" and result.needs_reconciliation
    assert (await submissions.get("tenant-a", result.decision_id)).status == "submitted"
    repeated = await make("allow", linker=failed_link).execute(execution, "request-1", "incident-1", at=NOW + timedelta(seconds=1))
    assert repeated.status == "submitted" and repeated.needs_reconciliation
    assert len(state.calls) == 1


@pytest.mark.anyio
async def test_waiting_approval_expires_without_external_submission(ticket_setup) -> None:
    make, execution, state, approvals, _, _, _, _, _ = ticket_setup
    adapter = make("require_approval")
    waiting = await adapter.execute(execution, "request-1", "incident-1", at=NOW)
    expired = await adapter.execute(execution, "request-1", "incident-1", at=NOW + timedelta(minutes=6))
    assert waiting.status == "awaiting_approval"
    assert expired.status == "expired"
    assert (await approvals.get("tenant-a", waiting.approval_id))[0].status == "expired"
    assert state.calls == []


@pytest.mark.anyio
async def test_denied_rule_persists_decision_without_provider_call(ticket_setup) -> None:
    make, execution, state, _, _, decisions, audits, _, _ = ticket_setup
    outcome = await make("deny").execute(execution, "request-1", "incident-1", at=NOW)
    assert outcome.status == "denied"
    assert (await decisions.get("tenant-a", outcome.decision_id)).verdict == "deny"
    assert (await audits.list_recent("tenant-a"))[0].outcome == "denied"
    assert state.calls == []


@pytest.mark.anyio
async def test_rejected_approval_never_submits(ticket_setup) -> None:
    make, execution, state, _, approval_service, _, _, _, _ = ticket_setup
    adapter = make("require_approval")
    waiting = await adapter.execute(execution, "request-1", "incident-1", at=NOW)
    await approval_service.review("tenant-a", waiting.approval_id, "admin-1", "reject", at=NOW + timedelta(minutes=1))
    rejected = await adapter.execute(execution, "request-1", "incident-1", at=NOW + timedelta(minutes=2))
    assert rejected.status == "rejected"
    assert state.calls == []


@pytest.mark.anyio
async def test_result_audit_and_legacy_delivery_replay(ticket_setup) -> None:
    make, execution, state, _, _, _, audits, submissions, _ = ticket_setup
    def fail_gateway(_event):
        raise OSError("private-secret: disk unavailable")
    state.delivery._gateway_writer = fail_gateway
    outcome = await make("allow").execute(execution, "request-1", "incident-1", at=NOW)
    assert outcome.status == "submitted" and len(state.calls) == 1
    events = await audits.list_recent("tenant-a")
    result = next(event for event in events if event.event_type == "action.submitted")
    assert result.policy_decision_id == outcome.decision_id
    assert result.execution == execution
    assert "private-secret" not in result.model_dump_json()
    pending = await state.delivery.list_undelivered("tenant-a")
    assert len(pending) == 1 and pending[0].destination == "gateway_jsonl"
    assert pending[0].attempts == 1 and pending[0].error_category == "OSError"
    assert "private-secret" not in str(pending)
    state.delivery._gateway_writer = lambda event: state.gateway_events.append(event)
    assert await state.delivery.replay("tenant-a") == 1
    assert await state.delivery.list_undelivered("tenant-a") == []
    assert len(state.gateway_events) == 1
    assert state.gateway_events[0]["event_id"] == result.event_id
    async with state.delivery._session_factory() as session:
        action = (await session.exec(select(IncidentAction).where(IncidentAction.id == result.event_id))).one()
        assert action.action_type == "ticket_created"
        assert action.action_payload["ticket_id"] == "T-1"
        assert "private-secret" not in str(action.action_payload)
    assert (await submissions.get("tenant-a", outcome.decision_id)).status == "submitted"
    assert len(state.calls) == 1


@pytest.mark.anyio
async def test_replay_is_tenant_scoped_and_never_resubmits_ticket(ticket_setup) -> None:
    make, execution, state, _, _, _, audits, _, _ = ticket_setup
    result = await make("allow").execute(execution, "request-1", "incident-1", at=NOW)
    event = next(e for e in await audits.list_recent("tenant-a") if e.event_type == "action.submitted")
    assert await state.delivery.replay("tenant-b") == 0
    assert len(state.calls) == 1
    assert len(state.gateway_events) == 1
    assert await state.delivery.replay("tenant-a") == 0
    assert (await state.delivery.counts("tenant-a"))["delivered"] == 2
    assert event.policy_decision_id == result.decision_id


@pytest.mark.anyio
async def test_result_audit_failure_keeps_submission_unknown(ticket_setup, monkeypatch) -> None:
    make, execution, state, _, _, _, audits, submissions, _ = ticket_setup
    original = AuditEventRepository.append_in_session

    async def fail_result(session, event):
        if event.event_type == "action.submitted":
            raise RuntimeError("result audit unavailable")
        return await original(session, event)

    monkeypatch.setattr(AuditEventRepository, "append_in_session", fail_result)
    outcome = await make("allow").execute(execution, "request-1", "incident-1", at=NOW)
    assert outcome.status == "unknown"
    assert (await submissions.get("tenant-a", outcome.decision_id)).status == "unknown"
    assert await state.delivery.list_undelivered("tenant-a") == []
    assert all(e.event_type != "action.submitted" for e in await audits.list_recent("tenant-a"))
    assert len(state.calls) == 1

@pytest.mark.anyio
async def test_diagnosis_agent_tool_reaches_provider_once_and_exposes_platform_facts(ticket_setup, monkeypatch) -> None:
    from app.alerting import governed_ticket_tool as agent_action

    make, _, state, _, _, decisions, audits, _, _ = ticket_setup
    monkeypatch.setenv("PRISMOS_TRUSTED_GRAPH_CONTEXT", "required")
    monkeypatch.setenv("PRISMOS_GOVERNED_TICKET_TENANT", "tenant-a")
    monkeypatch.setenv("PRISMOS_GOVERNED_TICKET_ACTION", "ticket.create")
    monkeypatch.setattr(agent_action, "ticket_adapter", lambda _tenant: make("allow"))
    monkeypatch.setattr(agent_action, "PolicyDecisionRepository", lambda: decisions)
    scope = {"tenant_id": "tenant-a", "user_id": "user-1", "thread_id": "diagnosis-thread-1",
             "agent_name": "diagnosis", "incident_id": "incident-1"}
    tools = agent_action.governed_ticket_tools(scope)
    assert [tool.name for tool in tools] == ["create_governed_incident_ticket", "read_file"]
    first = await tools[0].ainvoke({})
    repeated = await tools[0].ainvoke({})
    assert first == repeated
    assert first["status"] == "submitted" and first["ticket_id"] == "T-1"
    assert len(state.calls) == 1
    decision = await decisions.get("tenant-a", first["decision_id"])
    assert decision.execution.actor.id == "user-1"
    assert decision.execution.workload.id == "diagnosis-agent:diagnosis"
    assert decision.execution.attributes["thread_id"] == "diagnosis-thread-1"
    assert decision.policy_version == "v1"
    assert any(event.event_type == "action.submitted" and event.policy_decision_id == first["decision_id"]
               for event in await audits.list_recent("tenant-a"))


@pytest.mark.anyio
async def test_diagnosis_agent_tool_waits_for_approval_and_blocks_revoked_requester(ticket_setup, monkeypatch) -> None:
    from app.alerting import governed_ticket_tool as agent_action

    make, _, state, _, approval_service, decisions, _, _, _ = ticket_setup
    monkeypatch.setenv("PRISMOS_TRUSTED_GRAPH_CONTEXT", "required")
    monkeypatch.setenv("PRISMOS_GOVERNED_TICKET_TENANT", "tenant-a")
    monkeypatch.setenv("PRISMOS_GOVERNED_TICKET_ACTION", "ticket.create")
    monkeypatch.setattr(agent_action, "ticket_adapter", lambda _tenant: make("require_approval"))
    monkeypatch.setattr(agent_action, "PolicyDecisionRepository", lambda: decisions)
    scope = {"tenant_id": "tenant-a", "user_id": "user-1", "thread_id": "diagnosis-thread-2",
             "agent_name": "diagnosis", "incident_id": "incident-1"}
    selected_tool = agent_action.governed_ticket_tools(scope)[0]
    waiting = await selected_tool.ainvoke({})
    assert waiting["status"] == "awaiting_approval" and state.calls == []
    await approval_service.review("tenant-a", waiting["approval_id"], "admin-1", "approve")
    state.allowed = False
    with pytest.raises(PermissionError, match="authorized"):
        await selected_tool.ainvoke({})
    assert state.calls == []
    state.allowed = True
    submitted = await selected_tool.ainvoke({})
    assert submitted["status"] == "submitted" and len(state.calls) == 1


def test_diagnosis_agent_tool_requires_both_canary_switches(monkeypatch) -> None:
    from app.alerting.governed_ticket_tool import governed_ticket_tools

    scope = {"tenant_id": "tenant-a", "user_id": "user-1", "thread_id": "thread",
             "agent_name": "diagnosis", "incident_id": "incident-1"}
    monkeypatch.setenv("PRISMOS_GOVERNED_TICKET_TENANT", "tenant-a")
    monkeypatch.setenv("PRISMOS_GOVERNED_TICKET_ACTION", "ticket.create")
    assert governed_ticket_tools(scope) == []
    monkeypatch.setenv("PRISMOS_TRUSTED_GRAPH_CONTEXT", "required")
    assert [tool.name for tool in governed_ticket_tools(scope)] == ["create_governed_incident_ticket", "read_file"]
    assert governed_ticket_tools({**scope, "tenant_id": "tenant-b"}) == []
    monkeypatch.setenv("PRISMOS_GOVERNED_TICKET_ACTION", "off")
    assert governed_ticket_tools(scope) == []

@pytest.mark.anyio
async def test_diagnosis_card_status_reads_persisted_action_facts(ticket_setup, monkeypatch) -> None:
    from fastapi import HTTPException

    from app.gateway.routers import alerts
    from app.platform.approval import repository as approval_repository
    from app.platform.policy import repository as policy_repository
    from app.platform.submission import repository as submission_repository

    make, execution, state, _, _, _, _, _, incident = ticket_setup
    incident.thread_id = "status-thread"
    async with state.delivery._session_factory() as session:
        session.add(incident)
        await session.commit()
    monkeypatch.setenv("PRISMOS_TRUSTED_GRAPH_CONTEXT", "required")
    monkeypatch.setenv("PRISMOS_GOVERNED_TICKET_TENANT", "tenant-a")
    monkeypatch.setenv("PRISMOS_GOVERNED_TICKET_ACTION", "ticket.create")
    monkeypatch.setattr(alerts, "get_session_factory", lambda: state.delivery._session_factory)
    monkeypatch.setattr(approval_repository, "get_session_factory", lambda: state.delivery._session_factory)
    monkeypatch.setattr(policy_repository, "get_session_factory", lambda: state.delivery._session_factory)
    monkeypatch.setattr(submission_repository, "get_session_factory", lambda: state.delivery._session_factory)
    assert (await alerts._governed_ticket_status("incident-1", "tenant-a"))["status"] is None
    from app.alerting.governed_ticket_tool import ticket_request_id

    result = await make("allow").execute(execution, ticket_request_id("status-thread", "incident-1"),
                                         "incident-1", at=NOW)
    status = await alerts._governed_ticket_status("incident-1", "tenant-a")
    assert status["status"] == "submitted" and status["decision_id"] == result.decision_id
    assert status["actor_id"] == "user-1" and status["run_id"] == "run-1"
    assert status["policy_version"] == "v1" and status["ticket_id"] == "T-1"
    monkeypatch.setenv("PRISMOS_GOVERNED_TICKET_TENANT", "tenant-b")
    with pytest.raises(HTTPException) as error:
        await alerts._governed_ticket_status("incident-1", "tenant-b")
    monkeypatch.setenv("PRISMOS_GOVERNED_TICKET_TENANT", "tenant-a")
    assert error.value.status_code == 404
    monkeypatch.setenv("PRISMOS_GOVERNED_TICKET_ACTION", "off")
    assert await alerts._governed_ticket_status("incident-1", "tenant-a") == {"enabled": False, "status": None}


@pytest.mark.anyio
@pytest.mark.parametrize("native", [False, True])
async def test_diagnosis_read_file_records_policy_before_sandbox_read(ticket_setup, monkeypatch, native) -> None:
    from langchain.tools import ToolRuntime

    from app.alerting import governed_read_tool as read_action

    make, _, _, _, _, decisions, audits, _, _ = ticket_setup
    monkeypatch.setenv("PRISMOS_TRUSTED_GRAPH_CONTEXT", "required")
    monkeypatch.setenv("PRISMOS_GOVERNED_TICKET_TENANT", "tenant-a")
    monkeypatch.setenv("PRISMOS_GOVERNED_TICKET_ACTION", "ticket.create")
    adapter = make("allow")
    monkeypatch.setattr(read_action, "PolicyService", lambda: adapter._policy)
    monkeypatch.setattr(read_action, "PolicyDecisionRepository", lambda: decisions)
    monkeypatch.setattr(read_action, "AuditEventRepository", lambda: audits)

    async def member(_tenant, _user):
        return True

    monkeypatch.setattr(read_action, "active_requester", member)
    reads = []

    def sandbox_read(**kwargs):
        reads.append(kwargs["path"])
        return "file contents"

    monkeypatch.setattr(read_action.read_file_tool, "func", sandbox_read)
    scope = {"tenant_id": "tenant-a", "user_id": "user-1", "thread_id": "diagnosis-read-1",
             "agent_name": "diagnosis", "incident_id": "incident-1"}
    if native:
        scope["agent_id"] = "native-read-agent"
    selected = read_action.governed_read_file_tool(scope)
    runtime = ToolRuntime(state={}, context=scope, config={}, stream_writer=lambda _value: None,
                          tool_call_id="call-1", store=None)
    assert await selected.coroutine(runtime, "inspect logs", "/workspace/log.txt") == "file contents"
    assert reads == ["/workspace/log.txt"]
    request_id = "read-" + sha256(b"diagnosis-read-1:call-1").hexdigest()
    decision = await decisions.get_by_request("tenant-a", request_id)
    assert decision.action == "read_file" and decision.risk_class == "read_only"
    assert decision.verdict == "allow" and decision.execution.actor.id == "user-1"
    assert decision.execution.attributes.get("agent_id") == ("native-read-agent" if native else None)
    assert any(event.policy_decision_id == decision.decision_id and event.event_type == "action.policy_evaluated"
               for event in await audits.list_recent("tenant-a"))
    assert await selected.coroutine(runtime, "inspect logs", "/workspace/log.txt") == "file contents"
    assert len(reads) == 2
    assert sum(event.event_type == "action.read_result" for event in await audits.list_recent("tenant-a")) == 2
    assert all("file contents" not in event.model_dump_json() for event in await audits.list_recent("tenant-a"))
    wrong_runtime = ToolRuntime(state={}, context={**scope, "tenant_id": "tenant-b"}, config={},
                                stream_writer=lambda _value: None, tool_call_id="call-other", store=None)
    with pytest.raises(PermissionError, match="sandbox identity"):
        await selected.coroutine(wrong_runtime, "inspect logs", "/workspace/log.txt")
    if native:
        wrong_agent = ToolRuntime(state={}, context=scope | {"agent_id": "another-native-agent"}, config={},
                                  stream_writer=lambda _value: None, tool_call_id="call-agent-mismatch", store=None)
        with pytest.raises(PermissionError, match="sandbox identity"):
            await selected.coroutine(wrong_agent, "inspect logs", "/workspace/log.txt")
    with pytest.raises(ValueError, match="different Action context"):
        await selected.coroutine(runtime, "inspect logs", "/workspace/other.txt")
    assert len(reads) == 2


@pytest.mark.anyio
async def test_diagnosis_read_file_fails_closed_on_audit_failure(ticket_setup, monkeypatch) -> None:
    from langchain.tools import ToolRuntime

    from app.alerting import governed_read_tool as read_action

    make, _, _, _, _, decisions, audits, _, _ = ticket_setup
    monkeypatch.setenv("PRISMOS_TRUSTED_GRAPH_CONTEXT", "required")
    monkeypatch.setenv("PRISMOS_GOVERNED_TICKET_TENANT", "tenant-a")
    monkeypatch.setenv("PRISMOS_GOVERNED_TICKET_ACTION", "ticket.create")
    adapter = make("allow")
    monkeypatch.setattr(read_action, "PolicyService", lambda: adapter._policy)
    monkeypatch.setattr(read_action, "PolicyDecisionRepository", lambda: decisions)
    monkeypatch.setattr(read_action, "AuditEventRepository", lambda: audits)

    async def member(_tenant, _user):
        return True

    monkeypatch.setattr(read_action, "active_requester", member)
    reads = []
    monkeypatch.setattr(read_action.read_file_tool, "func", lambda **_kwargs: reads.append(True))

    async def failed_audit(*_args):
        raise RuntimeError("audit storage failed")

    monkeypatch.setattr(AuditEventRepository, "append_in_session", failed_audit)
    scope = {"tenant_id": "tenant-a", "user_id": "user-1", "thread_id": "diagnosis-read-2",
             "agent_name": "diagnosis", "incident_id": "incident-1"}
    selected = read_action.governed_read_file_tool(scope)
    runtime = ToolRuntime(state={}, context=scope, config={}, stream_writer=lambda _value: None,
                          tool_call_id="call-2", store=None)
    with pytest.raises(RuntimeError, match="audit storage"):
        await selected.coroutine(runtime, "inspect logs", "/workspace/log.txt")
    assert reads == []


@pytest.mark.anyio
async def test_diagnosis_read_file_denied_without_sandbox_access(ticket_setup, monkeypatch) -> None:
    from langchain.tools import ToolRuntime

    from app.alerting import governed_read_tool as read_action

    make, _, _, _, _, decisions, audits, _, _ = ticket_setup
    monkeypatch.setenv("PRISMOS_TRUSTED_GRAPH_CONTEXT", "required")
    monkeypatch.setenv("PRISMOS_GOVERNED_TICKET_TENANT", "tenant-a")
    monkeypatch.setenv("PRISMOS_GOVERNED_TICKET_ACTION", "ticket.create")
    adapter = make("allow")
    monkeypatch.setattr(read_action, "PolicyService", lambda: adapter._policy)
    monkeypatch.setattr(read_action, "PolicyDecisionRepository", lambda: decisions)
    monkeypatch.setattr(read_action, "AuditEventRepository", lambda: audits)
    configuration_type = read_action.PolicyConfiguration
    monkeypatch.setattr(read_action, "PolicyConfiguration", lambda **_kwargs: configuration_type(
        policy_id="read-test", version="v1",
        rules={"read_file": PolicyRule(risk_class="read_only", verdict="deny")},
    ))

    async def member(_tenant, _user):
        return True

    monkeypatch.setattr(read_action, "active_requester", member)
    reads = []
    monkeypatch.setattr(read_action.read_file_tool, "func", lambda **_kwargs: reads.append(True))
    scope = {"tenant_id": "tenant-a", "user_id": "user-1", "thread_id": "diagnosis-read-3",
             "agent_name": "diagnosis", "incident_id": "incident-1"}
    selected = read_action.governed_read_file_tool(scope)
    runtime = ToolRuntime(state={}, context=scope, config={}, stream_writer=lambda _value: None,
                          tool_call_id="call-3", store=None)
    with pytest.raises(PermissionError, match="denied"):
        await selected.coroutine(runtime, "inspect logs", "/workspace/log.txt")
    assert reads == []
    request_id = "read-" + sha256(b"diagnosis-read-3:call-3").hexdigest()
    decision = await decisions.get_by_request("tenant-a", request_id)
    assert decision.verdict == "deny"
    assert any(event.policy_decision_id == decision.decision_id and event.outcome == "denied"
               for event in await audits.list_recent("tenant-a"))


@pytest.mark.anyio
@pytest.mark.parametrize("first_native", [False, True])
async def test_existing_diagnosis_action_cannot_be_rebound_to_same_name_native_instance(ticket_setup, monkeypatch, first_native):
    from app.alerting import governed_ticket_tool as agent_action

    make, _, state, _, _, decisions, _, _, _ = ticket_setup
    monkeypatch.setenv("PRISMOS_TRUSTED_GRAPH_CONTEXT", "required")
    monkeypatch.setenv("PRISMOS_GOVERNED_TICKET_TENANT", "tenant-a")
    monkeypatch.setenv("PRISMOS_GOVERNED_TICKET_ACTION", "ticket.create")
    monkeypatch.setattr(agent_action, "ticket_adapter", lambda _tenant: make("allow"))
    monkeypatch.setattr(agent_action, "PolicyDecisionRepository", lambda: decisions)
    scope = {"tenant_id": "tenant-a", "user_id": "user-1", "thread_id": "same-name-thread", "agent_name": "collision-agent", "incident_id": "incident-1"}
    if first_native:
        scope["agent_id"] = "first-native-id"
    first = await agent_action.governed_ticket_tools(scope)[0].ainvoke({})
    assert first["status"] == "submitted" and len(state.calls) == 1
    chosen = scope | {"agent_id": "another-native-id"}
    with pytest.raises(PermissionError, match="identity changed"):
        await agent_action.governed_ticket_tools(chosen)[0].ainvoke({})
    assert len(state.calls) == 1
    decision = await decisions.get("tenant-a", first["decision_id"])
    assert decision.execution.attributes.get("agent_id") == ("first-native-id" if first_native else None)
