"""Knowledge base and document API (R2 week 1: upload -> index loop).

All endpoints resolve tenant/user from the authenticated request context
and delegate visibility, membership and lifecycle to KnowledgeService.
Indexing runs inline in this first slice: parse -> chunk -> embed ->
store in the per-KB index, with the document index_state machine
(pending -> indexing -> ready | failed) persisted before and after.
"""

from datetime import UTC, datetime
from hashlib import sha256
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.gateway.authorization import require_tenant_context
from app.knowledge import KnowledgeError, KnowledgeService
from app.models.files import FileObject
from deerflow.database.session import get_session, get_session_factory

router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])


def _service() -> KnowledgeService:
    return KnowledgeService()


@router.get("/bases")
async def list_bases(request: Request, _ctx: None = Depends(require_tenant_context)) -> dict:
    tenant_id = request.state.tenant_id
    user_id = request.state.user_id
    bases = await _service().list_visible(tenant_id, user_id)
    return {"bases": [
        {"id": b.id, "name": b.name, "visibility": b.visibility,
         "owner_user_id": b.owner_user_id, "created_at": b.created_at}
        for b in bases
    ]}


@router.post("/bases", status_code=201)
async def create_base(request: Request, body: dict, _ctx: None = Depends(require_tenant_context)) -> dict:
    tenant_id = request.state.tenant_id
    user_id = request.state.user_id
    name = body.get("name")
    if not isinstance(name, str):
        raise HTTPException(400, "name is required")
    try:
        base = await _service().create_base(
            tenant_id, user_id, name, visibility=body.get("visibility", "private"))
    except KnowledgeError as error:
        raise HTTPException(400, str(error)) from error
    return {"id": base.id, "name": base.name, "visibility": base.visibility}


@router.post("/bases/{kb_id}/members", status_code=201)
async def grant_member(kb_id: str, request: Request, body: dict,
                       _ctx: None = Depends(require_tenant_context)) -> dict:
    tenant_id = request.state.tenant_id
    user_id = request.state.user_id
    grantee = body.get("user_id")
    if not isinstance(grantee, str) or not grantee:
        raise HTTPException(400, "user_id is required")
    try:
        member = await _service().grant(tenant_id, kb_id, user_id, grantee)
    except KnowledgeError as error:
        raise HTTPException(404 if "not found" in str(error) else 400, str(error)) from error
    return {"kb_id": kb_id, "user_id": member.user_id}


@router.delete("/bases/{kb_id}/members")
async def revoke_member(kb_id: str, request: Request, body: dict | None = None,
                        user_id: str = Query(default=None),
                        _ctx: None = Depends(require_tenant_context)) -> dict:
    tenant_id = request.state.tenant_id
    owner_id = request.state.user_id
    grantee = user_id or (body or {}).get("user_id")
    if not isinstance(grantee, str) or not grantee:
        raise HTTPException(400, "user_id is required")
    try:
        await _service().revoke(tenant_id, kb_id, owner_id, grantee)
    except KnowledgeError as error:
        raise HTTPException(404 if "not found" in str(error) else 400, str(error)) from error
    return {"revoked": grantee}


@router.get("/bases/{kb_id}/documents")
async def list_documents(kb_id: str, request: Request, _ctx: None = Depends(require_tenant_context)) -> dict:
    try:
        documents = await _service().list_documents(request.state.tenant_id, kb_id, request.state.user_id)
    except KnowledgeError as error:
        raise HTTPException(404, str(error)) from error
    return {"documents": [_document_response(d) for d in documents]}


@router.post("/bases/{kb_id}/documents", status_code=201)
async def upload_document(
    kb_id: str,
    request: Request,
    file: UploadFile,
    db: AsyncSession = Depends(get_session),
    _ctx: None = Depends(require_tenant_context),
) -> dict:
    tenant_id = request.state.tenant_id
    user_id = request.state.user_id
    if not file.filename:
        raise HTTPException(400, "No filename provided")

    MAX_SIZE = 50 * 1024 * 1024
    content = await file.read()
    if len(content) > MAX_SIZE:
        raise HTTPException(413, "File exceeds maximum size of 50 MB")
    content_hash = sha256(content).hexdigest()
    content_type = file.content_type or "application/octet-stream"

    # Store bytes through the existing storage/FileObject seam.
    from app.gateway.routers.files import get_storage_driver

    storage = get_storage_driver()
    file_id = str(uuid4())
    object_key = storage._compute_object_key(tenant_id, file_id)
    await storage.put_object(object_key, content, content_type)
    file_obj = FileObject(
        id=file_id, tenant_id=tenant_id, owner_user_id=user_id,
        display_name=file.filename, original_filename=file.filename,
        mime_type=content_type, object_key=object_key,
        size_bytes=len(content), checksum=content_hash,
        storage_backend=storage._config.backend, source_type="business_attachment",
        created_by=user_id, created_by_role="user",
    )
    db.add(file_obj)
    await db.commit()

    try:
        document = await _service().add_document(
            tenant_id, kb_id, user_id, filename=file.filename,
            content_type=content_type, file_object_id=file_id, content_hash=content_hash,
        )
    except KnowledgeError as error:
        raise HTTPException(404, str(error)) from error

    # Inline index pipeline for the first slice: parse -> chunk -> embed -> store.
    document = await _index_document(storage, tenant_id, kb_id, document)
    return _document_response(document)


