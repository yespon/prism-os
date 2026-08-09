"""Shared upload management logic.

Pure business logic — no FastAPI/HTTP dependencies.
Both Gateway and Client delegate to these functions.
"""

import hashlib
import mimetypes
import os
import re
from pathlib import Path
from urllib.parse import quote

from deerflow.config.paths import VIRTUAL_PATH_PREFIX, get_paths


class PathTraversalError(ValueError):
    """Raised when a path escapes its allowed base directory."""

# thread_id must be alphanumeric, hyphens, underscores, or dots only.
_SAFE_THREAD_ID = re.compile(r"^[a-zA-Z0-9._-]+$")
_CONVERTIBLE_EXTENSIONS = {".pdf", ".ppt", ".pptx", ".xls", ".xlsx", ".doc", ".docx"}


def validate_thread_id(thread_id: str) -> None:
    """Reject thread IDs containing characters unsafe for filesystem paths.

    Raises:
        ValueError: If thread_id is empty or contains unsafe characters.
    """
    if not thread_id or not _SAFE_THREAD_ID.match(thread_id):
        raise ValueError(f"Invalid thread_id: {thread_id!r}")


def get_uploads_dir(thread_id: str, user_id: str = "default", tenant_id: str | None = None) -> Path:
    """Return the uploads directory path for a thread (no side effects)."""
    validate_thread_id(thread_id)
    return get_paths().sandbox_uploads_dir(user_id, thread_id, tenant_id=tenant_id)


def ensure_uploads_dir(thread_id: str, user_id: str = "default", tenant_id: str | None = None) -> Path:
    """Return the uploads directory for a thread, creating it if needed."""
    base = get_uploads_dir(thread_id, user_id, tenant_id=tenant_id)
    base.mkdir(parents=True, exist_ok=True)
    return base


def normalize_filename(filename: str) -> str:
    """Sanitize a filename by extracting its basename.

    Strips any directory components and rejects traversal patterns.

    Args:
        filename: Raw filename from user input (may contain path components).

    Returns:
        Safe filename (basename only).

    Raises:
        ValueError: If filename is empty or resolves to a traversal pattern.
    """
    if not filename:
        raise ValueError("Filename is empty")
    safe = Path(filename).name
    if not safe or safe in {".", ".."}:
        raise ValueError(f"Filename is unsafe: {filename!r}")
    # Reject backslashes — on Linux Path.name keeps them as literal chars,
    # but they indicate a Windows-style path that should be stripped or rejected.
    if "\\" in safe:
        raise ValueError(f"Filename contains backslash: {filename!r}")
    if len(safe.encode("utf-8")) > 255:
        raise ValueError(f"Filename too long: {len(safe)} chars")
    return safe


def claim_unique_filename(name: str, seen: set[str]) -> str:
    """Generate a unique filename by appending ``_N`` suffix on collision.

    Automatically adds the returned name to *seen* so callers don't need to.

    Args:
        name: Candidate filename.
        seen: Set of filenames already claimed (mutated in place).

    Returns:
        A filename not present in *seen* (already added to *seen*).
    """
    if name not in seen:
        seen.add(name)
        return name
    stem, suffix = Path(name).stem, Path(name).suffix
    counter = 1
    candidate = f"{stem}_{counter}{suffix}"
    while candidate in seen:
        counter += 1
        candidate = f"{stem}_{counter}{suffix}"
    seen.add(candidate)
    return candidate


def validate_path_traversal(path: Path, base: Path) -> None:
    """Verify that *path* is inside *base*.

    Raises:
        PathTraversalError: If a path traversal is detected.
    """
    try:
        path.resolve().relative_to(base.resolve())
    except ValueError:
        raise PathTraversalError("Path traversal detected") from None


def list_files_in_dir(directory: Path) -> dict:
    """List files (not directories) in *directory*.

    Args:
        directory: Directory to scan.

    Returns:
        Dict with "files" list (sorted by name) and "count".
        Each file entry has ``size`` as *int* (bytes).  Call
        :func:`enrich_file_listing` to stringify sizes and add
        virtual / artifact URLs.
    """
    if not directory.is_dir():
        return {"files": [], "count": 0}

    files = []
    with os.scandir(directory) as entries:
        for entry in sorted(entries, key=lambda e: e.name):
            if not entry.is_file(follow_symlinks=False):
                continue
            st = entry.stat(follow_symlinks=False)
            files.append({
                "filename": entry.name,
                "size": st.st_size,
                "path": entry.path,
                "extension": Path(entry.name).suffix,
                "modified": st.st_mtime,
            })
    return {"files": files, "count": len(files)}


