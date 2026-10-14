"""Upload router for handling file uploads."""

import logging
import os
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from pydantic import BaseModel

from app.gateway.audit import record_audit_event
from app.gateway.file_authorization import require_thread_access
from deerflow.config.paths import get_paths
from deerflow.sandbox.sandbox_provider import get_sandbox_provider
from deerflow.uploads.manager import (
    PathTraversalError,
    build_derived_files,
    claim_unique_filename,
    delete_file_safe,
    enrich_file_listing,
    ensure_uploads_dir,
    get_uploads_dir,
    guess_content_type,
    list_files_in_dir,
    normalize_filename,
    upload_artifact_url,
    upload_attachment_id,
    upload_virtual_path,
)
from deerflow.utils.file_conversion import CONVERTIBLE_EXTENSIONS, convert_file_to_markdown

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/threads/{thread_id}/uploads", tags=["uploads"])


class UploadResponse(BaseModel):
    """Response model for file upload."""

    success: bool
    files: list[dict[str, object]]
    message: str


def _resolve_filename_by_attachment_id(thread_id: str, uploads_dir: os.PathLike[str] | str, attachment_id: str) -> str | None:
    """Resolve a thread upload filename from its stable attachment id."""
    if not attachment_id:
        return None

    uploads_path = Path(uploads_dir)
    result = list_files_in_dir(uploads_path)
    for file_info in result.get("files", []):
        filename = file_info.get("filename")
        if isinstance(filename, str) and upload_attachment_id(thread_id, filename) == attachment_id:
            return filename
    return None


def _should_sync_virtual_file_to_sandbox(sandbox_id: str) -> bool:
    """Return True when sandbox file sync should run for the given sandbox id.

    Local sandbox ids can be either "local" (shared) or "local-<hash>"
    (thread-bound). Both execute directly on host paths and must not receive
    virtual `/mnt/user-data/...` writes.
    """
    return not sandbox_id.startswith("local")


def _parse_positive_int_env(name: str) -> int | None:
    value = os.getenv(name)
    if value is None or not value.strip():
        return None
    try:
        parsed = int(value)
    except ValueError:
        logger.warning("Invalid integer env for %s: %r", name, value)
        return None
    if parsed <= 0:
        return None
    return parsed


def _calculate_user_upload_bytes(user_id: str, tenant_id: str | None = None) -> int:
    users_root = get_paths().user_threads_dir(user_id, tenant_id=tenant_id)
    if not users_root.exists() or not users_root.is_dir():
        return 0

    total = 0
    for thread_dir in users_root.iterdir():
        uploads_dir = thread_dir / "user-data" / "uploads"
        if not uploads_dir.exists() or not uploads_dir.is_dir():
            continue
        for entry in uploads_dir.rglob("*"):
            if not entry.is_file():
                continue
            try:
                total += entry.stat().st_size
            except OSError:
                continue
    return total


def _enforce_upload_quota(user_id: str, thread_id: str, incoming_bytes: int, tenant_id: str | None = None) -> None:
    if tenant_id is None:
        current_total = _calculate_user_upload_bytes(user_id)
    else:
        current_total = _calculate_user_upload_bytes(user_id, tenant_id=tenant_id)
    projected = current_total + incoming_bytes

    hard_limit = _parse_positive_int_env("ADMIN_UPLOAD_BYTES_HARD_LIMIT")
    if hard_limit is not None and projected > hard_limit:
        record_audit_event(
            "upload.quota.blocked",
            actor_id=user_id,
            target_user_id=user_id,
            severity="warning",
            metadata={
                "thread_id": thread_id,
                "current_bytes": current_total,
                "incoming_bytes": incoming_bytes,
                "projected_bytes": projected,
                "hard_limit": hard_limit,
            },
        )
        raise HTTPException(status_code=403, detail="Upload quota exceeded")

    soft_limit = _parse_positive_int_env("ADMIN_UPLOAD_BYTES_SOFT_LIMIT")
    if soft_limit is not None and projected > soft_limit:
        logger.warning(
            "Upload soft limit exceeded for user %s: projected=%s soft_limit=%s",
            user_id,
            projected,
            soft_limit,
        )
        record_audit_event(
            "upload.quota.soft_limit_exceeded",
            actor_id=user_id,
            target_user_id=user_id,
            severity="warning",
            metadata={
                "thread_id": thread_id,
                "current_bytes": current_total,
                "incoming_bytes": incoming_bytes,
                "projected_bytes": projected,
                "soft_limit": soft_limit,
            },
        )




