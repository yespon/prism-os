"""Current original membership at resource admission and result delivery."""
from fastapi import HTTPException, Request
from fastapi.routing import APIRoute
from sqlalchemy import select

from app.gateway.authorization import require_tenant_admin, require_tenant_context
from app.integrations.file_access import verify_member
from deerflow.database import user_config_service as service
from deerflow.database.models import TenantMembership
from deerflow.database.tenant_service import tenant_role_has_admin_capability
from deerflow.runtime import ExecutionTrustError


async def current_resource_actor(tenant, actor):
    if not actor:
        raise HTTPException(401, "Current resource identity required")
    try:
        async with service.get_session_factory()() as session:
            await verify_member(session, tenant, actor)
            row = (await session.exec(select(TenantMembership).where(
                TenantMembership.tenant_id == tenant,
                TenantMembership.user_id == actor,
                TenantMembership.status == "active",
            ).execution_options(populate_existing=True))).scalars().first()
            if row is None:
                raise ExecutionTrustError("Current resource member unavailable")
            return {"id": row.id, "role": row.role, "admin": tenant_role_has_admin_capability(row.role)}
    except ExecutionTrustError:
        raise HTTPException(403, "Current resource membership unavailable") from None
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(503, "Current resource authority unavailable") from None


def resource_operation_guard(request, shared=False):
    tenant = require_tenant_context(request)
    actor = getattr(request.state, "user_id", None)

    async def authorize(_phase):
        current = await current_resource_actor(tenant, actor)
        request.state.tenant_role = current["role"]
        if shared:
            require_tenant_admin(request)

    return authorize


class CurrentResourceRoute(APIRoute):
    def get_route_handler(self):
        original = super().get_route_handler()

        async def handler(request: Request):
            tenant = require_tenant_context(request)
            actor = getattr(request.state, "user_id", None)
            before = await current_resource_actor(tenant, actor)
            request.state.tenant_role = before["role"]

            async def delivery():
                try:
                    after = await current_resource_actor(tenant, actor)
                    if (after["id"], after["admin"]) != (before["id"], before["admin"]):
                        raise HTTPException(403, "Current resource scope changed")
                except HTTPException:
                    if request.method not in {"GET", "HEAD", "OPTIONS"}:
                        raise HTTPException(503, {
                            "message": "Resource operation result unavailable after authority changed; inspect current state before retrying",
                            "inspection_required": True,
                        }) from None
                    raise
            try:
                response = await original(request)
            except Exception:
                await delivery()
                raise
            await delivery()
            response.headers["Cache-Control"] = "private, no-store"
            return response

        return handler
