"""Pure M1 Approval transitions over validated platform contracts."""

from datetime import UTC, datetime

from app.platform.contracts.approval import Approval
from app.platform.contracts.policy import PolicyDecision, PolicyRequest
from app.platform.contracts.resources import IdentityRef


def _at(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("transition time must include a timezone")
    return value.astimezone(UTC)


def _pending(approval: Approval, at: datetime) -> datetime:
    instant = _at(at)
    if approval.status != "pending":
        raise ValueError("approval is not pending")
    if instant < approval.created_at:
        raise ValueError("transition precedes approval creation")
    if instant >= approval.expires_at:
        raise ValueError("approval expired")
    return instant


def _approver(approval: Approval, actor: IdentityRef) -> None:
    if actor.tenant_id != approval.tenant_id:
        raise ValueError("approver must belong to the same tenant")
    if actor.kind != "user":
        raise ValueError("approver must be a user")


def _updated(approval: Approval, **changes: object) -> Approval:
    return Approval.model_validate({**approval.model_dump(), **changes})


def approve(approval: Approval, actor: IdentityRef, *, at: datetime) -> Approval:
    """Produce an approved fact; caller must authorize actor and persist with CAS."""
    _approver(approval, actor)
    instant = _pending(approval, at)
    return _updated(approval, status="approved", approver=actor, decided_at=instant)


def reject(approval: Approval, actor: IdentityRef, *, at: datetime) -> Approval:
    """Produce a rejected fact; caller must authorize actor and persist with CAS."""
    _approver(approval, actor)
    instant = _pending(approval, at)
    return _updated(approval, status="rejected", approver=actor, decided_at=instant)


def expire(approval: Approval, *, at: datetime) -> Approval:
    instant = _at(at)
    if approval.status != "pending":
        raise ValueError("approval is not pending")
    if instant < approval.expires_at:
        raise ValueError("approval cannot expire before deadline")
    return _updated(approval, status="expired", decided_at=instant)


def consume(
    approval: Approval,
    request: PolicyRequest,
    decision: PolicyDecision,
    *,
    at: datetime,
) -> Approval:
    """Bind an approved fact to the unchanged Action immediately before dispatch."""
    instant = _at(at)
    if approval.status == "consumed":
        raise ValueError("approval already consumed")
    if approval.status != "approved":
        raise ValueError("approval is not approved")
    if not approval.binds(decision) or not decision.binds(request):
        raise ValueError("approval context or decision version changed")
    if instant >= approval.expires_at or instant >= decision.expires_at:
        raise ValueError("approval expired")
    if approval.decided_at is None or instant < approval.decided_at:
        raise ValueError("consumption precedes approval")
    return _updated(approval, status="consumed", consumed_at=instant)
