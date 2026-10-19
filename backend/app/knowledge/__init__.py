"""Tenant-scoped knowledge base service (R2).

Visibility model: owner + explicit members always; ``tenant`` visibility
additionally grants read to every member of the same tenant. Writes
(upload/delete/grant) stay with the owner and explicit members. Every
query filters by tenant; authorization is checked against the current
membership on every call - revocation takes effect immediately because
no authorization is cached.
"""

from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.knowledge import (
    KnowledgeBaseRecord,
    KnowledgeDocumentRecord,
    KnowledgeMemberRecord,
)
from deerflow.database.session import get_session_factory


class KnowledgeError(Exception):
    """Domain error with a user-presentable message."""


class KnowledgeService:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession] | None = None) -> None:
        self._session_factory = session_factory or get_session_factory()

    # ---- visibility ----

    @staticmethod
    async def _visible_base(session: AsyncSession, tenant_id: str, kb_id: str, user_id: str) -> KnowledgeBaseRecord | None:
        base = await session.get(KnowledgeBaseRecord, kb_id)
        if base is None or base.tenant_id != tenant_id:
            return None
        if base.owner_user_id == user_id:
            return base
        member = (await session.exec(
            select(KnowledgeMemberRecord).where(
                KnowledgeMemberRecord.tenant_id == tenant_id,
                KnowledgeMemberRecord.kb_id == kb_id,
                KnowledgeMemberRecord.user_id == user_id,
            )
        )).first()
        if member is not None:
            return base
        if base.visibility == "tenant":
            return base
        return None

    async def list_visible(self, tenant_id: str, user_id: str) -> list[KnowledgeBaseRecord]:
        async with self._session_factory() as session:
            owned = (await session.exec(
                select(KnowledgeBaseRecord).where(
                    KnowledgeBaseRecord.tenant_id == tenant_id,
                    KnowledgeBaseRecord.owner_user_id == user_id,
                )
            )).all()
            member_rows = (await session.exec(
                select(KnowledgeBaseRecord).join(KnowledgeMemberRecord).where(
                    KnowledgeBaseRecord.tenant_id == tenant_id,
                    KnowledgeMemberRecord.tenant_id == tenant_id,
                    KnowledgeMemberRecord.user_id == user_id,
                )
            )).all()
            tenant_wide = (await session.exec(
                select(KnowledgeBaseRecord).where(
                    KnowledgeBaseRecord.tenant_id == tenant_id,
                    KnowledgeBaseRecord.visibility == "tenant",
                )
            )).all()
            merged: dict[str, KnowledgeBaseRecord] = {}
            for row in (*owned, *member_rows, *tenant_wide):
                merged[row.id] = row
            return sorted(merged.values(), key=lambda row: row.created_at)

    async def can_read(self, tenant_id: str, kb_id: str, user_id: str) -> bool:
        async with self._session_factory() as session:
            return await self._visible_base(session, tenant_id, kb_id, user_id) is not None

    # ---- bases ----

    async def create_base(self, tenant_id: str, owner_user_id: str, name: str, *, visibility: str = "private") -> KnowledgeBaseRecord:
        if visibility not in ("private", "tenant"):
            raise KnowledgeError("visibility must be private or tenant")
        if not name.strip():
            raise KnowledgeError("name must not be blank")
        from uuid import uuid4

        record = KnowledgeBaseRecord(
            id=f"kb_{uuid4().hex}", tenant_id=tenant_id, owner_user_id=owner_user_id,
            name=name.strip(), visibility=visibility, created_at=datetime.now(UTC),
        )
        async with self._session_factory() as session, session.begin():
            session.add(record)
        return record

    # ---- members ----

    async def grant(self, tenant_id: str, kb_id: str, grantor: str, grantee: str) -> KnowledgeMemberRecord:
        async with self._session_factory() as session, session.begin():
            base = await session.get(KnowledgeBaseRecord, kb_id)
            if base is None or base.tenant_id != tenant_id or base.owner_user_id != grantor:
                raise KnowledgeError("only the owner can grant access")
            if grantee == grantor:
                raise KnowledgeError("owner already has access")
            existing = (await session.exec(
                select(KnowledgeMemberRecord).where(
                    KnowledgeMemberRecord.tenant_id == tenant_id,
                    KnowledgeMemberRecord.kb_id == kb_id,
                    KnowledgeMemberRecord.user_id == grantee,
                )
            )).first()
            if existing is not None:
                raise KnowledgeError("member already granted")
            from uuid import uuid4

            record = KnowledgeMemberRecord(
                id=f"km_{uuid4().hex}", tenant_id=tenant_id, kb_id=kb_id,
                user_id=grantee, granted_by=grantor, created_at=datetime.now(UTC),
            )
            session.add(record)
        return record

    async def revoke(self, tenant_id: str, kb_id: str, grantor: str, grantee: str) -> None:
        async with self._session_factory() as session, session.begin():
            base = await session.get(KnowledgeBaseRecord, kb_id)
            if base is None or base.tenant_id != tenant_id or base.owner_user_id != grantor:
                raise KnowledgeError("only the owner can revoke access")
            member = (await session.exec(
                select(KnowledgeMemberRecord).where(
                    KnowledgeMemberRecord.tenant_id == tenant_id,
                    KnowledgeMemberRecord.kb_id == kb_id,
                    KnowledgeMemberRecord.user_id == grantee,
                )
            )).first()
            if member is None:
                raise KnowledgeError("member not found")
            await session.delete(member)

    # ---- documents ----

    async def add_document(self, tenant_id: str, kb_id: str, user_id: str, *, filename: str,
                           content_type: str, file_object_id: str, content_hash: str) -> KnowledgeDocumentRecord:
        from uuid import uuid4

        async with self._session_factory() as session, session.begin():
            base = await self._visible_base(session, tenant_id, kb_id, user_id)
            if base is None:
                raise KnowledgeError("knowledge base not found or not readable")
        record = KnowledgeDocumentRecord(
            id=f"kd_{uuid4().hex}", tenant_id=tenant_id, kb_id=kb_id,
            filename=filename, content_type=content_type, file_object_id=file_object_id,
            version=1, content_hash=content_hash, index_state="pending",
            created_at=datetime.now(UTC),
        )
        async with self._session_factory() as session, session.begin():
            session.add(record)
        return record

    async def get_document(self, tenant_id: str, kb_id: str, user_id: str, doc_id: str) -> KnowledgeDocumentRecord:
        async with self._session_factory() as session:
            base = await self._visible_base(session, tenant_id, kb_id, user_id)
            if base is None:
                raise KnowledgeError("knowledge base not found or not readable")
            document = await session.get(KnowledgeDocumentRecord, doc_id)
            if document is None or document.tenant_id != tenant_id or document.kb_id != kb_id:
                raise KnowledgeError("document not found")
            return document

    async def list_documents(self, tenant_id: str, kb_id: str, user_id: str) -> list[KnowledgeDocumentRecord]:
        async with self._session_factory() as session:
            base = await self._visible_base(session, tenant_id, kb_id, user_id)
            if base is None:
                raise KnowledgeError("knowledge base not found or not readable")
            return list((await session.exec(
                select(KnowledgeDocumentRecord).where(
                    KnowledgeDocumentRecord.tenant_id == tenant_id,
                    KnowledgeDocumentRecord.kb_id == kb_id,
                ).order_by(KnowledgeDocumentRecord.created_at)
            )).all())

    async def delete_document(self, tenant_id: str, kb_id: str, user_id: str, doc_id: str) -> None:
        async with self._session_factory() as session, session.begin():
            base = await session.get(KnowledgeBaseRecord, kb_id)
            if base is None or base.tenant_id != tenant_id:
                raise KnowledgeError("knowledge base not found")
            if base.owner_user_id != user_id:
                member = (await session.exec(
                    select(KnowledgeMemberRecord).where(
                        KnowledgeMemberRecord.tenant_id == tenant_id,
                        KnowledgeMemberRecord.kb_id == kb_id,
                        KnowledgeMemberRecord.user_id == user_id,
                    )
                )).first()
                if member is None:
                    raise KnowledgeError("only the owner or a member can delete documents")
            document = await session.get(KnowledgeDocumentRecord, doc_id)
            if document is None or document.tenant_id != tenant_id or document.kb_id != kb_id:
                raise KnowledgeError("document not found")
            await session.delete(document)
