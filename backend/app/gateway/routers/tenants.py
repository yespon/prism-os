from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from app.gateway.audit import record_audit_event
from app.gateway.auth_repository import AuthUserRepository
from app.gateway.authorization import require_tenant_admin
from deerflow.database.tenant_service import (
    add_tenant_member,
    get_membership,
    get_tenant,
    list_tenant_members,
    list_user_tenants,
    normalize_tenant_role,
    remove_tenant_member,
    set_tenant_member_status,
    update_tenant_member_role,
)
from deerflow.database.user_config_service import get_current_tenant_id, set_current_tenant_id

router = APIRouter(prefix="/api", tags=["tenants"])


class TenantItemResponse(BaseModel):
    id: str = Field(..., description="Tenant id")
    name: str = Field(..., description="Tenant display name")
    slug: str = Field(..., description="Tenant slug")
    role: str = Field(..., description="Role in the tenant")
    tenant_type: str = Field(default="general", description="Tenant type: general, ops, product, rd, or custom")


class TenantsListResponse(BaseModel):
    tenants: list[TenantItemResponse]


class CurrentTenantResponse(BaseModel):
    tenant_id: str
    role: str
    tenant_type: str = "general"


class SwitchTenantRequest(BaseModel):
    tenant_id: str = Field(..., description="Tenant id to switch to")


def _require_user_id(request: Request) -> str:
    user_id = getattr(request.state, "user_id", None)
    if not isinstance(user_id, str) or not user_id.strip():
        raise HTTPException(status_code=401, detail="Authentication required")
    return user_id


@router.get("/tenants", response_model=TenantsListResponse)
async def list_tenants(request: Request) -> TenantsListResponse:
    user_id = _require_user_id(request)

    rows = await list_user_tenants(user_id)

    return TenantsListResponse(
        tenants=[
            TenantItemResponse(
                id=tenant.id,
                name=tenant.name,
                slug=tenant.slug,
                role=normalize_tenant_role(membership.role),
                tenant_type=getattr(tenant, "tenant_type", "general") or "general",
            )
            for tenant, membership in rows
        ]
    )


@router.get("/tenants/current", response_model=CurrentTenantResponse)
async def get_current_tenant(request: Request) -> CurrentTenantResponse:
    user_id = _require_user_id(request)

    rows = await list_user_tenants(user_id)
    if not rows:
        raise HTTPException(status_code=403, detail="当前账号未加入任何租户，请联系管理员将你加入租户后再登录。")

    memberships_by_tenant = {tenant.id: membership for tenant, membership in rows}
    current_tenant_id = await get_current_tenant_id(user_id)

    if not current_tenant_id or current_tenant_id not in memberships_by_tenant:
        current_tenant_id = rows[0][0].id
        await set_current_tenant_id(user_id, current_tenant_id)

    membership = memberships_by_tenant[current_tenant_id]
    tenant = next((t for t, _ in rows if t.id == current_tenant_id), None)
    tenant_type = getattr(tenant, "tenant_type", "general") or "general" if tenant else "general"
    return CurrentTenantResponse(
        tenant_id=current_tenant_id,
        role=normalize_tenant_role(membership.role),
        tenant_type=tenant_type,
    )


@router.post("/tenants/switch", response_model=CurrentTenantResponse)
async def switch_tenant(request: Request, body: SwitchTenantRequest) -> CurrentTenantResponse:
    user_id = _require_user_id(request)
    tenant_id = body.tenant_id.strip()
    if not tenant_id:
        raise HTTPException(status_code=400, detail="tenant_id is required")

    membership = await get_membership(user_id=user_id, tenant_id=tenant_id)
    if membership is None:
        raise HTTPException(status_code=403, detail="Tenant access denied")

    await set_current_tenant_id(user_id, tenant_id)
    request.state.tenant_id = tenant_id

    tenant = await get_tenant(tenant_id)
    tenant_type = getattr(tenant, "tenant_type", "general") or "general" if tenant else "general"

    return CurrentTenantResponse(
        tenant_id=tenant_id,
        role=normalize_tenant_role(membership.role),
        tenant_type=tenant_type,
    )


class TenantMemberResponse(BaseModel):
    user_id: str
    email: str | None = None
    name: str | None = None
    role: str
    status: Literal["active", "inactive"]


class TenantMembersListResponse(BaseModel):
    members: list[TenantMemberResponse]


class TenantSelectableUserResponse(BaseModel):
    user_id: str
    email: str | None = None
    name: str | None = None
    role: str | None = None
    status: str | None = None
    already_member: bool


class TenantSelectableUsersResponse(BaseModel):
    users: list[TenantSelectableUserResponse]


