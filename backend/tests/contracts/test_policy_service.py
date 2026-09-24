from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models import governance as _governance_models  # noqa: F401
from app.platform.approval.repository import ApprovalRepository
from app.platform.approval.transitions import approve
from app.platform.audit.repository import AuditEventRepository
from app.platform.contracts import ExecutionEnvelope, IdentityRef, PolicyRequest
from app.platform.policy.evaluator import PolicyConfiguration, PolicyRule
from app.platform.policy.fact_writer import PolicyFactWriter
from app.platform.policy.repository import PolicyDecisionRepository
from app.platform.policy.service import PolicyService

NOW = datetime(2026, 9, 24, 10, 0, tzinfo=UTC)


@pytest.fixture
async def service_stores(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'service.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(SQLModel.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    decisions = PolicyDecisionRepository(factory)
    audits = AuditEventRepository(factory)
    approvals = ApprovalRepository(factory)
    yield PolicyService(PolicyFactWriter(factory), decisions), decisions, audits, approvals
    await engine.dispose()


def _request() -> PolicyRequest:
    execution = ExecutionEnvelope(
        tenant_id="tenant-a", task_id="task-1", run_id="run-1", correlation_id="alert-1",
        workload=IdentityRef(kind="workload", id="agent-1", tenant_id="tenant-a"),
        actor=IdentityRef(kind="user", id="user-1", tenant_id="tenant-a"), occurred_at=NOW,
    )
    return PolicyRequest(
        tenant_id="tenant-a", request_id="request-1", execution=execution,
        action="ticket.create", risk_class="side_effect", resource_id="incident-1",
        context_hash="a" * 64, requested_at=NOW,
    )


def _config(verdict="require_approval") -> PolicyConfiguration:
    return PolicyConfiguration(
        policy_id="aio-ops-m1", version="v1",
        rules={"ticket.create": PolicyRule(risk_class="side_effect", verdict=verdict)},
    )


@pytest.mark.anyio
async def test_service_persists_decision_audit_and_pending_approval(service_stores) -> None:
    service, decisions, audits, approvals = service_stores
    decision = await service.evaluate_and_record(_request(), _config(), at=NOW)
    assert decision.verdict == "require_approval"
    assert await decisions.get("tenant-a", decision.decision_id) == decision
    events = await audits.list_recent("tenant-a")
    assert len(events) == 1
    assert events[0].policy_decision_id == decision.decision_id
    assert events[0].payload == {
        "verdict": "require_approval", "policy_version": "v1", "reason_code": "policy.rule",
    }
    pending = await approvals.get("tenant-a", events[0].approval_id)
    assert pending[0].binds(decision)
    assert pending[0].status == "pending"


@pytest.mark.anyio
async def test_service_reuses_exact_persisted_facts_on_duplicate_request(service_stores) -> None:
    service, _, audits, _ = service_stores
    first = await service.evaluate_and_record(_request(), _config(), at=NOW)
    changed_config = PolicyConfiguration(
        policy_id="new-policy", version="v2",
        rules={"ticket.create": PolicyRule(risk_class="side_effect", verdict="deny")},
    )
    second = await service.evaluate_and_record(_request(), changed_config, at=NOW + timedelta(seconds=3))
    assert second == first
    assert len(await audits.list_recent("tenant-a")) == 1


@pytest.mark.anyio
async def test_service_rejects_request_id_reuse_for_changed_context(service_stores) -> None:
    service, _, audits, _ = service_stores
    await service.evaluate_and_record(_request(), _config(), at=NOW)
    with pytest.raises(ValueError, match="context"):
        await service.evaluate_and_record(
            _request().model_copy(update={"context_hash": "b" * 64}), _config(), at=NOW,
        )
    assert len(await audits.list_recent("tenant-a")) == 1


@pytest.mark.anyio
async def test_service_records_fail_closed_provider_result(service_stores) -> None:
    service, _, audits, _ = service_stores

    async def broken(_request):
        raise RuntimeError("private provider detail")

    decision = await service.evaluate_and_record(_request(), _config("allow"), broken, at=NOW)
    assert (decision.verdict, decision.reason_code) == ("deny", "policy.provider_error")
    events = await audits.list_recent("tenant-a")
    assert events[0].outcome == "denied"
    assert "private" not in events[0].model_dump_json()


@pytest.mark.anyio
async def test_duplicate_request_after_approval_does_not_reopen_it(service_stores) -> None:
    service, _, audits, approvals = service_stores
    first = await service.evaluate_and_record(_request(), _config(), at=NOW)
    event = (await audits.list_recent("tenant-a"))[0]
    pending, version = await approvals.get("tenant-a", event.approval_id)
    approver = IdentityRef(kind="user", id="admin-1", tenant_id="tenant-a")
    approved = approve(pending, approver, at=NOW + timedelta(minutes=1))
    await approvals.transition("tenant-a", pending.approval_id, version, approved)
    assert await service.evaluate_and_record(_request(), _config(), at=NOW + timedelta(minutes=2)) == first
    assert await approvals.get("tenant-a", pending.approval_id) == (approved, 1)