@router.get("/bases/{kb_id}/documents/{doc_id}")
async def get_document_status(
    kb_id: str, doc_id: str, request: Request, _ctx: None = Depends(require_tenant_context)
) -> dict:
    try:
        document = await _service().get_document(
            request.state.tenant_id, kb_id, request.state.user_id, doc_id)
    except KnowledgeError as error:
        raise HTTPException(404, str(error)) from error
    return _document_response(document)


@router.delete("/bases/{kb_id}/documents/{doc_id}", status_code=204)
async def delete_document(
    kb_id: str, doc_id: str, request: Request, _ctx: None = Depends(require_tenant_context)
) -> None:
    try:
        await _service().delete_document(request.state.tenant_id, kb_id, request.state.user_id, doc_id)
    except KnowledgeError as error:
        raise HTTPException(404, str(error)) from error
    # Invalidate the index sidecar for the deleted document.
    from app.knowledge.index import KnowledgeIndex

    KnowledgeIndex(request.state.tenant_id, kb_id).delete_doc(doc_id)


def _document_response(d) -> dict:
    return {
        "id": d.id, "kb_id": d.kb_id, "filename": d.filename, "content_type": d.content_type,
        "file_object_id": d.file_object_id, "version": d.version, "content_hash": d.content_hash,
        "index_state": d.index_state, "index_error": d.index_error, "indexed_at": d.indexed_at,
    }


async def _index_document(storage, tenant_id: str, kb_id: str, document) -> object:
    """Run the inline index pipeline and persist the index_state machine."""
    from app.knowledge.chunk import chunk_text
    from app.knowledge.index import KnowledgeIndex
    from app.knowledge.parse import parse_document
    from app.models.knowledge import KnowledgeDocumentRecord

    async with get_session_factory()() as session, session.begin():
        row = await session.get(KnowledgeDocumentRecord, document.id)
        if row is None:
            raise HTTPException(404, "document record vanished")
        row.index_state = "indexing"
        await session.commit()

    error: str | None = None
    try:
        object_key = storage._compute_object_key(tenant_id, document.file_object_id)
        content = await storage.get_object(object_key)
        import tempfile
        from pathlib import Path as _Path

        suffix = _Path(document.filename).suffix
        with tempfile.NamedTemporaryFile(suffix=suffix) as tmp:
            tmp.write(content)
            tmp.flush()
            text = parse_document(_Path(tmp.name))
        chunks = chunk_text(text)
        if chunks:
            from app.knowledge.embedding import embed_for_tenant

            embeddings = await embed_for_tenant(tenant_id, chunks)
            index = KnowledgeIndex(tenant_id, kb_id)
            index.replace_doc_chunks(
                document.id, chunks, embeddings,
                metadata=[{"version": document.version, "content_hash": document.content_hash}] * len(chunks),
            )
    except Exception as exc:  # noqa: BLE001 - surfaced through index_state
        error = f"{type(exc).__name__}: {exc}"

    async with get_session_factory()() as session, session.begin():
        row = await session.get(KnowledgeDocumentRecord, document.id)
        if row is None:
            raise HTTPException(404, "document record vanished")
        if error is None:
            row.index_state = "ready"
            row.indexed_at = datetime.now(UTC)
        else:
            row.index_state = "failed"
            row.index_error = error[:1000]
        await session.commit()
        row_index_state, row_index_error, row_indexed_at = row.index_state, row.index_error, row.indexed_at

    document.index_state = row_index_state
    document.index_error = row_index_error
    document.indexed_at = row_indexed_at
    return document

