"""Exercise encrypted Source bindings through real HTTPX and durable approval facts."""

import asyncio
import logging
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import httpx
import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel import SQLModel, select
from sqlmodel.ext.asyncio.session import AsyncSession
from starlette.requests import Request

from app.alerting import governed_ticket, ticket_provider, ticket_secrets
from app.alerting.escalation import apply_escalation_actions, evaluate_escalation_rules
from app.alerting.legacy_audit_delivery import LegacyAuditDeliveryService
from app.alerting.ticket_secrets import TicketSecretRepository
from app.gateway.routers import alerts
from app.models.alerting import AlertRule, AlertSource, Incident, IncidentAction, IncidentSignalLink, RawAlert, Signal
from app.models.governance import PlatformActionSubmissionRecord, PlatformAuditEventRecord, PlatformPolicyDecisionRecord, PlatformTicketSecretRecord
from app.platform.approval.repository import ApprovalRepository
from app.platform.approval.service import ApprovalService
from app.platform.contracts import ExecutionEnvelope, IdentityRef
from app.platform.policy.evaluator import PolicyConfiguration, PolicyRule
from app.platform.policy.fact_writer import PolicyFactWriter
from app.platform.policy.repository import PolicyDecisionRepository
from app.platform.policy.service import PolicyService
from app.platform.submission.repository import ActionSubmissionRepository

pytestmark = pytest.mark.anyio
NOW = datetime(2026, 10, 9, 8, 0, tzinfo=UTC)
URL = "https://tickets.example/hook/private-path?token=private-url-value"
HEADER = "Bearer private-header-value"


@pytest.fixture
async def setup(tmp_path, monkeypatch):
    monkeypatch.setenv("DEERFLOW_SECRETS_ENCRYPTION_KEY", "test-encryption-key")
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'provider.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(SQLModel.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        session.add_all(
            [
                AlertSource(id="source-a", tenant_id="tenant-a", name="source"),
                AlertSource(id="source-a2", tenant_id="tenant-a", name="other-source"),
                Incident(id="incident-a", tenant_id="tenant-a", incident_key="INC-A", title="Alarm", first_seen_at=NOW, last_seen_at=NOW),
                RawAlert(id="raw-a", tenant_id="tenant-a", source_id="source-a", payload_hash="hash-a", received_at=NOW),
                Signal(id="signal-a", tenant_id="tenant-a", raw_alert_id="raw-a", fingerprint="fingerprint-a", title="Alarm signal"),
                IncidentSignalLink(id="link-a", tenant_id="tenant-a", incident_id="incident-a", signal_id="signal-a"),
            ]
        )
        await session.flush()
        ref = await TicketSecretRepository().create(session, "tenant-a", "source-a", URL, {"Authorization": HEADER})
        source = await session.get(AlertSource, "source-a")
        source.config_json = {"ticket": {"provider": "webhook", "secret_ref": ref.model_dump(mode="json")}}
        await session.commit()
    monkeypatch.setattr(governed_ticket, "get_session_factory", lambda: factory)
    monkeypatch.setattr(ticket_secrets, "get_session_factory", lambda: factory)
    state = SimpleNamespace(factory=factory, ref=ref, calls=[], allowed=True, sequence=[], timeout=False, response={"id": "T-1", "url": "https://portal.example/T-1"})
    # Instantiate this logger before client setup so its context filter is installed.
    core_logger = logging.getLogger("httpcore.http11")

    async def transport(request):
        state.calls.append(request)
        core_logger.debug("response headers %s", {"echo": HEADER})
        if state.timeout:
            raise httpx.ReadTimeout(URL, request=request)
        return httpx.Response(200, json=state.response)

    original_client = httpx.AsyncClient
    monkeypatch.setattr(ticket_provider.httpx, "AsyncClient", lambda **kwargs: original_client(transport=httpx.MockTransport(transport), **kwargs))

    async def permission(*args):
        return state.sequence.pop(0) if state.sequence else state.allowed

    async def membership(user, tenant):
        return SimpleNamespace(role="admin" if user == "admin-a" else "member") if state.allowed else None

    async def tenant(tenant_id):
        return object() if tenant_id == "tenant-a" else None

    state.decisions = PolicyDecisionRepository(factory)
    state.approvals = ApprovalRepository(factory)
    state.approval_service = ApprovalService(state.approvals, state.decisions, membership, tenant)
    state.submissions = ActionSubmissionRepository(factory)
    state.execution = ExecutionEnvelope(
        tenant_id="tenant-a",
        task_id="task-a",
        run_id="run-a",
        correlation_id="incident-a",
        workload=IdentityRef(kind="workload", id="diagnosis", tenant_id="tenant-a"),
        actor=IdentityRef(kind="user", id="user-a", tenant_id="tenant-a"),
        occurred_at=NOW,
    )

    def adapter(verdict="allow"):
        return governed_ticket.TicketActionAdapter(
            enabled_tenants=frozenset({"tenant-a"}),
            configuration=PolicyConfiguration(policy_id="test-policy", version="v1", rules={"ticket.create": PolicyRule(risk_class="side_effect", verdict=verdict)}),
            policy=PolicyService(PolicyFactWriter(factory), state.decisions),
            approvals=state.approvals,
            approval_service=state.approval_service,
            submissions=state.submissions,
            deliveries=LegacyAuditDeliveryService(factory, gateway_writer=lambda event: None),
            check_permission=permission,
        )

    state.adapter = adapter
    yield state
    await engine.dispose()


