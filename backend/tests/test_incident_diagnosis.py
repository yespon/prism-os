"""Tests for incident deep diagnosis API endpoint."""

from __future__ import annotations

import asyncio
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.pool import NullPool
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.agents import CustomAgent
from app.models.alerting import AlertSource, Incident, IncidentSignalLink, RawAlert, Signal
from deerflow.database.models import Tenant, TenantMembership

# ---------------------------------------------------------------------------
# Engine & Session Fixtures
# ---------------------------------------------------------------------------

def _make_test_engine(path=None) -> AsyncEngine:
    if url := os.environ.get('PRISMOS_SKILL_TEST_DB_URL'):
        return create_async_engine(url, poolclass=NullPool)
    return create_async_engine(
        f"sqlite+aiosqlite:///{path}" if path else "sqlite+aiosqlite://",
        echo=False,
        connect_args={"check_same_thread": False},
    )

async def _create_tables(engine: AsyncEngine) -> None:
    # Ensure all tables are registered

    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

async def _drop_tables(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.drop_all)

@pytest.fixture()
def test_session_factory(tmp_path, native_identity):
    native_identity("user-a")
    # Fresh delivery checks require independent transactions; a single
    # in-memory connection can roll back a concurrent background writer.
    engine = _make_test_engine(tmp_path / "diagnosis.db")
    asyncio.run(_create_tables(engine))

    from sqlalchemy.ext.asyncio import async_sessionmaker
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    yield factory

    asyncio.run(_drop_tables(engine))
    asyncio.run(engine.dispose())

# ---------------------------------------------------------------------------
# Test App Setup
# ---------------------------------------------------------------------------

def _make_test_app(session_factory, default_user_id: str | None = "user-a"):
    from fastapi import FastAPI, Request

    from app.gateway.routers.alerts import router

    app = FastAPI()

    @app.middleware("http")
    async def inject_test_user(request: Request, call_next):
        header_user_id = request.headers.get("x-user-id")
        request.state.user_id = header_user_id if header_user_id is not None else default_user_id
        request.state.tenant_id = request.headers.get("x-tenant-id", "tenant-a")
        request.state.tenant_role = request.headers.get("x-tenant-role", "tenant_member")
        return await call_next(request)

    async def override_get_session():
        async with session_factory() as session:
            yield session

    from deerflow.database.session import get_session
    app.dependency_overrides[get_session] = override_get_session
    app.include_router(router)
    return app

@pytest.fixture()
def client(test_session_factory):
    app = _make_test_app(test_session_factory)
    with TestClient(app) as client:
        yield client

# ---------------------------------------------------------------------------
# LangGraph Mocking
# ---------------------------------------------------------------------------

class MockStreamChunk:
    def __init__(self, event: str, data: any):
        self.event = event
        self.data = data

async def mock_runs_stream(*args, **kwargs):
    # Yield a few mock tokens to simulate LangGraph streaming
    yield MockStreamChunk(
        "messages-tuple",
        [("ai", {"type": "ai", "content": "Mock diagnosis token 1"})]
    )
    yield MockStreamChunk(
        "messages-tuple",
        [("ai", {"type": "ai", "content": "Mock diagnosis token 2"})]
    )

@pytest.fixture()
def mock_langgraph():
    mock_client = MagicMock()
    mock_client.threads.create = AsyncMock(return_value={"thread_id": "mock-thread-xyz"})
    mock_client.runs.stream = mock_runs_stream

    with patch("langgraph_sdk.get_client", return_value=mock_client):
        yield mock_client

# ---------------------------------------------------------------------------
# Test Cases
# ---------------------------------------------------------------------------

