import logging

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from app.gateway.authorization import require_tenant_context
from deerflow.agents.checkpointer import get_checkpointer
from deerflow.config.paths import Paths, get_paths

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/threads", tags=["threads"])


class ThreadDeleteResponse(BaseModel):
    """Response model for thread cleanup."""

    success: bool
    message: str


def _delete_thread_checkpoints(thread_id: str) -> None:
    """Best-effort cleanup for checkpointer state of a thread.

    Some backends expose `delete_thread`; if unavailable or failing, we only log
    and continue deleting local files to avoid breaking existing behavior.
    """
    try:
        checkpointer = get_checkpointer()
    except Exception:
        logger.warning("Failed to initialize checkpointer for thread cleanup: %s", thread_id, exc_info=True)
        return

    delete_thread = getattr(checkpointer, "delete_thread", None)
    if not callable(delete_thread):
        logger.info("Checkpointer does not support thread deletion, skip checkpoint cleanup: %s", thread_id)
        return

    try:
        delete_thread(thread_id)
        logger.info("Deleted checkpointer state for %s", thread_id)
    except Exception:
        logger.warning("Failed to delete checkpointer state for %s", thread_id, exc_info=True)


def _delete_thread_data(
    user_id: str,
    thread_id: str,
    *,
    tenant_id: str | None = None,
    paths: Paths | None = None,
) -> ThreadDeleteResponse:
    """Delete local persisted filesystem data for a thread."""
    _delete_thread_checkpoints(thread_id)

    path_manager = paths or get_paths()
    try:
        path_manager.delete_thread_dir(user_id, thread_id, tenant_id=tenant_id)
        # Threads created before tenant-scoped storage was introduced live under
        # the user-only root. Clean that legacy location as part of the same
        # authenticated, user-scoped deletion request.
        if tenant_id is not None:
            path_manager.delete_thread_dir(user_id, thread_id, tenant_id=None)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Failed to delete thread data for %s", thread_id)
        raise HTTPException(status_code=500, detail="Failed to delete local thread data.") from exc

    logger.info("Deleted local thread data for %s", thread_id)
    return ThreadDeleteResponse(success=True, message=f"Deleted local thread data for {thread_id}")


@router.delete("/{thread_id}", response_model=ThreadDeleteResponse)
async def delete_thread_data(thread_id: str, request: Request) -> ThreadDeleteResponse:
    """Delete local persisted filesystem data for a thread.

    This endpoint only cleans DeerFlow-managed thread directories. LangGraph
    thread state deletion remains handled by the LangGraph API.
    """
    require_tenant_context(request)
    return _delete_thread_data(
        request.state.user_id,
        thread_id,
        tenant_id=getattr(request.state, "tenant_id", None),
    )
