from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models import governance as _governance_models  # noqa: F401
from app.platform.approval.repository import ApprovalConflict, ApprovalRepository
from app.platform.approval.transitions import approve, reject
from app.platform.contracts import Approval, ExecutionEnvelope, IdentityRef, PolicyDecision
from app.platform.policy.repository import PolicyDecisionRepository

NOW = datetime(2026, 9, 24, 9, 0, tzinfo=UTC)
ACTOR = IdentityRef(kind="user", id="user-1", tenant_id="tenant-a")
APPROVER = IdentityRef(kind="user", id="admin-1", tenant_id="tenant-a")


@pytest.fixture
async def repositories(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'governance.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(SQLModel.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    yield PolicyDecisionRepository(factory), ApprovalRepository(factory)
    await engine.dispose()


def _decision(**changes) -> PolicyDecision:
    execution = ExecutionEnvelope(
        tenant_id="tenant-a",
        task_id="task-1",
        run_id="run-1",
        correlation_id="alert-1",
        workload=IdentityRef(kind="workload", id="agent-1", tenant_id="tenant-a"),
        actor=ACTOR,
        occurred_at=NOW,
    )
    fields = {
        "tenant_id": "tenant-a",
        "decision_id": "decision-1",
        "request_id": "request-1",
        "execution": execution,
        "action": "ticket.create",
        "risk_class": "side_effect",
        "resource_id": "incident-1",
        "context_hash": "a" * 64,
        "verdict": "require_approval",
        "policy_id": "ticket-policy",
        "policy_version": "v1",
        "reason_code": "approval.required",
        "decided_at": NOW,
        "expires_at": NOW + timedelta(minutes=10),
    }
    fields.update(changes)
    return PolicyDecision(**fields)


def _approval(decision: PolicyDecision | None = None) -> Approval:
    decision = decision or _decision()
    return Approval(
        tenant_id=decision.tenant_id,
        approval_id="approval-1",
        decision_id=decision.decision_id,
        request_id=decision.request_id,
        execution=decision.execution,
        action=decision.action,
        resource_id=decision.resource_id,
        context_hash=decision.context_hash,
        policy_version=decision.policy_version,
        requester=ACTOR,
        status="pending",
        created_at=NOW,
        expires_at=NOW + timedelta(minutes=5),
    )


@pytest.mark.anyio
async def test_decision_is_tenant_scoped_and_idempotent(repositories) -> None:
    decisions, _ = repositories
    decision = _decision()
    await decisions.append(decision)
    await decisions.append(decision)
    assert await decisions.get("tenant-a", decision.decision_id) == decision
    assert await decisions.get_by_request("tenant-a", decision.request_id) == decision
    assert await decisions.get("tenant-b", decision.decision_id) is None
    assert await decisions.get_by_request("tenant-b", decision.request_id) is None


@pytest.mark.anyio
async def test_decision_rejects_reused_id_or_request_with_different_fact(repositories) -> None:
    decisions, _ = repositories
    await decisions.append(_decision())
    with pytest.raises(ValueError, match="different payload"):
        await decisions.append(_decision(verdict="deny"))
    with pytest.raises(ValueError, match="request_id"):
        await decisions.append(_decision(decision_id="decision-2"))


@pytest.mark.anyio
async def test_approval_is_tenant_scoped_and_idempotent(repositories) -> None:
    decisions, approvals = repositories
    pending = _approval()
    await decisions.append(_decision())
    await approvals.create(pending)
    await approvals.create(pending)
    assert await approvals.get("tenant-a", pending.approval_id) == (pending, 0)
    assert await approvals.get("tenant-b", pending.approval_id) is None
    with pytest.raises(ValueError, match="different payload"):
        await approvals.create(pending.model_copy(update={"context_hash": "b" * 64}))


@pytest.mark.anyio
async def test_approval_requires_persisted_matching_decision(repositories) -> None:
    decisions, approvals = repositories
    with pytest.raises(ValueError, match="Policy Decision"):
        await approvals.create(_approval())
    await decisions.append(_decision(verdict="allow"))
    with pytest.raises(ValueError, match="require_approval"):
        await approvals.create(_approval())


@pytest.mark.anyio
async def test_approval_compare_and_swap_allows_one_terminal_decision(repositories) -> None:
    decisions, approvals = repositories
    pending = _approval()
    await decisions.append(_decision())
    await approvals.create(pending)
    approved = approve(pending, APPROVER, at=NOW + timedelta(minutes=1))
    rejected = reject(pending, APPROVER, at=NOW + timedelta(minutes=1))
    assert await approvals.transition("tenant-a", pending.approval_id, 0, approved) == (approved, 1)
    with pytest.raises(ApprovalConflict):
        await approvals.transition("tenant-a", pending.approval_id, 0, rejected)
    assert await approvals.get("tenant-a", pending.approval_id) == (approved, 1)


@pytest.mark.anyio
async def test_approval_rejects_cross_tenant_and_immutable_context_change(repositories) -> None:
    decisions, approvals = repositories
    pending = _approval()
    await decisions.append(_decision())
    await approvals.create(pending)
    approved = approve(pending, APPROVER, at=NOW + timedelta(minutes=1))
    with pytest.raises(ApprovalConflict):
        await approvals.transition("tenant-b", pending.approval_id, 0, approved)
    with pytest.raises(ValueError, match="immutable"):
        await approvals.transition(
            "tenant-a",
            pending.approval_id,
            0,
            approved.model_copy(update={"context_hash": "b" * 64}),
        )
    assert await approvals.get("tenant-a", pending.approval_id) == (pending, 0)


@pytest.mark.anyio
async def test_approval_consumption_cannot_replace_approver(repositories) -> None:
    decisions, approvals = repositories
    decision = _decision()
    pending = _approval(decision)
    await decisions.append(decision)
    await approvals.create(pending)
    approved = approve(pending, APPROVER, at=NOW + timedelta(minutes=1))
    await approvals.transition("tenant-a", pending.approval_id, 0, approved)
    changed = approved.model_copy(update={
        "status": "consumed",
        "consumed_at": NOW + timedelta(minutes=2),
        "approver": IdentityRef(kind="user", id="admin-2", tenant_id="tenant-a"),
    })
    with pytest.raises(ValueError, match="immutable"):
        await approvals.transition("tenant-a", pending.approval_id, 1, changed)


@pytest.mark.anyio
async def test_concurrent_approval_decisions_have_one_winner(repositories) -> None:
    import asyncio

    decisions, approvals = repositories
    pending = _approval()
    await decisions.append(_decision())
    await approvals.create(pending)
    approved = approve(pending, APPROVER, at=NOW + timedelta(minutes=1))
    rejected = reject(pending, APPROVER, at=NOW + timedelta(minutes=1))
    results = await asyncio.gather(
        approvals.transition("tenant-a", pending.approval_id, 0, approved),
        approvals.transition("tenant-a", pending.approval_id, 0, rejected),
        return_exceptions=True,
    )
    assert sum(isinstance(result, tuple) for result in results) == 1
    assert sum(isinstance(result, ApprovalConflict) for result in results) == 1
