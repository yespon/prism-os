"""Protected source/incident authority at reads and actual scoped OS commands."""

import asyncio
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from sqlalchemy import select
from test_skill_member_tools import configured as configured_fixture
from test_skill_member_tools import scoped_client  # noqa: F401
from test_skill_reference_transactions import durable_sqlite  # noqa: F401
from test_skill_scoped_commands import command_runtime as owned_command_fixture
from test_skill_scoped_commands import run, selected_runtime  # noqa: F401

from app.alerting import diagnosis_authorization
from app.models.alerting import AlertSource, Incident
from deerflow.database.models import TenantMembership
from deerflow.sandbox import tools

configured = configured_fixture
command_runtime = owned_command_fixture


@pytest.fixture
def source_runtime(command_runtime, configured):
    factory, root, agent, calls, runtime, sandbox = command_runtime
    http, _, _, resources = configured
    current = http.get("/api/agents/member-agent").json()
    changed = http.put(
        "/api/agents/member-agent",
        headers={"x-tenant-role": "tenant_admin"},
        json={
            "is_shared": True,
            "skill_binding_mode": "selected",
            "skill_resources": [resources["tenant"]],
            "expected_agent_id": agent,
            "expected_revision": current["revision"],
        },
    )
    assert changed.status_code == 200, changed.text
    (root / "custom/tenant-a/collision/authority.txt").write_text("CURRENT SOURCE AUTHORIZED RESOURCE")

    async def seed():
        async with factory() as session:
            config = await diagnosis_authorization.configure(
                session,
                "tenant-a",
                "user-a",
                {
                    "analysis_trigger": {"mode": "conditional", "conditions": {"severity": ["critical"]}, "diagnosis_agent_id": agent},
                },
                confirm=True,
            )
            session.add(AlertSource(id="live-source", tenant_id="tenant-a", name="live source", config_json=config, created_by="user-a"))
            session.add(Incident(id="live-incident", tenant_id="tenant-a", incident_key="LIVE-INCIDENT", severity="critical"))
            await session.commit()
            return diagnosis_authorization.revision(config)

    runtime.context.update(diagnosis_source_id="live-source", diagnosis_source_revision=asyncio.run(seed()), diagnosis_incident_id="live-incident")
    return factory, root, agent, calls, runtime, sandbox


def alter(source_runtime, change):
    factory = source_runtime[0]

    async def apply():
        async with factory() as session:
            if change == "source":
                row = await session.get(AlertSource, "live-source")
                row.status = "disabled"
            elif change == "revision":
                row = await session.get(AlertSource, "live-source")
                config = dict(row.config_json)
                trigger = dict(config["analysis_trigger"])
                trigger["model"] = "changed"
                config["analysis_trigger"] = trigger
                row.config_json = config
            elif change == "role":
                row = (await session.exec(select(TenantMembership))).scalars().one()
                row.role = "tenant_member"
            else:
                row = await session.get(Incident, "live-incident")
                if change == "deleted-incident":
                    await session.delete(row)
                    await session.commit()
                    return
                if change == "cancel-request":
                    row.diagnosis_status = "failed"
                    row.diagnosis_error = "cancel_requested: interruption unknown"
                elif change == "replaced-thread":
                    row.thread_id = "replacement-thread"
                else:
                    row.severity = "warning"
            session.add(row)
            await session.commit()

    asyncio.run(apply())


@pytest.mark.parametrize("change", ["source", "revision", "role", "severity", "deleted-incident", "missing-context", "cancel-request", "replaced-thread"])
def test_selected_member_read_checks_protected_source_and_incident_at_use(source_runtime, change):
    _, _, _, calls, runtime, _ = source_runtime
    path = "/mnt/skills/custom/tenant-a/collision/authority.txt"
    assert "CURRENT SOURCE AUTHORIZED RESOURCE" in tools.read_file_tool.func(runtime, "Read authorized diagnosis resource", path)
    if change == "missing-context":
        runtime.context.pop("diagnosis_incident_id")
    else:
        alter(source_runtime, change)
    result = tools.read_file_tool.func(runtime, "Read after source condition change", path)
    assert result.startswith("Error:") and "AUTHORIZED RESOURCE" not in result
    assert calls == []


