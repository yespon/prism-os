"""R2 knowledge tool assembly contracts."""

from unittest.mock import patch

import pytest

from app.knowledge.tools import knowledge_search_tool


def test_tool_assembles_with_binding():
    tool = knowledge_search_tool({"tenant_id": "t1", "user_id": "u1"}, ["kb-1"])
    assert tool.name == "knowledge.search"


def test_runtime_provider_wires_knowledge_tools():
    from app.runtime_adapters import _agent_extra_tools

    bound = {"tenant_id": "t1", "user_id": "u1", "meta_info": {"knowledge_base_ids": ["kb-1", "kb-2"]}}
    tools = _agent_extra_tools(bound)
    assert [t.name for t in tools] == ["knowledge.search"]

    unbound = {"tenant_id": "t1", "user_id": "u1", "meta_info": {}}
    assert _agent_extra_tools(unbound) == []
    no_meta = {"tenant_id": "t1", "user_id": "u1"}
    assert _agent_extra_tools(no_meta) == []


def test_provider_registered_with_runtime():
    from app.runtime_adapters import _agent_extra_tools
    from deerflow.runtime import get_agent_tool_provider

    assert get_agent_tool_provider() is _agent_extra_tools


@pytest.mark.anyio
async def test_search_tool_returns_cited_context(tmp_path, monkeypatch):
    monkeypatch.setenv("PRISMOS_HOME", str(tmp_path))
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from sqlmodel import SQLModel
    from sqlmodel.ext.asyncio.session import AsyncSession

    from app.knowledge import KnowledgeService
    from app.knowledge.index import KnowledgeIndex
    from app.knowledge.retrieve import hash_embed_chunks
    from app.models import knowledge as _knowledge_models  # noqa: F401
    from deerflow.database import models as _deerflow_models  # noqa: F401  (tenant_model_configs)

    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'tool.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(SQLModel.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    service = KnowledgeService(factory)
    from app.knowledge import embedding as embedding_module

    monkeypatch.setattr(embedding_module, "get_session_factory", lambda: factory)

    base = await service.create_base("t1", "owner-1", "runbooks")
    document = await service.add_document(
        "t1", base.id, "owner-1", filename="gateway.md", content_type="text/markdown",
        file_object_id="f1", content_hash="h1",
    )
    from app.knowledge.chunk import chunk_text

    chunks = chunk_text("restart the api gateway gracefully with docker compose")
    KnowledgeIndex("t1", base.id).replace_doc_chunks(
        document.id, chunks, hash_embed_chunks(chunks),
    )
    from datetime import UTC, datetime


    async with factory() as session, session.begin():
        await session.execute(
            __import__("app.models.knowledge", fromlist=["KnowledgeDocumentRecord"]).KnowledgeDocumentRecord.__table__.update()
            .where(__import__("app.models.knowledge", fromlist=["KnowledgeDocumentRecord"]).KnowledgeDocumentRecord.id == document.id)
            .values(index_state="ready", indexed_at=datetime.now(UTC))
        )

    with patch("app.knowledge.tools.KnowledgeService", lambda: service):
        tool = knowledge_search_tool({"tenant_id": "t1", "user_id": "owner-1"}, [base.id])
        result = await tool.ainvoke({"query": "how to restart gateway"})
    assert "gateway.md#1" in result
    assert "prismos-kb-citations" in result

    # A stranger with no visibility gets the no-match answer, not content.
    with patch("app.knowledge.tools.KnowledgeService", lambda: service):
        tool = knowledge_search_tool({"tenant_id": "t1", "user_id": "stranger"}, [base.id])
        stranger = await tool.ainvoke({"query": "how to restart gateway"})
    assert "No knowledge matches" in stranger
    await engine.dispose()