class TestIncidentDiagnosis:
    async def _setup_data(self, session_factory):
        async with session_factory() as session:
            session.add(Tenant(id="tenant-a", name="A", slug="a"))
            session.add(TenantMembership(tenant_id="tenant-a", user_id="user-a", role="tenant_member"))
            # 1. Create SRE custom agents
            private_agent = CustomAgent(
                id="agent-private",
                tenant_id="tenant-a",
                user_id="user-a",
                name="private-diagnoser",
                system_prompt="Private agent system prompt",
            )
            shared_agent = CustomAgent(
                id="agent-shared",
                tenant_id="tenant-a",
                user_id="tenant-shared",
                name="shared-diagnoser",
                system_prompt="Shared agent system prompt",
            )
            other_agent = CustomAgent(
                id="agent-other",
                tenant_id="tenant-a",
                user_id="user-other",
                name="other-diagnoser",
                system_prompt="Other agent system prompt",
            )
            cross_tenant_agent = CustomAgent(
                id="agent-tenant-b",
                tenant_id="tenant-b",
                user_id="tenant-shared",
                name="tenant-b-diagnoser",
                system_prompt="Other tenant agent system prompt",
            )

            # 2. Create Alert Source
            source = AlertSource(
                id="source-1",
                tenant_id="tenant-a",
                name="Prometheus",
                type="webhook",
                status="active",
                config_json={
                    "analysis_trigger": {
                        "mode": "conditional",
                        "diagnosis_agent_id": "agent-shared",
                    }
                },
            )

            # 3. Create Incident
            incident = Incident(
                id="incident-1",
                tenant_id="tenant-a",
                incident_key="INC-1",
                title="Service high error rate",
                severity="critical",
                status="firing",
            )

            # 4. Create Signal & Links
            signal = Signal(
                id="sig-1",
                tenant_id="tenant-a",
                raw_alert_id="raw-1",
                source="prometheus",
                severity="critical",
                status="firing",
                title="High response time",
                fingerprint="finger-1",
            )
            raw_alert = RawAlert(
                id="raw-1",
                tenant_id="tenant-a",
                source_id="source-1",
                payload_hash="mock_payload_hash",
                raw_payload_json={},
            )
            link = IncidentSignalLink(
                id="link-1",
                tenant_id="tenant-a",
                incident_id="incident-1",
                signal_id="sig-1",
            )

            session.add_all([private_agent, shared_agent, other_agent, cross_tenant_agent, source, incident, signal, raw_alert, link])
            await session.commit()

    def test_diagnose_default_agent(self, test_session_factory, client, mock_langgraph):
        asyncio.run(self._setup_data(test_session_factory))

        # Patch get_session_factory so the SSE write session uses test DB
        with patch("app.gateway.routers.alerts.get_session_factory", return_value=test_session_factory):
            response = client.post(
                "/api/incidents/incident-1/diagnose",
                headers={"x-user-id": "user-a", "x-tenant-id": "tenant-a"},
            )
            assert response.status_code == 200
            # Read streaming response chunks
            chunks = response.text.split("\n\n")
            assert any("thread" in chunk and "mock-thread-xyz" in chunk for chunk in chunks)
            # Check for token messages (new SSE format)
            assert any("token" in chunk and "Mock diagnosis token" in chunk for chunk in chunks)

            # Verify Incident in DB has completed status and thread/agent linked
            async def verify_db():
                async with test_session_factory() as session:
                    inc = await session.get(Incident, "incident-1")
                    assert inc.diagnosis_status == "completed"
                    assert inc.agent_id == "agent-shared"
                    # thread_id is cleared after completion in new code
            asyncio.run(verify_db())

    def test_diagnose_custom_private_agent(self, test_session_factory, client, mock_langgraph):
        asyncio.run(self._setup_data(test_session_factory))

        with patch("app.gateway.routers.alerts.get_session_factory", return_value=test_session_factory):
            response = client.post(
                "/api/incidents/incident-1/diagnose?agent_id=agent-private",
                headers={"x-user-id": "user-a", "x-tenant-id": "tenant-a"},
            )
            assert response.status_code == 200
            chunks = response.text.split("\n\n")
            assert any("thread" in chunk and "mock-thread-xyz" in chunk for chunk in chunks)

            async def verify_db():
                async with test_session_factory() as session:
                    inc = await session.get(Incident, "incident-1")
                    assert inc.diagnosis_status == "completed"
                    assert inc.agent_id == "agent-private"
                    # thread_id is cleared after completion in new code
            asyncio.run(verify_db())

    def test_diagnose_custom_shared_agent(self, test_session_factory, client, mock_langgraph):
        asyncio.run(self._setup_data(test_session_factory))

        with patch("app.gateway.routers.alerts.get_session_factory", return_value=test_session_factory):
            response = client.post(
                "/api/incidents/incident-1/diagnose?agent_id=agent-shared",
                headers={"x-user-id": "user-a", "x-tenant-id": "tenant-a"},
            )
            assert response.status_code == 200
            chunks = response.text.split("\n\n")
            assert any("thread" in chunk and "mock-thread-xyz" in chunk for chunk in chunks)

            async def verify_db():
                async with test_session_factory() as session:
                    inc = await session.get(Incident, "incident-1")
                    assert inc.diagnosis_status == "completed"
                    assert inc.agent_id == "agent-shared"
            asyncio.run(verify_db())

    def test_diagnose_permission_denied_other_user_agent(self, test_session_factory, client, mock_langgraph):
        asyncio.run(self._setup_data(test_session_factory))

        with patch("app.gateway.routers.alerts.get_session_factory", return_value=test_session_factory):
            response = client.post(
                "/api/incidents/incident-1/diagnose?agent_id=agent-other",
                headers={"x-user-id": "user-a", "x-tenant-id": "tenant-a"},
            )
            # Should return 400 Bad Request / Permission Denied
            assert response.status_code == 400
            assert "permission denied" in response.json()["detail"]

    def test_diagnose_cross_tenant_agent_is_rejected_before_run(self, test_session_factory, client, mock_langgraph):
        asyncio.run(self._setup_data(test_session_factory))

        response = client.post(
            "/api/incidents/incident-1/diagnose?agent_id=agent-tenant-b",
            headers={"x-user-id": "user-a", "x-tenant-id": "tenant-a"},
        )
        assert response.status_code == 400
        mock_langgraph.threads.create.assert_not_awaited()

    def test_diagnose_disabled_agent_is_rejected_before_run(self, test_session_factory, client, mock_langgraph):
        asyncio.run(self._setup_data(test_session_factory))

        async def disable_agent():
            async with test_session_factory() as session:
                agent = await session.get(CustomAgent, "agent-shared")
                agent.enabled = False
                session.add(agent)
                await session.commit()

        asyncio.run(disable_agent())

        response = client.post(
            "/api/incidents/incident-1/diagnose",
            headers={"x-user-id": "user-a", "x-tenant-id": "tenant-a"},
        )
        assert response.status_code == 400
        assert "not found or permission denied" in response.json()["detail"]
        mock_langgraph.threads.create.assert_not_awaited()

    def test_diagnose_stream_failure_handling(self, test_session_factory, client, mock_langgraph):
        asyncio.run(self._setup_data(test_session_factory))

        # Force runs.stream to raise an Exception
        async def failing_stream(*args, **kwargs):
            yield ("messages-tuple", MagicMock(content="Token before fail"))
            raise RuntimeError("LangGraph connection failed")

        mock_langgraph.runs.stream = failing_stream

        with patch("app.gateway.routers.alerts.get_session_factory", return_value=test_session_factory):
            response = client.post(
                "/api/incidents/incident-1/diagnose",
                headers={"x-user-id": "user-a", "x-tenant-id": "tenant-a"},
            )
            assert response.status_code == 200
            chunks = response.text.split("\n\n")
            # AG-UI protocol uses RUN_ERROR event type
            assert any("RUN_ERROR" in chunk and "LangGraph connection failed" in chunk for chunk in chunks)

            # Verify Incident in DB has failed status
            async def verify_db():
                async with test_session_factory() as session:
                    inc = await session.get(Incident, "incident-1")
                    assert inc.diagnosis_status == "failed"
            asyncio.run(verify_db())