class AddTenantMemberRequest(BaseModel):
    user_id: str = Field(..., description="User ID to add to tenant")
    role: Literal["tenant_admin", "tenant_member"] = Field(default="tenant_member", description="Role to assign")


class AddTenantMembersByEmailRequest(BaseModel):
    emails: list[str] = Field(..., description="List of email addresses to add")
    role: Literal["tenant_admin", "tenant_member"] = Field(default="tenant_member", description="Role to assign")


class AddTenantMembersByEmailResult(BaseModel):
    success: list[dict] = Field(default_factory=list)
    not_found: list[str] = Field(default_factory=list)
    already_member: list[dict] = Field(default_factory=list)


class UpdateTenantMemberRequest(BaseModel):
    role: Literal["tenant_admin", "tenant_member"] = Field(..., description="New role for the member")


class UpdateTenantMemberStatusRequest(BaseModel):
    status: Literal["active", "inactive"] = Field(..., description="Membership status")


@router.get("/tenants/users", response_model=TenantSelectableUsersResponse, dependencies=[Depends(require_tenant_admin)])
async def list_selectable_users(
    request: Request,
    keyword: str | None = None,
    limit: int = 20,
) -> TenantSelectableUsersResponse:
    tenant_id = request.state.tenant_id
    auth_repo = AuthUserRepository()

    safe_limit = max(1, min(limit, 100))
    rows = auth_repo.list_users(keyword=keyword.strip() if keyword else None, limit=safe_limit, offset=0)
    members = await list_tenant_members(tenant_id, include_inactive=True)
    member_ids = {item.user_id for item in members}

    users = [
        TenantSelectableUserResponse(
            user_id=str(row.get("id", "")),
            email=row.get("email"),
            name=row.get("name"),
            role=row.get("role"),
            status=row.get("status"),
            already_member=str(row.get("id", "")) in member_ids,
        )
        for row in rows
        if str(row.get("id", "")).strip()
    ]
    return TenantSelectableUsersResponse(users=users)


@router.get("/tenants/members", response_model=TenantMembersListResponse, dependencies=[Depends(require_tenant_admin)])
async def list_members(request: Request) -> TenantMembersListResponse:
    tenant_id = request.state.tenant_id
    members = await list_tenant_members(tenant_id, include_inactive=True)

    auth_repo = AuthUserRepository()
    response_members = []
    for m in members:
        user_info = auth_repo.get_user_by_id(m.user_id)
        email = user_info["email"] if user_info else None
        name = user_info["name"] if user_info else None
        response_members.append(
            TenantMemberResponse(
                user_id=m.user_id,
                email=email,
                name=name,
                role=normalize_tenant_role(m.role),
                status="inactive" if str(m.status).lower() == "inactive" else "active",
            )
        )
    return TenantMembersListResponse(members=response_members)


@router.post("/tenants/members", response_model=TenantMemberResponse, dependencies=[Depends(require_tenant_admin)])
async def add_member(request: Request, body: AddTenantMemberRequest) -> TenantMemberResponse:
    tenant_id = request.state.tenant_id
    actor_id = getattr(request.state, "user_id", None)
    auth_repo = AuthUserRepository()
    user_info = auth_repo.get_user_by_id(body.user_id)
    if not user_info:
        raise HTTPException(status_code=404, detail="User not found")

    m = await add_tenant_member(tenant_id, body.user_id, role=body.role)
    record_audit_event(
        "tenant.member.added",
        actor_id=actor_id,
        target_user_id=m.user_id,
        tenant_id=tenant_id,
        scope="tenant",
        metadata={"role": normalize_tenant_role(m.role)},
    )
    return TenantMemberResponse(
        user_id=m.user_id,
        email=user_info.get("email"),
        name=user_info.get("name"),
        role=normalize_tenant_role(m.role),
        status="inactive" if str(m.status).lower() == "inactive" else "active",
    )


