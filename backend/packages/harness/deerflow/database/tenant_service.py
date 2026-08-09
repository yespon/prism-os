from __future__ import annotations

import re
from uuid import uuid4

from sqlmodel import select

from deerflow.database.models import Tenant, TenantMembership
from deerflow.database.session import get_session_factory

TENANT_ROLE_ADMIN = "tenant_admin"
TENANT_ROLE_MEMBER = "tenant_member"


def normalize_tenant_role(role: str) -> str:
    """Normalize persisted/input tenant role into capability role value."""
    normalized = str(role or "").strip().lower()
    if normalized in {"owner", "admin", TENANT_ROLE_ADMIN}:
        return TENANT_ROLE_ADMIN
    if normalized in {"member", TENANT_ROLE_MEMBER}:
        return TENANT_ROLE_MEMBER
    raise ValueError("Invalid tenant role. Allowed values: tenant_admin, tenant_member")


def tenant_role_has_admin_capability(role: str | None) -> bool:
    if role is None:
        return False
    try:
        return normalize_tenant_role(role) == TENANT_ROLE_ADMIN
    except ValueError:
        return False


def normalize_tenant_role_for_storage(role: str, *, preserve_owner: bool = False) -> str:
    normalized = normalize_tenant_role(role)
    if normalized == TENANT_ROLE_ADMIN:
        return "owner" if preserve_owner else "admin"
    return "member"


