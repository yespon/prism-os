import asyncio
from datetime import timedelta

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models import governance as _governance_models  # noqa: F401
from app.platform.approval.repository import ApprovalRepository
from app.platform.approval.transitions import approve, consume
from app.platform.contracts import AuditEvent, IdentityRef, PolicyRequest, stable_platform_id
from app.platform.policy.fact_writer import PolicyFactWriter
from app.platform.submission.repository import ActionSubmissionRepository, SubmissionConflict

from .test_policy_fact_writer import NOW, _facts

APPROVER = IdentityRef(kind="user", id="admin-1", tenant_id="tenant-a")


@pytest.fixture
async def submission_setup(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'submission.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(SQLModel.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    yield PolicyFactWriter(factory), ApprovalRepository(factory), ActionSubmissionRepository(factory)
    await engine.dispose()


def _request(decision):
    return PolicyRequest(
        tenant_id=decision.tenant_id, request_id=decision.request_id,
        execution=decision.execution, action=decision.action,
        risk_class=decision.risk_class, resource_id=decision.resource_id,
        context_hash=decision.context_hash, requested_at=NOW,
    )


@pytest.mark.anyio
async def test_allow_submission_claims_only_one_external_attempt(submission_setup) -> None:
    writer, _, submissions = submission_setup
    decision, audit, _ = _facts(verdict="allow")
    await writer.record(decision, audit)
    prepared = await submissions.prepare(decision, at=NOW + timedelta(seconds=1))
    assert prepared.status == "not_submitted"
    assert await submissions.prepare(decision, at=NOW + timedelta(seconds=1)) == prepared
    results = await asyncio.gather(
        submissions.claim("tenant-a", decision.decision_id, at=NOW + timedelta(seconds=2)),
        submissions.claim("tenant-a", decision.decision_id, at=NOW + timedelta(seconds=2)),
    )
    assert sorted(results) == [False, True]
    assert (await submissions.get("tenant-a", decision.decision_id)).status == "unknown"
    assert await submissions.claim("tenant-a", decision.decision_id, at=NOW + timedelta(seconds=2)) is False
    result_audit = AuditEvent(
        tenant_id=decision.tenant_id,
        event_id=stable_platform_id("event", "ticket-submitted", decision.decision_id),
        event_type="action.submitted", action=decision.action, outcome="succeeded",
        execution=decision.execution, policy_decision_id=decision.decision_id,
        resource_id=decision.resource_id, payload={"ticket_id": "T-1", "provider": "webhook"},
        recorded_at=NOW + timedelta(seconds=3),
    )
    submitted = await submissions.mark_submitted(
        "tenant-a", decision.decision_id, ticket_id="T-1", ticket_url="https://tickets/T-1",
        provider="webhook", result_audit=result_audit, at=NOW + timedelta(seconds=3),
    )
    assert submitted.status == "submitted"
    assert submitted.ticket_id == "T-1"
    assert await submissions.claim("tenant-a", decision.decision_id, at=NOW + timedelta(seconds=2)) is False
    assert await submissions.get("tenant-b", decision.decision_id) is None


@pytest.mark.anyio
async def test_approval_submission_requires_consumed_fact(submission_setup) -> None:
    writer, approvals, submissions = submission_setup
    decision, audit, pending = _facts()
    await writer.record(decision, audit, pending)
    with pytest.raises(SubmissionConflict, match="consumed"):
        await submissions.prepare(decision, pending.approval_id, at=NOW + timedelta(seconds=1))
    approved = approve(pending, APPROVER, at=NOW + timedelta(minutes=1))
    await approvals.transition("tenant-a", pending.approval_id, 0, approved)
    with pytest.raises(SubmissionConflict, match="consumed"):
        await submissions.prepare(decision, pending.approval_id, at=NOW + timedelta(minutes=1))
    consumed = consume(approved, _request(decision), decision, at=NOW + timedelta(minutes=2))
    await approvals.transition("tenant-a", pending.approval_id, 1, consumed)
    prepared = await submissions.prepare(decision, pending.approval_id, at=NOW + timedelta(minutes=2))
    assert prepared.approval_id == pending.approval_id


@pytest.mark.anyio
async def test_submission_refuses_denied_or_unpaired_policy_fact(submission_setup) -> None:
    writer, _, submissions = submission_setup
    denied, denied_audit, _ = _facts(verdict="deny")
    await writer.record(denied, denied_audit)
    with pytest.raises(SubmissionConflict, match="allow"):
        await submissions.prepare(denied, at=NOW + timedelta(seconds=1))
    missing, _, _ = _facts(verdict="allow", suffix="missing")
    with pytest.raises(SubmissionConflict, match="persisted"):
        await submissions.prepare(missing, at=NOW + timedelta(seconds=1))
    assert await submissions.get("tenant-a", missing.decision_id) is None


@pytest.mark.anyio
async def test_expired_or_changed_context_cannot_prepare_submission(submission_setup) -> None:
    writer, _, submissions = submission_setup
    decision, audit, _ = _facts(verdict="allow")
    await writer.record(decision, audit)
    with pytest.raises(SubmissionConflict, match="expired"):
        await submissions.prepare(decision, at=NOW + timedelta(minutes=11))
    with pytest.raises(SubmissionConflict, match="changed"):
        await submissions.prepare(decision.model_copy(update={"context_hash": "b" * 64}), at=NOW)


@pytest.mark.anyio
async def test_unknown_never_reverts_to_not_submitted(submission_setup) -> None:
    writer, _, submissions = submission_setup
    decision, audit, _ = _facts(verdict="allow")
    await writer.record(decision, audit)
    await submissions.prepare(decision, at=NOW)
    assert await submissions.claim("tenant-a", decision.decision_id, at=NOW + timedelta(seconds=2))
    with pytest.raises(SubmissionConflict):
        await submissions.mark_submitted("tenant-a", decision.decision_id, ticket_id="", provider="webhook", result_audit=audit)
    assert (await submissions.get("tenant-a", decision.decision_id)).status == "unknown"
    assert (await submissions.prepare(decision, at=NOW)).status == "unknown"


@pytest.mark.anyio
async def test_approval_audit_link_must_match_submission(submission_setup) -> None:
    writer, approvals, submissions = submission_setup
    decision, audit, pending = _facts()
    await writer.record(decision, audit, pending)
    approved = approve(pending, APPROVER, at=NOW + timedelta(minutes=1))
    await approvals.transition("tenant-a", pending.approval_id, 0, approved)
    consumed = consume(approved, _request(decision), decision, at=NOW + timedelta(minutes=2))
    await approvals.transition("tenant-a", pending.approval_id, 1, consumed)
    with pytest.raises(SubmissionConflict, match="AuditEvent"):
        await submissions.prepare(decision, "other-approval", at=NOW + timedelta(minutes=2))