async def assert_no_persisted_material(state):
    async with state.factory() as session:
        for model in (PlatformAuditEventRecord, PlatformPolicyDecisionRecord, PlatformActionSubmissionRecord, Incident, IncidentAction, AlertSource):
            for row in (await session.exec(select(model))).all():
                serialized = row.model_dump_json()
                for private in ("private-path", "private-url-value", "private-header-value"):
                    assert private not in serialized


async def test_provider_injects_only_locally_and_suppresses_http_logs(setup, caplog):
    state = setup
    target = await governed_ticket.resolve_ticket_target("tenant-a", "incident-a")
    saved = deepcopy(target.config)
    caplog.set_level(logging.DEBUG, logger="httpx")
    caplog.set_level(logging.DEBUG, logger="httpcore.http11")
    result = await ticket_provider.create_ticket(target.incident, target.config, target.signals, source_id=target.source_id, idempotency_key="stable-key")
    assert result.ticket_id == "T-1" and target.config == saved
    request = state.calls[0]
    assert str(request.url) == URL and request.headers["Authorization"] == HEADER
    assert request.headers["Idempotency-Key"] == "stable-key"
    assert "private-header-value" not in request.content.decode()
    assert "private-url-value" not in caplog.text and "private-header-value" not in caplog.text
    # Unrelated traffic retains its message after the private context exits.
    logging.getLogger("httpx").info("ordinary-request")
    assert "ordinary-request" in caplog.text
    await assert_no_persisted_material(state)


@pytest.mark.parametrize("change", ["wrong-tenant", "wrong-source", "missing-source", "malformed", "inline"])
async def test_provider_rejects_invalid_reference_before_network(setup, change):
    state = setup
    target = await governed_ticket.resolve_ticket_target("tenant-a", "incident-a")
    config = deepcopy(target.config)
    source = target.source_id
    if change == "wrong-tenant":
        config["secret_ref"]["tenant_id"] = "tenant-b"
    elif change == "wrong-source":
        source = "source-a2"
    elif change == "missing-source":
        source = None
    elif change == "malformed":
        config["secret_ref"] = {"secret_value": HEADER}
    else:
        config["headers"] = {"Authorization": HEADER}
    with pytest.raises((ValueError, PermissionError)) as error:
        await ticket_provider.create_ticket(target.incident, config, source_id=source)
    assert "private-header-value" not in str(error.value) and not state.calls


async def test_governed_reference_submits_once_and_never_persists_material(setup):
    state = setup
    adapter = state.adapter()
    first = await adapter.execute(state.execution, "request-a", "incident-a", at=NOW)
    second = await adapter.execute(state.execution, "request-a", "incident-a", at=NOW + timedelta(seconds=1))
    assert first.status == second.status == "submitted" and len(state.calls) == 1
    assert state.calls[0].headers["Idempotency-Key"] == first.idempotency_key
    await assert_no_persisted_material(state)


@pytest.mark.parametrize("mutation", ["disable", "rotate", "missing-key", "wrong-key", "bad-ciphertext", "revoke", "source-disabled", "template"])
async def test_approved_request_rechecks_reference_before_consuming_or_claiming(setup, monkeypatch, mutation):
    state = setup
    adapter = state.adapter("require_approval")
    waiting = await adapter.execute(state.execution, "request-a", "incident-a", at=NOW)
    assert waiting.status == "awaiting_approval" and not state.calls
    await state.approval_service.review("tenant-a", waiting.approval_id, "admin-a", "approve", at=NOW + timedelta(seconds=1))
    async with state.factory() as session:
        source = await session.get(AlertSource, "source-a")
        if mutation == "disable":
            await TicketSecretRepository().disable(session, "tenant-a", "source-a", state.ref)
        elif mutation == "rotate":
            new = await TicketSecretRepository().create(session, "tenant-a", "source-a", URL, {"Authorization": HEADER})
            await TicketSecretRepository().disable(session, "tenant-a", "source-a", state.ref)
            source.config_json = {"ticket": {"provider": "webhook", "secret_ref": new.model_dump(mode="json")}}
        elif mutation == "missing-key":
            monkeypatch.delenv("DEERFLOW_SECRETS_ENCRYPTION_KEY")
        elif mutation == "wrong-key":
            monkeypatch.setenv("DEERFLOW_SECRETS_ENCRYPTION_KEY", "wrong-key")
        elif mutation == "bad-ciphertext":
            record = await session.get(PlatformTicketSecretRecord, state.ref.id)
            record.encrypted_payload = "enc:v1:broken"
        elif mutation == "revoke":
            state.allowed = False
        elif mutation == "source-disabled":
            source.status = "disabled"
        else:
            config = deepcopy(source.config_json)
            config["ticket"]["template"] = {"title": "Changed after approval"}
            source.config_json = config
        await session.commit()
    with pytest.raises((ValueError, PermissionError)):
        await adapter.execute(state.execution, "request-a", "incident-a", at=NOW + timedelta(seconds=2))
    assert (await state.approvals.get("tenant-a", waiting.approval_id))[0].status == "approved"
    assert await state.submissions.get("tenant-a", waiting.decision_id) is None
    assert not state.calls