def _slugify(name: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return base or "tenant"


async def get_user_active_memberships(user_id: str) -> list[TenantMembership]:
    """Return active tenant memberships for a user."""
    session_factory = get_session_factory()
    async with session_factory() as session:
        rows = (
            await session.execute(
                select(TenantMembership).where(
                    TenantMembership.user_id == user_id,
                    TenantMembership.status == "active",
                )
            )
        ).scalars().all()
        return list(rows)


async def get_membership(user_id: str, tenant_id: str) -> TenantMembership | None:
    """Return active membership for a user in a specific tenant."""
    session_factory = get_session_factory()
    async with session_factory() as session:
        row = await session.scalar(
            select(TenantMembership).where(
                TenantMembership.user_id == user_id,
                TenantMembership.tenant_id == tenant_id,
                TenantMembership.status == "active",
            )
        )
        return row


async def get_tenant(tenant_id: str) -> Tenant | None:
    """Return an active tenant by id."""
    session_factory = get_session_factory()
    async with session_factory() as session:
        tenant = await session.get(Tenant, tenant_id)
        if tenant is None or tenant.status != "active":
            return None
        return tenant


async def ensure_default_tenant_for_user(user_id: str, role: str = "member", tenant_type: str = "general") -> TenantMembership:
    """Ensure user has at least one active tenant membership.

    If the user has no active membership, create a personal default tenant and
    return its membership.
    """
    session_factory = get_session_factory()
    async with session_factory() as session:
        existing = await session.scalar(
            select(TenantMembership).where(
                TenantMembership.user_id == user_id,
                TenantMembership.status == "active",
            )
        )
        if existing is not None:
            return existing

        tenant_id = f"t-{uuid4().hex[:16]}"
        tenant_name = f"{user_id}-default"
        tenant_slug = f"{_slugify(user_id)}-{tenant_id[-6:]}"

        tenant = Tenant(
            id=tenant_id,
            name=tenant_name,
            slug=tenant_slug,
            status="active",
            tenant_type=tenant_type,
        )
        session.add(tenant)

        membership = TenantMembership(
            tenant_id=tenant_id,
            user_id=user_id,
            role=normalize_tenant_role_for_storage(role),
            status="active",
        )
        session.add(membership)

        await session.commit()
        await session.refresh(membership)
        return membership


async def list_user_tenants(user_id: str) -> list[tuple[Tenant, TenantMembership]]:
    """List active tenants for a user with membership metadata."""
    session_factory = get_session_factory()
    async with session_factory() as session:
        memberships = (
            await session.execute(
                select(TenantMembership).where(
                    TenantMembership.user_id == user_id,
                    TenantMembership.status == "active",
                )
            )
        ).scalars().all()

        result: list[tuple[Tenant, TenantMembership]] = []
        for membership in memberships:
            tenant = await session.get(Tenant, membership.tenant_id)
            if tenant is None or tenant.status != "active":
                continue
            result.append((tenant, membership))

        return result


async def backfill_default_tenants_for_users(user_ids: list[str], role: str = "member") -> int:
    """Ensure default tenant membership exists for each user in the list.

    Returns count of processed users.
    """
    processed = 0
    for user_id in user_ids:
        normalized_user_id = str(user_id).strip()
        if not normalized_user_id:
            continue
        await ensure_default_tenant_for_user(normalized_user_id, role=role)
        processed += 1
    return processed

async def list_tenant_members(tenant_id: str, *, include_inactive: bool = False) -> list[TenantMembership]:
    session_factory = get_session_factory()
    async with session_factory() as session:
        query = select(TenantMembership).where(TenantMembership.tenant_id == tenant_id)
        if not include_inactive:
            query = query.where(TenantMembership.status == "active")
        rows = (await session.execute(query)).scalars().all()
        return list(rows)

async def add_tenant_member(tenant_id: str, user_id: str, role: str = "member") -> TenantMembership:
    stored_role = normalize_tenant_role_for_storage(role)
    session_factory = get_session_factory()
    async with session_factory() as session:
        existing = await session.scalar(
            select(TenantMembership).where(
                TenantMembership.tenant_id == tenant_id,
                TenantMembership.user_id == user_id,
            )
        )
        if existing:
            existing.status = "active"
            existing.role = stored_role
            await session.commit()
            await session.refresh(existing)
            return existing

        membership = TenantMembership(
            tenant_id=tenant_id,
            user_id=user_id,
            role=stored_role,
            status="active",
        )
        session.add(membership)
        await session.commit()
        await session.refresh(membership)
        return membership

async def remove_tenant_member(tenant_id: str, user_id: str) -> bool:
    session_factory = get_session_factory()
    async with session_factory() as session:
        existing = await session.scalar(
            select(TenantMembership).where(
                TenantMembership.tenant_id == tenant_id,
                TenantMembership.user_id == user_id,
            )
        )
        if not existing:
            return False
        existing.status = "inactive"
        await session.commit()
        return True

async def update_tenant_member_role(tenant_id: str, user_id: str, role: str) -> TenantMembership | None:
    stored_role = normalize_tenant_role_for_storage(role)
    session_factory = get_session_factory()
    async with session_factory() as session:
        existing = await session.scalar(
            select(TenantMembership).where(
                TenantMembership.tenant_id == tenant_id,
                TenantMembership.user_id == user_id,
                TenantMembership.status == "active",
            )
        )
        if not existing:
            return None
        existing.role = stored_role
        await session.commit()
        await session.refresh(existing)
        return existing


async def set_tenant_member_status(tenant_id: str, user_id: str, status: str) -> TenantMembership | None:
    normalized = status.strip().lower()
    if normalized not in {"active", "inactive"}:
        raise ValueError("Invalid membership status. Allowed values: active, inactive")

    session_factory = get_session_factory()
    async with session_factory() as session:
        existing = await session.scalar(
            select(TenantMembership).where(
                TenantMembership.tenant_id == tenant_id,
                TenantMembership.user_id == user_id,
            )
        )
        if not existing:
            return None
        existing.status = normalized
        await session.commit()
        await session.refresh(existing)
        return existing


async def create_tenant(name: str, owner_user_id: str, slug: str | None = None, tenant_type: str = "general") -> Tenant:
    """Create a new tenant and assign the user as owner."""
    session_factory = get_session_factory()
    async with session_factory() as session:
        tenant_id = f"t-{uuid4().hex[:16]}"
        if not slug:
            slug = f"{_slugify(name)}-{tenant_id[-6:]}"
            
        tenant = Tenant(
            id=tenant_id,
            name=name,
            slug=slug,
            status="active",
            tenant_type=tenant_type,
        )
        session.add(tenant)
        
        membership = TenantMembership(
            tenant_id=tenant_id,
            user_id=owner_user_id,
            role=normalize_tenant_role_for_storage(TENANT_ROLE_ADMIN, preserve_owner=True),
            status="active"
        )
        session.add(membership)
        
        await session.commit()
        await session.refresh(tenant)
        return tenant