@pytest.mark.parametrize("change", ["source", "role", "severity"])
def test_source_condition_change_stops_actual_command_and_discards_unconfirmed_output(source_runtime, change):
    _, _, _, _, runtime, _ = source_runtime
    # Initial permitted execution proves these are current authorized facts.
    assert "CURRENT SOURCE AUTHORIZED RESOURCE" in run(runtime, "from pathlib import Path; print(Path('/mnt/skills/custom/tenant-a/collision/authority.txt').read_text())")
    output = Path(runtime.state["thread_data"]["outputs_path"])
    code = "import time; from pathlib import Path; Path('/mnt/user-data/outputs/started').write_text('started'); print('UNCONFIRMED OUTPUT', flush=True); time.sleep(3); Path('/mnt/user-data/outputs/late').write_text('LATE EFFECT')"
    with ThreadPoolExecutor(max_workers=1) as pool:
        pending = pool.submit(run, runtime, code)
        deadline = time.monotonic() + 10
        while not (output / "started").exists() and time.monotonic() < deadline:
            time.sleep(0.03)
        assert (output / "started").exists()
        alter(source_runtime, change)
        result = pending.result(timeout=10)
    assert result.startswith("Error:") and "UNCONFIRMED OUTPUT" not in result
    time.sleep(3.1)
    assert not (output / "late").exists()


@pytest.mark.anyio
@pytest.mark.parametrize("withdrawal", ["member_role", "account"])
async def test_policy_allow_cannot_submit_ticket_after_source_authority_withdrawn(source_runtime, withdrawal):
    from datetime import UTC, datetime

    from app.alerting.governed_ticket import TicketActionAdapter, TicketTarget
    from app.alerting.governed_ticket_tool import authorize_diagnosis_execution, ticket_execution
    from app.platform.audit.repository import AuditEventRepository
    from app.platform.policy.evaluator import PolicyConfiguration, PolicyRule
    from app.platform.policy.fact_writer import PolicyFactWriter
    from app.platform.policy.repository import PolicyDecisionRepository
    from app.platform.policy.service import PolicyService
    from app.platform.submission.repository import ActionSubmissionRepository

    factory, _, _, _, runtime, _ = source_runtime
    decisions = PolicyDecisionRepository(factory)
    submissions = ActionSubmissionRepository(factory)
    policy = PolicyService(PolicyFactWriter(factory), decisions)
    scope = runtime.context | {"incident_id": "live-incident"}
    execution = ticket_execution(scope)
    sent = []

    class RevokeAfterDecision:
        async def evaluate_and_record(self, *args, **kwargs):
            decision = await policy.evaluate_and_record(*args, **kwargs)
            if withdrawal == "account":
                from sqlalchemy import text

                from app.gateway.auth_db import get_auth_engine

                with get_auth_engine().begin() as connection:
                    connection.execute(text('UPDATE "user" SET status=:status WHERE id=:id'), {"status": "suspended", "id": "user-a"})
            else:
                async with factory() as session:
                    row = (await session.exec(select(TenantMembership))).scalars().one()
                    row.role = "tenant_member"
                    session.add(row)
                    await session.commit()
            return decision

    async def resolve(tenant, incident):
        async with factory() as session:
            row = await session.get(Incident, incident)
        return TicketTarget(row, {"provider": "webhook", "webhook_url": "https://tickets.example/create"}, [])

    async def send(*args, **kwargs):
        sent.append(True)
        pytest.fail("Source withdrawal must prevent ticket submission")

    adapter = TicketActionAdapter(
        enabled_tenants=frozenset({"tenant-a"}),
        configuration=PolicyConfiguration(policy_id="source-live", version="v1", rules={"ticket.create": PolicyRule(risk_class="side_effect", verdict="allow")}),
        policy=RevokeAfterDecision(),
        submissions=submissions,
        resolve_target=resolve,
        check_permission=lambda *args: asyncio.sleep(0, result=True),
        send_ticket=send,
        execution_authorizer=authorize_diagnosis_execution,
    )
    with pytest.raises(PermissionError):
        await adapter.execute(execution, "source-policy-request", "live-incident", at=datetime.now(UTC))
    decision = await decisions.get_by_request("tenant-a", "source-policy-request")
    assert decision.verdict == "allow"
    assert await submissions.get("tenant-a", decision.decision_id) is None
    assert sent == []
    assert any(event.event_type == "action.policy_evaluated" for event in await AuditEventRepository(factory).list_recent("tenant-a"))