@router.post("", response_model=UploadResponse)
async def upload_files(
    thread_id: str,
    request: Request,
    files: list[UploadFile] = File(...),
) -> UploadResponse:
    """Upload multiple files to a thread's uploads directory."""
    await require_thread_access(request, thread_id)
    if not files:
        raise HTTPException(status_code=400, detail="No files provided")

    try:
        uploads_dir = ensure_uploads_dir(
            thread_id,
            user_id=request.state.user_id,
            tenant_id=getattr(request.state, "tenant_id", None),
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    sandbox_uploads = get_paths().sandbox_uploads_dir(
        request.state.user_id,
        thread_id,
        tenant_id=getattr(request.state, "tenant_id", None),
    )
    uploaded_files = []

    prepared_files: list[tuple[str, str, bytes, str]] = []
    claimed_filenames = {
        f.get("filename")
        for f in list_files_in_dir(uploads_dir).get("files", [])
        if isinstance(f.get("filename"), str)
    }
    incoming_bytes = 0
    for file in files:
        if not file.filename:
            continue
        try:
            normalized_filename = normalize_filename(file.filename)
            safe_filename = claim_unique_filename(normalized_filename, claimed_filenames)
        except ValueError:
            logger.warning(f"Skipping file with unsafe filename: {file.filename!r}")
            continue
        content = await file.read()
        prepared_files.append(
            (
                file.filename,
                safe_filename,
                content,
                file.content_type or guess_content_type(safe_filename),
            )
        )
        incoming_bytes += len(content)

    _enforce_upload_quota(
        request.state.user_id,
        thread_id,
        incoming_bytes,
        tenant_id=getattr(request.state, "tenant_id", None),
    )

    sandbox_provider = get_sandbox_provider()
    sandbox_id = sandbox_provider.acquire(
        thread_id,
        user_id=request.state.user_id,
        tenant_id=getattr(request.state, "tenant_id", None),
    )
    sandbox = sandbox_provider.get(sandbox_id)

    for original_filename, safe_filename, content, content_type in prepared_files:

        try:
            file_path = uploads_dir / safe_filename
            file_path.write_bytes(content)

            virtual_path = upload_virtual_path(safe_filename)

            if _should_sync_virtual_file_to_sandbox(sandbox_id):
                sandbox.update_file(virtual_path, content)

            file_info = {
                "attachment_id": upload_attachment_id(thread_id, safe_filename),
                "filename": safe_filename,
                "original_filename": original_filename,
                "stored_filename": safe_filename,
                "size": str(len(content)),
                "path": str(sandbox_uploads / safe_filename),
                "virtual_path": virtual_path,
                "artifact_url": upload_artifact_url(thread_id, safe_filename),
                "content_type": content_type,
                "derived_files": [],
            }

            logger.info(f"Saved file: {safe_filename} ({len(content)} bytes) to {file_info['path']}")

            file_ext = file_path.suffix.lower()
            if file_ext in CONVERTIBLE_EXTENSIONS:
                md_path = await convert_file_to_markdown(file_path)
                if md_path:
                    md_virtual_path = upload_virtual_path(md_path.name)

                    if _should_sync_virtual_file_to_sandbox(sandbox_id):
                        sandbox.update_file(md_virtual_path, md_path.read_bytes())

                    file_info["markdown_file"] = md_path.name
                    file_info["markdown_path"] = str(sandbox_uploads / md_path.name)
                    file_info["markdown_virtual_path"] = md_virtual_path
                    file_info["markdown_artifact_url"] = upload_artifact_url(thread_id, md_path.name)
                    file_info["derived_files"] = build_derived_files(uploads_dir, thread_id, safe_filename)

            uploaded_files.append(file_info)

        except Exception as e:
            logger.error(f"Failed to upload {safe_filename}: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to upload {safe_filename}: {str(e)}")

    if uploaded_files:
        record_audit_event(
            "upload.files.uploaded",
            actor_id=request.state.user_id,
            target_user_id=request.state.user_id,
            severity="info",
            metadata={
                "thread_id": thread_id,
                "tenant_id": getattr(request.state, "tenant_id", None),
                "file_count": len(uploaded_files),
                "filenames": [f.get("filename") for f in uploaded_files],
            },
        )

    return UploadResponse(
        success=True,
        files=uploaded_files,
        message=f"Successfully uploaded {len(uploaded_files)} file(s)",
    )


@router.get("/list", response_model=dict)
async def list_uploaded_files(thread_id: str, request: Request) -> dict:
    """List all files in a thread's uploads directory."""
    await require_thread_access(request, thread_id)
    try:
        uploads_dir = get_uploads_dir(
            thread_id,
            user_id=request.state.user_id,
            tenant_id=getattr(request.state, "tenant_id", None),
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    result = list_files_in_dir(uploads_dir)
    enrich_file_listing(result, thread_id)

    # Gateway additionally includes the sandbox-relative path.
    sandbox_uploads = get_paths().sandbox_uploads_dir(
        request.state.user_id,
        thread_id,
        tenant_id=getattr(request.state, "tenant_id", None),
    )
    for f in result["files"]:
        f["path"] = str(sandbox_uploads / f["filename"])

    return result


@router.delete("/{filename}")
async def delete_uploaded_file(thread_id: str, filename: str, request: Request) -> dict:
    """Delete a file from a thread's uploads directory."""
    await require_thread_access(request, thread_id)
    try:
        uploads_dir = get_uploads_dir(
            thread_id,
            user_id=request.state.user_id,
            tenant_id=getattr(request.state, "tenant_id", None),
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    try:
        result = delete_file_safe(uploads_dir, filename, convertible_extensions=CONVERTIBLE_EXTENSIONS)
        record_audit_event(
            "upload.file.deleted",
            actor_id=request.state.user_id,
            target_user_id=request.state.user_id,
            severity="info",
            metadata={
                "thread_id": thread_id,
                "tenant_id": getattr(request.state, "tenant_id", None),
                "filename": filename,
                "deleted_files": result.get("deleted_files", []),
                "cascaded_deleted_files": result.get("cascaded_deleted_files", []),
            },
        )
        return result
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"File not found: {filename}")
    except PathTraversalError:
        raise HTTPException(status_code=400, detail="Invalid path")
    except Exception as e:
        logger.error(f"Failed to delete {filename}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to delete {filename}: {str(e)}")


@router.delete("/by-attachment/{attachment_id}")
async def delete_uploaded_file_by_attachment_id(thread_id: str, attachment_id: str, request: Request) -> dict:
    """Delete a file from a thread's uploads directory by attachment id."""
    await require_thread_access(request, thread_id)
    try:
        uploads_dir = get_uploads_dir(
            thread_id,
            user_id=request.state.user_id,
            tenant_id=getattr(request.state, "tenant_id", None),
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    filename = _resolve_filename_by_attachment_id(thread_id, uploads_dir, attachment_id)
    if filename is None:
        raise HTTPException(status_code=404, detail=f"Attachment not found: {attachment_id}")

    try:
        result = delete_file_safe(uploads_dir, filename, convertible_extensions=CONVERTIBLE_EXTENSIONS)
        record_audit_event(
            "upload.file.deleted",
            actor_id=request.state.user_id,
            target_user_id=request.state.user_id,
            severity="info",
            metadata={
                "thread_id": thread_id,
                "tenant_id": getattr(request.state, "tenant_id", None),
                "filename": filename,
                "attachment_id": attachment_id,
                "deleted_files": result.get("deleted_files", []),
                "cascaded_deleted_files": result.get("cascaded_deleted_files", []),
            },
        )
        return result
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"File not found: {filename}")
    except PathTraversalError:
        raise HTTPException(status_code=400, detail="Invalid path")
    except Exception as e:
        logger.error(f"Failed to delete {filename} by attachment_id={attachment_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to delete {filename}: {str(e)}")
