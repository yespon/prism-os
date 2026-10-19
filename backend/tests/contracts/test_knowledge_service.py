"""R2 knowledge service contracts: visibility, revocation, lifecycle."""

from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from app.knowledge import KnowledgeError, KnowledgeService
from app.models import knowledge as _knowledge_models  # noqa: F401
from app.models import governance as _governance_models  # noqa: F401


@pytest.fixture
async def service(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'knowledge.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(SQLModel.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    yield KnowledgeService(factory)
    await engine.dispose()


@pytest.mark.anyio
async def test_private_base_visibility_and_member_grant(service):
    base = await service.create_base("t1", "owner-1", "runbooks")
    assert await service.can_read("t1", base.id, "owner-1")
    assert not await service.can_read("t1", base.id, "stranger")
    assert not await service.can_read("t2", base.id, "owner-1"), "cross-tenant read refused"

    await service.grant("t1", base.id, "owner-1", "member-1")
    assert await service.can_read("t1", base.id, "member-1")

    await service.revoke("t1", base.id, "owner-1", "member-1")
    assert not await service.can_read("t1", base.id, "member-1"), "revocation is immediate"


@pytest.mark.anyio
async def test_tenant_visibility_grants_read_not_write(service):
    base = await service.create_base("t1", "owner-1", "shared", visibility="tenant")
    assert await service.can_read("t1", base.id, "anyone-in-t1")
    assert not await service.can_read("t2", base.id, "anyone-in-t2"), "tenant visibility stays in the tenant"
    # A tenant reader cannot grant or revoke.
    with pytest.raises(KnowledgeError):
        await service.grant("t1", base.id, "anyone-in-t1", "friend")
    with pytest.raises(KnowledgeError):
        await service.revoke("t1", base.id, "anyone-in-t1", "member-x")


@pytest.mark.anyio
async def test_document_lifecycle_and_revoked_reader(service):
    base = await service.create_base("t1", "owner-1", "runbooks")
    doc = await service.add_document(
        "t1", base.id, "owner-1", filename="a.md", content_type="text/markdown",
        file_object_id="file_1", content_hash="a" * 64,
    )
    assert doc.index_state == "pending"

    await service.grant("t1", base.id, "owner-1", "member-1")
    listed = await service.list_documents("t1", base.id, "member-1")
    assert [d.id for d in listed] == [doc.id]

    # Revoke -> member can no longer list or get.
    await service.revoke("t1", base.id, "owner-1", "member-1")
    with pytest.raises(KnowledgeError):
        await service.list_documents("t1", base.id, "member-1")
    with pytest.raises(KnowledgeError):
        await service.get_document("t1", base.id, "member-1", doc.id)


@pytest.mark.anyio
async def test_document_delete_scopes(service):
    base = await service.create_base("t1", "owner-1", "runbooks")
    doc = await service.add_document(
        "t1", base.id, "owner-1", filename="b.md", content_type="text/markdown",
        file_object_id="file_2", content_hash="b" * 64,
    )
    with pytest.raises(KnowledgeError):
        await service.delete_document("t1", base.id, "stranger", doc.id)
    await service.delete_document("t1", base.id, "owner-1", doc.id)
    with pytest.raises(KnowledgeError):
        await service.get_document("t1", base.id, "owner-1", doc.id)


@pytest.mark.anyio
async def test_cross_tenant_document_access_refused(service):
    base = await service.create_base("t1", "owner-1", "runbooks")
    doc = await service.add_document(
        "t1", base.id, "owner-1", filename="c.md", content_type="text/markdown",
        file_object_id="file_3", content_hash="c" * 64,
    )
    # Same user id in another tenant must not see it.
    with pytest.raises(KnowledgeError):
        await service.get_document("t2", base.id, "owner-1", doc.id)
    with pytest.raises(KnowledgeError):
        await service.list_documents("t2", base.id, "owner-1")