def test_authenticated_diagnosis_stream_invokes_scoped_governed_tool(
    test_session_factory, client, mock_langgraph, monkeypatch,
) -> None:
    """Gateway diagnosis -> one-use graph scope -> Agent Tool -> Policy/Provider."""

    from app.alerting import governed_ticket_tool as agent_action
    from app.alerting.governed_ticket import TicketActionAdapter, TicketTarget
    from app.alerting.legacy_audit_delivery import LegacyAuditDeliveryService
    from app.alerting.ticket_provider import TicketResult
    from app.models import governance as _governance_models  # noqa: F401
    from app.platform.audit.repository import AuditEventRepository
    from app.platform.execution import trust
    from app.platform.policy.evaluator import PolicyConfiguration, PolicyRule
    from app.platform.policy.fact_writer import PolicyFactWriter
    from app.platform.policy.repository import PolicyDecisionRepository
    from app.platform.policy.service import PolicyService
    from app.platform.submission.repository import ActionSubmissionRepository

    asyncio.run(TestIncidentDiagnosis()._setup_data(test_session_factory))
    monkeypatch.setenv("PRISMOS_TRUSTED_GRAPH_CONTEXT", "required")
    monkeypatch.setenv("PRISMOS_GOVERNED_TICKET_TENANT", "tenant-a")
    monkeypatch.setenv("PRISMOS_GOVERNED_TICKET_ACTION", "ticket.create")
    monkeypatch.setattr(trust, "get_session_factory", lambda: test_session_factory)
    decisions = PolicyDecisionRepository(test_session_factory)
    submissions = ActionSubmissionRepository(test_session_factory)
    sent = []
    observed = []

    async def resolve(_tenant, incident_id):
        async with test_session_factory() as session:
            incident = await session.get(Incident, incident_id)
        return TicketTarget(incident, {"provider": "webhook", "webhook_url": "https://tickets.example/create"}, [])

    async def send(_incident, _config, _signals, *, idempotency_key):
        sent.append(idempotency_key)
        return TicketResult(ticket_id="GOLDEN-1", ticket_url="https://tickets.example/GOLDEN-1", provider="webhook")

    async def link(_tenant, _incident, _result):
        return None

    adapter = TicketActionAdapter(
        enabled_tenants=frozenset({"tenant-a"}),
        configuration=PolicyConfiguration(policy_id="golden-ticket", version="v1",
            rules={"ticket.create": PolicyRule(risk_class="side_effect", verdict="allow")}),
        policy=PolicyService(PolicyFactWriter(test_session_factory), decisions),
        submissions=submissions,
        deliveries=LegacyAuditDeliveryService(test_session_factory, gateway_writer=lambda _event: None),
        resolve_target=resolve, check_permission=lambda _tenant, _user: asyncio.sleep(0, result=True),
        send_ticket=send, link_ticket=link,
    )
    monkeypatch.setattr(agent_action, "ticket_adapter", lambda _tenant: adapter)
    monkeypatch.setattr(agent_action, "PolicyDecisionRepository", lambda: decisions)

    async def graph_stream(thread_id, _assistant, *, context, **_kwargs):
        from app.runtime_adapters import verify_native_selection
        selected = await trust.ExecutionCapabilityRepository(test_session_factory, native_selection_validator=verify_native_selection).consume(
            context["prismos_execution_capability"], context["tenant_id"], context["user_id"],
            thread_id, context["agent_name"], include_selection=True,
        )
        incident_id = selected["incident_id"]
        assert incident_id == "incident-1" and selected["agent_id"] == "agent-shared"
        scope = {"tenant_id": context["tenant_id"], "user_id": context["user_id"],
                 "thread_id": thread_id, "agent_name": context["agent_name"], "incident_id": incident_id, "agent_id": selected["agent_id"]}
        outcome = await agent_action.governed_ticket_tools(scope)[0].ainvoke({})
        observed.append(outcome)
        yield MockStreamChunk("metadata", {})

    mock_langgraph.runs.stream = graph_stream
    with patch("app.gateway.routers.alerts.get_session_factory", return_value=test_session_factory):
        response = client.post("/api/incidents/incident-1/diagnose",
            headers={"x-user-id": "user-a", "x-tenant-id": "tenant-a"})
    assert response.status_code == 200
    assert observed[0]["status"] == "submitted" and observed[0]["ticket_id"] == "GOLDEN-1"
    assert len(sent) == 1

    async def verify_facts():
        decision = await decisions.get("tenant-a", observed[0]["decision_id"])
        assert decision.execution.actor.id == "user-a"
        assert decision.execution.workload.id == "diagnosis-agent:shared-diagnoser"
        assert decision.execution.attributes["agent_id"] == "agent-shared"
        assert decision.execution.run_id
        assert (await submissions.get("tenant-a", decision.decision_id)).status == "submitted"
        assert any(event.event_type == "action.submitted" for event in
                   await AuditEventRepository(test_session_factory).list_recent("tenant-a"))
    asyncio.run(verify_facts())

    # Real durable native decisions must survive the HTTP resume projection.
    # Only the server-stored selection may be restored, even if a body is forged.
    from app.platform.approval import repository as approval_repository
    from app.platform.policy import repository as policy_repository
    from app.platform.submission import repository as submission_repository

    for repository in (approval_repository, policy_repository, submission_repository):
        monkeypatch.setattr(repository, "get_session_factory", lambda: test_session_factory)
    async def finish_diagnosis():
        async with test_session_factory() as session:
            incident = await session.get(Incident, "incident-1")
            incident.diagnosis_result = "Completed diagnosis after the Tool returned"
            await session.commit()
    asyncio.run(finish_diagnosis())
    with patch("app.gateway.routers.alerts.get_session_factory", return_value=test_session_factory):
        resumed = client.post("/api/incidents/incident-1/governed-ticket/resume",
            headers={"x-user-id": "user-a", "x-tenant-id": "tenant-a"},
            json={"agent_id": "agent-private", "diagnosis_source_id": "forged-source"})
        assert resumed.status_code == 200
        assert resumed.json()["status"] == "submitted" and len(sent) == 1

        async def replace_selection():
            async with test_session_factory() as session:
                incident = await session.get(Incident, "incident-1")
                incident.agent_id = "agent-private"
                await session.commit()
        asyncio.run(replace_selection())
        changed = client.post("/api/incidents/incident-1/governed-ticket/resume",
            headers={"x-user-id": "user-a", "x-tenant-id": "tenant-a"})
        assert changed.status_code == 409 and len(sent) == 1


