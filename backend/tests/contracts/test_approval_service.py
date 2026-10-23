from datetime import timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models import governance as _governance_models  # noqa: F401
from app.platform.approval.repository import ApprovalConflict, ApprovalRepository
from app.platform.approval.service import ApprovalNotFound, ApprovalService
from app.platform.audit.repository import AuditEventRepository
from app.platform.policy.fact_writer import PolicyFactWriter
from app.platform.policy.repository import PolicyDecisionRepository
from app.platform.policy.service import PolicyService

from .test_policy_service import NOW, _config, _request


@pytest.fixture
async def approval_setup(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'approval-service.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(SQLModel.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    approvals = ApprovalRepository(factory)
    decisions = PolicyDecisionRepository(factory)
    policy = PolicyService(PolicyFactWriter(factory), decisions)
    await policy.evaluate_and_record(_request(), _config(), at=NOW)
    event = (await AuditEventRepository(factory).list_recent("tenant-a"))[0]
    roles = {"user-1": "member", "admin-1": "admin", "admin-2": "admin"}
    active_tenants = {"tenant-a"}

    async def membership(user_id, tenant_id):
        if tenant_id != "tenant-a" or user_id not in roles:
            return None
        return SimpleNamespace(role=roles[user_id])

    async def tenant_lookup(tenant_id):
        return object() if tenant_id in active_tenants else None

    service = ApprovalService(approvals, decisions, membership, tenant_lookup)
    yield service, approvals, event.approval_id, roles, active_tenants
    await engine.dispose()


@pytest.mark.anyio
async def test_admin_can_approve_and_idempotently_review(approval_setup) -> None:
    service, approvals, approval_id, _, _ = approval_setup
    approved = await service.review("tenant-a", approval_id, "admin-1", "approve", at=NOW + timedelta(minutes=1))
    assert approved.status == "approved"
    assert approved.approver.id == "admin-1"
    assert await service.review("tenant-a", approval_id, "admin-1", "approve", at=NOW + timedelta(minutes=2)) == approved
    assert (await approvals.get("tenant-a", approval_id))[1] == 1
    with pytest.raises(ApprovalConflict):
        await service.review("tenant-a", approval_id, "admin-2", "reject", at=NOW + timedelta(minutes=2))


@pytest.mark.anyio
async def test_reject_and_expire_are_persisted(approval_setup) -> None:
    service, approvals, approval_id, _, _ = approval_setup
    rejected = await service.review("tenant-a", approval_id, "admin-1", "reject", at=NOW + timedelta(minutes=1))
    assert rejected.status == "rejected"
    with pytest.raises(ValueError, match="not approved"):
        await service.consume_for_request("tenant-a", approval_id, _request(), at=NOW + timedelta(minutes=2))
    assert (await approvals.get("tenant-a", approval_id))[0].status == "rejected"


@pytest.mark.anyio
async def test_expired_approval_cannot_be_approved(approval_setup) -> None:
    service, approvals, approval_id, _, _ = approval_setup
    with pytest.raises(ApprovalConflict):
        await service.review("tenant-a", approval_id, "admin-1", "approve", at=NOW + timedelta(minutes=6))
    assert (await approvals.get("tenant-a", approval_id))[0].status == "expired"


@pytest.mark.anyio
async def test_current_roles_and_requester_membership_are_required(approval_setup) -> None:
    service, _, approval_id, roles, _ = approval_setup
    with pytest.raises(PermissionError):
        await service.review("tenant-a", approval_id, "user-1", "approve", at=NOW + timedelta(minutes=1))
    roles["admin-1"] = "member"
    with pytest.raises(PermissionError):
        await service.review("tenant-a", approval_id, "admin-1", "approve", at=NOW + timedelta(minutes=1))
    roles["admin-1"] = "admin"
    del roles["user-1"]
    with pytest.raises(PermissionError):
        await service.review("tenant-a", approval_id, "admin-1", "approve", at=NOW + timedelta(minutes=1))


@pytest.mark.anyio
async def test_cross_tenant_and_unrelated_reader_cannot_access(approval_setup) -> None:
    service, _, approval_id, _, _ = approval_setup
    with pytest.raises(ApprovalNotFound):
        await service.get_for_user("tenant-a", "missing", "admin-1", at=NOW)
    with pytest.raises(PermissionError):
        await service.get_for_user("tenant-b", approval_id, "admin-1", at=NOW)
    with pytest.raises(PermissionError):
        await service.get_for_user("tenant-a", approval_id, "outsider", at=NOW)
    assert (await service.get_for_user("tenant-a", approval_id, "user-1", at=NOW)).status == "pending"


@pytest.mark.anyio
async def test_consume_checks_exact_request_and_current_membership(approval_setup) -> None:
    service, approvals, approval_id, roles, _ = approval_setup
    await service.review("tenant-a", approval_id, "admin-1", "approve", at=NOW + timedelta(minutes=1))
    changed = _request().model_copy(update={"context_hash": "b" * 64})
    with pytest.raises(ValueError, match="context"):
        await service.consume_for_request("tenant-a", approval_id, changed, at=NOW + timedelta(minutes=2))
    del roles["user-1"]
    with pytest.raises(PermissionError):
        await service.consume_for_request("tenant-a", approval_id, _request(), at=NOW + timedelta(minutes=2))
    roles["user-1"] = "member"
    consumed = await service.consume_for_request("tenant-a", approval_id, _request(), at=NOW + timedelta(minutes=2))
    assert consumed.status == "consumed"
    assert (await approvals.get("tenant-a", approval_id))[1] == 2
    with pytest.raises(ValueError, match="already consumed"):
        await service.consume_for_request("tenant-a", approval_id, _request(), at=NOW + timedelta(minutes=3))


@pytest.mark.anyio
async def test_requester_cannot_self_approve_even_if_admin(approval_setup) -> None:
    service, _, approval_id, roles, _ = approval_setup
    roles["user-1"] = "admin"
    with pytest.raises(PermissionError, match="own Approval"):
        await service.review("tenant-a", approval_id, "user-1", "approve", at=NOW + timedelta(minutes=1))


@pytest.mark.anyio
async def test_inactive_tenant_cannot_review(approval_setup) -> None:
    service, _, approval_id, _, active_tenants = approval_setup
    active_tenants.clear()
    with pytest.raises(PermissionError, match="active tenant"):
        await service.review("tenant-a", approval_id, "admin-1", "approve", at=NOW + timedelta(minutes=1))
