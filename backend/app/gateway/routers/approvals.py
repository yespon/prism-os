"""Authenticated tenant Approval reads and review commands."""

from fastapi import APIRouter, Depends, HTTPException, Request

from app.gateway.authorization import require_tenant_context
from app.platform.approval.repository import ApprovalConflict
from app.platform.approval.service import ApprovalNotFound, ApprovalService
from app.platform.contracts import Approval

router = APIRouter(prefix="/api/approvals", tags=["approvals"])


def get_approval_service() -> ApprovalService:
    return ApprovalService()


def _identity(request: Request) -> tuple[str, str]:
    tenant_id = require_tenant_context(request)
    user_id = getattr(request.state, "user_id", None)
    if not isinstance(user_id, str) or not user_id.strip():
        raise HTTPException(status_code=401, detail="Authentication required")
    if getattr(request.state, "must_change_password", False):
        raise HTTPException(status_code=403, detail="Change initial password before reviewing approvals")
    return tenant_id, user_id


def _translate(error: Exception) -> HTTPException:
    if isinstance(error, ApprovalNotFound):
        return HTTPException(status_code=404, detail="Approval not found")
    if isinstance(error, PermissionError):
        return HTTPException(status_code=403, detail="Approval access denied")
    return HTTPException(status_code=409, detail="Approval is no longer actionable")


@router.get("/{approval_id}", response_model=Approval)
async def get_approval(
    approval_id: str,
    request: Request,
    service: ApprovalService = Depends(get_approval_service),
) -> Approval:
    tenant_id, user_id = _identity(request)
    try:
        return await service.get_for_user(tenant_id, approval_id, user_id)
    except (ApprovalNotFound, PermissionError, ApprovalConflict, ValueError) as exc:
        raise _translate(exc) from exc


@router.post("/{approval_id}/approve", response_model=Approval)
async def approve_approval(
    approval_id: str,
    request: Request,
    service: ApprovalService = Depends(get_approval_service),
) -> Approval:
    tenant_id, user_id = _identity(request)
    try:
        return await service.review(tenant_id, approval_id, user_id, "approve")
    except (ApprovalNotFound, PermissionError, ApprovalConflict, ValueError) as exc:
        raise _translate(exc) from exc


@router.post("/{approval_id}/reject", response_model=Approval)
async def reject_approval(
    approval_id: str,
    request: Request,
    service: ApprovalService = Depends(get_approval_service),
) -> Approval:
    tenant_id, user_id = _identity(request)
    try:
        return await service.review(tenant_id, approval_id, user_id, "reject")
    except (ApprovalNotFound, PermissionError, ApprovalConflict, ValueError) as exc:
        raise _translate(exc) from exc