def delete_file_safe(base_dir: Path, filename: str, *, convertible_extensions: set[str] | None = None) -> dict:
    """Delete a file inside *base_dir* after path-traversal validation.

    If *convertible_extensions* is provided and the file's extension matches,
    the companion ``.md`` file is also removed (if it exists).

    Args:
        base_dir: Directory containing the file.
        filename: Name of file to delete.
        convertible_extensions: Lowercase extensions (e.g. ``{".pdf", ".docx"}``)
            whose companion markdown should be cleaned up.

    Returns:
        Dict with success and message.

    Raises:
        FileNotFoundError: If the file does not exist.
        PathTraversalError: If path traversal is detected.
    """
    file_path = (base_dir / filename).resolve()
    validate_path_traversal(file_path, base_dir)

    if not file_path.is_file():
        raise FileNotFoundError(f"File not found: {filename}")

    file_path.unlink()
    deleted_files = [filename]
    cascaded_deleted_files: list[str] = []

    # Clean up companion markdown generated during upload conversion.
    if convertible_extensions and file_path.suffix.lower() in convertible_extensions:
        md_filename = file_path.with_suffix(".md").name
        md_path = file_path.with_suffix(".md")
        if md_path.exists() and md_path.is_file():
            md_path.unlink()
            deleted_files.append(md_filename)
            cascaded_deleted_files.append(md_filename)

    return {
        "success": True,
        "message": f"Deleted {filename}",
        "deleted_files": deleted_files,
        "cascaded_deleted_files": cascaded_deleted_files,
    }


def upload_artifact_url(thread_id: str, filename: str) -> str:
    """Build the artifact URL for a file in a thread's uploads directory.

    *filename* is percent-encoded so that spaces, ``#``, ``?`` etc. are safe.
    """
    return f"/api/threads/{thread_id}/artifacts{VIRTUAL_PATH_PREFIX}/uploads/{quote(filename, safe='')}"


def upload_virtual_path(filename: str) -> str:
    """Build the virtual path for a file in the uploads directory."""
    return f"{VIRTUAL_PATH_PREFIX}/uploads/{filename}"


def upload_attachment_id(thread_id: str, filename: str) -> str:
    """Build a stable attachment id for a file in a thread uploads directory."""
    digest = hashlib.sha1(f"{thread_id}:{filename}".encode()).hexdigest()[:16]
    return f"att-{digest}"


def guess_content_type(filename: str) -> str:
    """Return best-effort content type for a filename."""
    guessed, _ = mimetypes.guess_type(filename)
    return guessed or "application/octet-stream"


def build_derived_files(directory: Path, thread_id: str, filename: str) -> list[dict[str, object]]:
    """Return derived files metadata for convertible sources.

    Currently maps convertible source files to their markdown companion if it exists.
    """
    suffix = Path(filename).suffix.lower()
    if suffix not in _CONVERTIBLE_EXTENSIONS:
        return []

    md_filename = Path(filename).with_suffix(".md").name
    md_path = directory / md_filename
    if not md_path.is_file():
        return []

    return [
        {
            "attachment_id": upload_attachment_id(thread_id, md_filename),
            "filename": md_filename,
            "virtual_path": upload_virtual_path(md_filename),
            "artifact_url": upload_artifact_url(thread_id, md_filename),
            "content_type": guess_content_type(md_filename),
            "is_derived": True,
            "source_filename": filename,
            "source_attachment_id": upload_attachment_id(thread_id, filename),
        }
    ]


def _detect_markdown_source_filename(directory: Path, filename: str) -> str | None:
    """Best-effort source file detection for markdown derived uploads."""
    if Path(filename).suffix.lower() != ".md":
        return None

    stem = Path(filename).stem
    for ext in sorted(_CONVERTIBLE_EXTENSIONS):
        candidate = directory / f"{stem}{ext}"
        if candidate.is_file():
            return candidate.name
    return None


def enrich_file_listing(result: dict, thread_id: str) -> dict:
    """Add virtual paths, artifact URLs, and stringify sizes on a listing result.

    Mutates *result* in place and returns it for convenience.
    """
    for f in result["files"]:
        filename = f["filename"]
        parent_dir = Path(f["path"]).parent
        source_filename = _detect_markdown_source_filename(parent_dir, filename)
        f["size"] = str(f["size"])
        f["original_filename"] = filename
        f["stored_filename"] = filename
        f["attachment_id"] = upload_attachment_id(thread_id, filename)
        f["virtual_path"] = upload_virtual_path(filename)
        f["artifact_url"] = upload_artifact_url(thread_id, filename)
        f["content_type"] = guess_content_type(filename)
        f["is_derived"] = source_filename is not None
        f["source_filename"] = source_filename
        f["source_attachment_id"] = (
            upload_attachment_id(thread_id, source_filename) if source_filename else None
        )
        f["derived_files"] = build_derived_files(parent_dir, thread_id, filename)
    return result
