from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from app.alerting.governed_ticket import TicketActionAdapter, TicketTarget
from app.alerting.ticket_provider import TicketResult
from app.models import alerting as _alert_models  # noqa: F401
from app.models import governance as _governance_models  # noqa: F401
from app.models.alerting import Incident
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
        config={"provider": "webhook", "webhook_url": "https://tickets.example/create",
                "headers": {"Authorization": "Bearer private-secret"}},
        signals=[],
    )
    state = SimpleNamespace(allowed=True, allowed_sequence=[], calls=[], linked=[])

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
            send_ticket=sender, link_ticket=linker,
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
    assert "private-secret" not in (await audits.list_recent("tenant-a"))[0].model_dump_json()
    assert "private-secret" not in (await decisions.get_by_request("tenant-a", "request-1")).model_dump_json()


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
    make, execution, state, _, _, _, _, submissions, _ = ticket_setup

    async def timeout(*_args, **kwargs):
        state.calls.append(kwargs["idempotency_key"])
        raise TimeoutError("remote result unknown")

    adapter = make("allow", sender=timeout)
    first = await adapter.execute(execution, "request-1", "incident-1", at=NOW)
    second = await adapter.execute(execution, "request-1", "incident-1", at=NOW + timedelta(seconds=1))
    assert first.status == second.status == "unknown"
    assert len(state.calls) == 1
    assert (await submissions.get("tenant-a", first.decision_id)).status == "unknown"


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