def test_diagnosis_stream_releases_preflight_resource_transaction(client, mock_langgraph, test_session_factory, monkeypatch):
    from sqlmodel import select

    from app.integrations import agent_skill_references
    from deerflow.database.models import TenantSkill

    asyncio.run(TestIncidentDiagnosis()._setup_data(test_session_factory))

    async def resource():
        async with test_session_factory() as session:
            session.add(TenantSkill(tenant_id="tenant-a", user_id="__tenant_shared_skill__:tenant-a", name="transaction-probe", category="custom", enabled=False))
            await session.commit()
    asyncio.run(resource())
    sessions = []
    observed = []

    async def lock_selected_resource(session, *_args, **_kwargs):
        await session.exec(select(TenantSkill).where(TenantSkill.tenant_id == "tenant-a", TenantSkill.name == "transaction-probe").with_for_update())
        sessions.append(session)
        return None

    async def create_thread(**_kwargs):
        observed.append(not sessions[0].in_transaction())
        async with test_session_factory() as session:
            # PostgreSQL must permit an independent worker to acquire this row now.
            await session.exec(select(TenantSkill).where(TenantSkill.tenant_id == "tenant-a", TenantSkill.name == "transaction-probe").with_for_update(nowait=True))
        return {"thread_id": "mock-thread-xyz"}

    monkeypatch.setattr(agent_skill_references, "current_skill_prompt", lock_selected_resource)
    mock_langgraph.threads.create.side_effect = create_thread
    with patch("app.gateway.routers.alerts.get_session_factory", return_value=test_session_factory):
        response = client.post("/api/incidents/incident-1/diagnose")
    assert response.status_code == 200
    assert observed == [True]