@router.post("/tenants/members/by-email", response_model=AddTenantMembersByEmailResult, dependencies=[Depends(require_tenant_admin)])
async def add_members_by_email(request: Request, body: AddTenantMembersByEmailRequest) -> AddTenantMembersByEmailResult:
    tenant_id = request.state.tenant_id
    actor_id = getattr(request.state, "user_id", None)
    auth_repo = AuthUserRepository()
    
    # Get current members to check for duplicates
    current_members = await list_tenant_members(tenant_id, include_inactive=True)
    member_ids = {m.user_id for m in current_members}
    
    success = []
    not_found = []
    already_member = []
    
    for email in body.emails:
        email = email.strip().lower()
        if not email:
            continue
            
        # Find user by exact email match
        users = auth_repo.list_users(keyword=email, limit=10)
        user = None
        for u in users:
            if u.get("email", "").lower() == email:
                user = u
                break
        
        if not user:
            not_found.append(email)
            continue
            
        user_id = str(user.get("id", ""))
        
        # Check if already a member
        if user_id in member_ids:
            already_member.append({"email": email, "user_id": user_id})
            continue
        
        # Add member
        try:
            m = await add_tenant_member(tenant_id, user_id, role=body.role)
            member_ids.add(user_id)
            success.append({"email": email, "user_id": user_id, "name": user.get("name")})
            record_audit_event(
                "tenant.member.added",
                actor_id=actor_id,
                target_user_id=m.user_id,
                tenant_id=tenant_id,
                scope="tenant",
                metadata={"role": normalize_tenant_role(m.role), "by_email": True},
            )
        except Exception:
            not_found.append(email)
    
    return AddTenantMembersByEmailResult(
        success=success,
        not_found=not_found,
        already_member=already_member,
    )


@router.put("/tenants/members/{target_user_id}", response_model=TenantMemberResponse, dependencies=[Depends(require_tenant_admin)])
async def update_member(request: Request, target_user_id: str, body: UpdateTenantMemberRequest) -> TenantMemberResponse:
    tenant_id = request.state.tenant_id
    actor_id = getattr(request.state, "user_id", None)
    auth_repo = AuthUserRepository()
    user_info = auth_repo.get_user_by_id(target_user_id)
    if not user_info:
        raise HTTPException(status_code=404, detail="User not found")

    m = await update_tenant_member_role(tenant_id, target_user_id, role=body.role)
    if not m:
        raise HTTPException(status_code=404, detail="Membership not found in this tenant")

    record_audit_event(
        "tenant.member.role_updated",
        actor_id=actor_id,
        target_user_id=m.user_id,
        tenant_id=tenant_id,
        scope="tenant",
        metadata={"role": normalize_tenant_role(m.role)},
    )

    return TenantMemberResponse(
        user_id=m.user_id,
        email=user_info.get("email"),
        name=user_info.get("name"),
        role=normalize_tenant_role(m.role),
        status="inactive" if str(m.status).lower() == "inactive" else "active",
    )


@router.patch("/tenants/members/{target_user_id}/status", response_model=TenantMemberResponse, dependencies=[Depends(require_tenant_admin)])
async def update_member_status(
    request: Request,
    target_user_id: str,
    body: UpdateTenantMemberStatusRequest,
) -> TenantMemberResponse:
    tenant_id = request.state.tenant_id
    actor_id = getattr(request.state, "user_id", None)
    auth_repo = AuthUserRepository()
    user_info = auth_repo.get_user_by_id(target_user_id)
    if not user_info:
        raise HTTPException(status_code=404, detail="User not found")

    if target_user_id == getattr(request.state, "user_id", None) and body.status == "inactive":
        raise HTTPException(status_code=400, detail="Cannot disable yourself in the current tenant")

    try:
        m = await set_tenant_member_status(tenant_id, target_user_id, body.status)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    if not m:
        raise HTTPException(status_code=404, detail="Membership not found in this tenant")

    record_audit_event(
        "tenant.member.status_updated",
        actor_id=actor_id,
        target_user_id=m.user_id,
        tenant_id=tenant_id,
        scope="tenant",
        metadata={"status": "inactive" if str(m.status).lower() == "inactive" else "active"},
    )

    return TenantMemberResponse(
        user_id=m.user_id,
        email=user_info.get("email"),
        name=user_info.get("name"),
        role=normalize_tenant_role(m.role),
        status="inactive" if str(m.status).lower() == "inactive" else "active",
    )


@router.delete("/tenants/members/{target_user_id}", dependencies=[Depends(require_tenant_admin)])
async def remove_member(request: Request, target_user_id: str):
    tenant_id = request.state.tenant_id
    actor_id = getattr(request.state, "user_id", None)
    if target_user_id == getattr(request.state, "user_id", None):
        raise HTTPException(status_code=400, detail="Cannot remove yourself from the tenant")

    success = await remove_tenant_member(tenant_id, target_user_id)
    if not success:
        raise HTTPException(status_code=404, detail="Membership not found")

    record_audit_event(
        "tenant.member.removed",
        actor_id=actor_id,
        target_user_id=target_user_id,
        tenant_id=tenant_id,
        scope="tenant",
    )
    return {"status": "ok"}

@router.post("/tenants")
async def create_new_tenant(request: Request):
    _require_user_id(request)
    raise HTTPException(
        status_code=403,
        detail="Self-service tenant creation is disabled. Use platform admin API /api/admin/tenants.",
    )
