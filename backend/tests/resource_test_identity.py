"""Facts for synthetic header authenticators; real revocation tests use fixed apps."""
from native_auth_test_identity import declare_actor
from sqlalchemy import select

from deerflow.database.models import Tenant, TenantMembership


async def persist_fixture_identity(request, factory):
    actor = getattr(request.state, "user_id", None)
    tenant = getattr(request.state, "tenant_id", None)
    if not actor or not tenant:
        return
    declare_actor(actor)
    async with factory() as db:
        if await db.get(Tenant, tenant) is None:
            db.add(Tenant(id=tenant, name=tenant, slug=tenant))
            await db.flush()
        member = (await db.exec(select(TenantMembership).where(
            TenantMembership.tenant_id == tenant, TenantMembership.user_id == actor,
        ))).scalars().first()
        role = getattr(request.state, "tenant_role", "member")
        if member is not None and member.role == role:
            return  # Do not add an unrelated commit to business after_commit fault injection.
        if member is None:
            member = TenantMembership(tenant_id=tenant, user_id=actor)
        member.role = role
        # Never reactivate a revoked membership.
        db.add(member)
        await db.commit()