async def test_rechecks_permission_after_claim_before_network(setup):
    state = setup
    state.sequence = [True, True, False]
    outcome = await state.adapter().execute(state.execution, "request-a", "incident-a", at=NOW)
    assert outcome.status == "unknown" and not state.calls
    assert (await state.submissions.get("tenant-a", outcome.decision_id)).status == "unknown"
    await assert_no_persisted_material(state)


async def test_disabled_after_preflight_is_rechecked_at_provider_boundary(setup, monkeypatch):
    state = setup
    original = TicketSecretRepository.read
    reads = 0

    async def read(repository, session, tenant, source, ref):
        nonlocal reads
        reads += 1
        if reads == 2:
            async with state.factory() as writer:
                await repository.disable(writer, tenant, source, ref)
                await writer.commit()
        return await original(repository, session, tenant, source, ref)

    monkeypatch.setattr(TicketSecretRepository, "read", read)
    adapter = state.adapter()
    first = await adapter.execute(state.execution, "request-a", "incident-a", at=NOW)
    assert reads == 2 and first.status == "unknown" and not state.calls
    repeated = await adapter.execute(state.execution, "request-a", "incident-a", at=NOW + timedelta(seconds=1))
    assert repeated.status == "unknown" and not state.calls


async def test_reference_timeout_does_not_resend_or_expose_request_in_error(setup, caplog):
    state = setup
    state.timeout = True
    adapter = state.adapter()
    first = await adapter.execute(state.execution, "request-a", "incident-a", at=NOW)
    repeated = await adapter.execute(state.execution, "request-a", "incident-a", at=NOW + timedelta(seconds=1))
    assert first.status == repeated.status == "unknown" and len(state.calls) == 1
    assert "private-url-value" not in caplog.text
    await assert_no_persisted_material(state)


@pytest.mark.parametrize("echo", ["private-header-value", "private-url-value", "private-path"])
async def test_provider_drops_credentials_echoed_in_returned_ticket_fields(setup, echo):
    state = setup
    state.response = {"id": echo, "url": URL}
    outcome = await state.adapter().execute(state.execution, "request-a", "incident-a", at=NOW)
    assert outcome.status == "submitted" and outcome.ticket_id == "inc-INC-A"
    await assert_no_persisted_material(state)


async def test_manual_route_uses_same_reference_and_source_scope(setup):
    state = setup
    request = Request({"type": "http"})
    request.state.tenant_id = "tenant-a"
    request.state.user_id = "user-a"
    async with state.factory() as session:
        result = await alerts.create_incident_ticket("incident-a", request=request, session=session)
        assert result["ticket_id"] == "T-1"
    assert len(state.calls) == 1
    await assert_no_persisted_material(state)


async def test_rule_auto_ticket_uses_provider_and_skips_existing_ticket(setup):
    state = setup
    async with state.factory() as session:
        session.add(AlertRule(id="rule-a", tenant_id="tenant-a", name="auto-ticket", rule_type="escalation", action_json={"action": "auto_ticket"}))
        await session.commit()
        incident = await session.get(Incident, "incident-a")
        rules = await evaluate_escalation_rules(incident, session)
        assert len(rules) == 1
        result = await apply_escalation_actions(incident, rules, session)
        assert result[0]["ticket_id"] == "T-1"
        assert await apply_escalation_actions(incident, rules, session) == []
    assert len(state.calls) == 1
    await assert_no_persisted_material(state)


async def test_concurrent_governed_requests_claim_only_one_submission(setup):
    state = setup
    adapter = state.adapter()
    results = await asyncio.gather(*(adapter.execute(state.execution, "request-a", "incident-a", at=NOW) for _ in range(2)))
    assert len(state.calls) == 1 and "submitted" in {result.status for result in results}
    final = await adapter.execute(state.execution, "request-a", "incident-a", at=NOW + timedelta(seconds=1))
    assert final.status == "submitted" and len(state.calls) == 1
