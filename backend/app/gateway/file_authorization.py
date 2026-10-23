"""Request-time access to original thread/member facts, including legacy proof."""

from fastapi import HTTPException

from app.gateway.authorization import require_tenant_context
from app.integrations.file_access import verify_member
from app.platform.execution.trust import ThreadBindingRepository
from deerflow.database.session import get_session_factory
from deerflow.runtime import ExecutionTrustError


async def require_current_member(request, *, factory=None):
    tenant = require_tenant_context(request)
    actor = getattr(request.state, "user_id", None)
    if not isinstance(actor, str) or not actor:
        raise HTTPException(401, "Authentication required")
    try:
        async with (factory or get_session_factory())() as session:
            await verify_member(session, tenant, actor)
    except ExecutionTrustError:
        raise HTTPException(403, "Current tenant membership unavailable") from None
    return tenant, actor


async def require_thread_access(request, thread, *, factory=None):
    factory = factory or get_session_factory()
    tenant, actor = await require_current_member(request, factory=factory)
    from app.gateway.routers.langgraph_proxy import _binding_or_legacy

    try:
        binding = await _binding_or_legacy(ThreadBindingRepository(factory), thread, tenant, actor, request)
    except ExecutionTrustError:
        raise HTTPException(404, "Thread unavailable") from None
    # The legacy upstream round-trip must not outlive a membership withdrawal.
    await require_current_member(request, factory=factory)
    return binding
