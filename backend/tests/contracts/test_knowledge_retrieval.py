"""R2 retrieval contracts: citations, readiness gate, revocation-immediate loss."""

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from app.knowledge import KnowledgeService
from app.knowledge.index import KnowledgeIndex
from app.knowledge.retrieve import (
    append_citations_marker,
    format_context,
    retrieve_chunks,
    strip_citations_marker,
)
from app.models import governance as _governance_models  # noqa: F401
from app.models import knowledge as _knowledge_models  # noqa: F401


@pytest.fixture
async def service(tmp_path, monkeypatch):
    monkeypatch.setenv("PRISMOS_HOME", str(tmp_path / "home"))
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'retrieval.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(SQLModel.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    # Retrieval resolves the embedding model through the same factory: with no
    # embedding row configured it degrades to the deterministic hash vectors.
    from app.knowledge import embedding as embedding_module

    monkeypatch.setattr(embedding_module, "get_session_factory", lambda: factory)
    yield KnowledgeService(factory)
    await engine.dispose()


async def _seed(service, texts: dict[str, str]) -> tuple[str, list[str]]:
    base = await service.create_base("t1", "owner-1", "runbooks")
    doc_ids = []
    for name, text in texts.items():
        document = await service.add_document(
            "t1", base.id, "owner-1", filename=name, content_type="text/markdown",
            file_object_id=f"file-{name}", content_hash="h" + name,
        )
        from app.knowledge.chunk import chunk_text
        from app.knowledge.retrieve import hash_embed_chunks

        chunks = chunk_text(text)
        index = KnowledgeIndex("t1", base.id)
        index.replace_doc_chunks(
            document.id, chunks, hash_embed_chunks(chunks),
            metadata=[{"version": document.version}] * len(chunks),
        )
        # Simulate the upload pipeline marking the document ready.
        from datetime import UTC, datetime

        from sqlalchemy import update

        from app.models.knowledge import KnowledgeDocumentRecord

        async with service._session_factory() as session, session.begin():
            await session.execute(
                update(KnowledgeDocumentRecord)
                .where(KnowledgeDocumentRecord.id == document.id)
                .values(index_state="ready", indexed_at=datetime.now(UTC))
            )
        doc_ids.append(document.id)
    return base.id, doc_ids


@pytest.mark.anyio
async def test_retrieval_returns_cited_chunks(service):
    kb_id, doc_ids = await _seed(service, {
        "gateway.md": "restart the api gateway gracefully with docker compose",
        "database.md": "vacuum the postgres database weekly",
    })
    chunks = await retrieve_chunks(service, "t1", "owner-1", "how to restart gateway", [kb_id])
    assert chunks, "expected at least one chunk"
    assert chunks[0].citation.doc_id in doc_ids
    assert chunks[0].citation.content_hash.startswith("h")

    context = format_context(chunks, kb_names={kb_id: "runbooks"})
    assert "gateway.md#1" in context
    assert "<!--prismos-kb-citations:" in context
    assert strip_citations_marker(context) != context


@pytest.mark.anyio
async def test_revoked_member_loses_retrieval_immediately(service):
    kb_id, _ = await _seed(service, {"secret.md": "rotate the master key quarterly"})
    await service.grant("t1", kb_id, "owner-1", "member-1")
    before = await retrieve_chunks(service, "t1", "member-1", "rotate key", [kb_id])
    assert before, "granted member retrieves"

    await service.revoke("t1", kb_id, "owner-1", "member-1")
    after = await retrieve_chunks(service, "t1", "member-1", "rotate key", [kb_id])
    assert after == [], "revoked member retrieves nothing - immediate loss"


@pytest.mark.anyio
async def test_cross_tenant_retrieval_refused(service):
    kb_id, _ = await _seed(service, {"a.md": "tenant one content"})
    other = await retrieve_chunks(service, "t2", "owner-1", "tenant one content", [kb_id])
    assert other == []


@pytest.mark.anyio
async def test_only_ready_documents_participate(service):
    base = await service.create_base("t1", "owner-1", "kb")
    document = await service.add_document(
        "t1", base.id, "owner-1", filename="pending.md", content_type="text/markdown",
        file_object_id="f1", content_hash="hpending",
    )
    # Document stays pending (never indexed): retrieval must not surface it
    # even if an index entry somehow existed.
    from app.knowledge.chunk import chunk_text
    from app.knowledge.retrieve import hash_embed_chunks

    chunks = chunk_text("pending document content")
    KnowledgeIndex("t1", base.id).replace_doc_chunks(
        document.id, chunks, hash_embed_chunks(chunks),
    )
    hits = await retrieve_chunks(service, "t1", "owner-1", "pending document content", [base.id])
    assert hits == [], "pending document must not participate in retrieval"


def test_marker_roundtrip():
    body = "text"
    marked = append_citations_marker(body, [{"doc_id": "d1", "filename": "a.md"}])
    assert strip_citations_marker(marked) == body
