"""Tenant-scoped Approval decisions using current membership and persisted facts."""

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Literal

from app.platform.approval.repository import ApprovalConflict, ApprovalRepository
from app.platform.approval.transitions import approve, consume, expire, reject
from app.platform.contracts import Approval, IdentityRef, PolicyRequest
from app.platform.policy.repository import PolicyDecisionRepository
from deerflow.database.tenant_service import get_membership, get_tenant, tenant_role_has_admin_capability

MembershipLookup = Callable[[str, str], Awaitable[object | None]]
TenantLookup = Callable[[str], Awaitable[object | None]]


class ApprovalNotFound(LookupError):
    pass


class ApprovalService:
    def __init__(
        self,
        approvals: ApprovalRepository | None = None,
        decisions: PolicyDecisionRepository | None = None,
        membership_lookup: MembershipLookup = get_membership,
        tenant_lookup: TenantLookup = get_tenant,
    ) -> None:
        self._approvals = approvals or ApprovalRepository()
        self._decisions = decisions or PolicyDecisionRepository()
        self._membership_lookup = membership_lookup
        self._tenant_lookup = tenant_lookup

    async def _load(self, tenant_id: str, approval_id: str) -> tuple[Approval, int]:
        found = await self._approvals.get(tenant_id, approval_id)
        if found is None:
            raise ApprovalNotFound("Approval unavailable")
        return found

    async def _member(self, tenant_id: str, user_id: str) -> object:
        if await self._tenant_lookup(tenant_id) is None:
            raise PermissionError("active tenant required")
        member = await self._membership_lookup(user_id, tenant_id)
        if member is None:
            raise PermissionError("active tenant membership required")
        return member

    async def _valid_decision(self, approval: Approval, at: datetime):
        decision = await self._decisions.get(approval.tenant_id, approval.decision_id)
        if decision is None or not approval.binds(decision):
            raise ApprovalConflict("Policy Decision or Approval context changed")
        if at >= decision.expires_at:
            raise ApprovalConflict("Policy Decision expired")
        return decision

    async def _expire_if_due(self, approval: Approval, version: int, at: datetime) -> tuple[Approval, int]:
        if approval.status == "pending" and at >= approval.expires_at:
            updated = expire(approval, at=at)
            return await self._approvals.transition(approval.tenant_id, approval.approval_id, version, updated)
        return approval, version

    async def get_for_user(self, tenant_id: str, approval_id: str, user_id: str, *, at: datetime | None = None) -> Approval:
        member = await self._member(tenant_id, user_id)
        approval, version = await self._load(tenant_id, approval_id)
        if approval.requester.id != user_id and not tenant_role_has_admin_capability(getattr(member, "role", None)):
            raise PermissionError("Approval is unavailable to this user")
        instant = at or datetime.now(UTC)
        approval, _ = await self._expire_if_due(approval, version, instant)
        return approval

    async def review(
        self,
        tenant_id: str,
        approval_id: str,
        approver_id: str,
        action: Literal["approve", "reject"],
        *,
        at: datetime | None = None,
    ) -> Approval:
        if action not in ("approve", "reject"):
            raise ValueError("invalid Approval review action")
        member = await self._member(tenant_id, approver_id)
        if not tenant_role_has_admin_capability(getattr(member, "role", None)):
            raise PermissionError("tenant admin role required")
        approval, version = await self._load(tenant_id, approval_id)
        if approval.requester.kind != "user" or approval.requester.id == approver_id:
            raise PermissionError("requester cannot review own Approval")
        await self._member(tenant_id, approval.requester.id)
        instant = at or datetime.now(UTC)
        approval, version = await self._expire_if_due(approval, version, instant)
        if approval.status != "pending":
            if approval.status == ("approved" if action == "approve" else "rejected") and approval.approver.id == approver_id:
                return approval
            raise ApprovalConflict("Approval is no longer pending")
        await self._valid_decision(approval, instant)
        actor = IdentityRef(kind="user", id=approver_id, tenant_id=tenant_id)
        updated = approve(approval, actor, at=instant) if action == "approve" else reject(approval, actor, at=instant)
        try:
            result, _ = await self._approvals.transition(tenant_id, approval_id, version, updated)
            return result
        except ApprovalConflict:
            current, _ = await self._load(tenant_id, approval_id)
            if current.status == updated.status and current.approver == actor:
                return current
            raise

    async def consume_for_request(
        self,
        tenant_id: str,
        approval_id: str,
        request: PolicyRequest,
        *,
        at: datetime | None = None,
    ) -> Approval:
        """Internal resume check; the later Action dispatcher owns external submission."""
        approval, version = await self._load(tenant_id, approval_id)
        if request.tenant_id != tenant_id or approval.requester != request.execution.actor:
            raise ApprovalConflict("Approval requester or tenant changed")
        if approval.requester.kind != "user":
            raise ApprovalConflict("Approval requester is not a user")
        await self._member(tenant_id, approval.requester.id)
        instant = at or datetime.now(UTC)
        decision = await self._valid_decision(approval, instant)
        updated = consume(approval, request, decision, at=instant)
        result, _ = await self._approvals.transition(tenant_id, approval_id, version, updated)
        return result
