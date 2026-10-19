"""R2 knowledge API contracts: upload -> index -> status -> delete loop."""

from io import BytesIO

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from app.gateway import auth
from app.gateway.routers import knowledge as routes
from app.knowledge import KnowledgeService
from app.models import files as _files_models  # noqa: F401
from app.models import knowledge as _knowledge_models  # noqa: F401


def _client(monkeypatch, tmp_path):
    monkeypatch.setenv("PRISMOS_HOME", str(tmp_path / "home"))
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'api.db'}")
    SQLModel.metadata.create_all  # ensure import side effects ran

    async def setup():
        async with engine.begin() as connection:
            await connection.run_sync(SQLModel.metadata.create_all)

    import asyncio
    asyncio.run(setup())
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    service = KnowledgeService(factory)
    monkeypatch.setattr(routes, "_service", lambda: service)
    from app.knowledge import embedding as embedding_module
    monkeypatch.setattr(embedding_module, "get_session_factory", lambda: factory)
    monkeypatch.setattr(routes, "get_session_factory", lambda: factory)

    def resolve_user(token):
        if token == "valid":
            return ("user-1", "user", False)
        if token == "member-token":
            return ("member-9", "user", False)
        return None

    monkeypatch.setattr(auth, "_resolve_user_from_auth_db", resolve_user)
    monkeypatch.setattr(auth, "_resolve_user_status_from_auth_db", lambda _user: "active")

    async def resolve_tenant(user_id=None, requested_tenant_id=None):
        return requested_tenant_id or "t1"

    monkeypatch.setattr(auth, "_resolve_tenant_id", resolve_tenant)
    async def resolve_role(*, user_id, tenant_id):
        return "user"

    monkeypatch.setattr(auth, "_resolve_tenant_role", resolve_role)

    app = FastAPI()
    app.add_middleware(auth.AuthMiddleware)
    app.include_router(routes.router, prefix="/api")

    async def _session_override():
        async with factory() as session:
            yield session

    app.dependency_overrides[routes.get_session] = _session_override
    return TestClient(app)


def _auth(client):
    client.headers.update({"Authorization": "Bearer valid", "x-tenant-id": "t1"})
    return client


def test_upload_index_status_delete_loop(monkeypatch, tmp_path):
    with _client(monkeypatch, tmp_path) as client:
        _auth(client)
        created = client.post("/api/knowledge/bases", json={"name": "runbooks"})
        assert created.status_code == 201, created.text
        kb_id = created.json()["id"]

        upload = client.post(
            f"/api/knowledge/bases/{kb_id}/documents",
            files={"file": ("guide.md", BytesIO(b"# Runbook\n\nRestart the api gateway gracefully."), "text/markdown")},
        )
        assert upload.status_code == 201, upload.text
        document = upload.json()
        assert document["index_state"] == "ready", document
        assert document["indexed_at"] is not None

        status = client.get(f"/api/knowledge/bases/{kb_id}/documents/{document['id']}")
        assert status.status_code == 200
        assert status.json()["index_state"] == "ready"

        # Delete removes the document; the status then 404s.
        deleted = client.delete(f"/api/knowledge/bases/{kb_id}/documents/{document['id']}")
        assert deleted.status_code == 204
        gone = client.get(f"/api/knowledge/bases/{kb_id}/documents/{document['id']}")
        assert gone.status_code == 404


def test_cross_tenant_documents_refused(monkeypatch, tmp_path):
    with _client(monkeypatch, tmp_path) as client:
        _auth(client)
        created = client.post("/api/knowledge/bases", json={"name": "private-kb"})
        kb_id = created.json()["id"]
        upload = client.post(
            f"/api/knowledge/bases/{kb_id}/documents",
            files={"file": ("a.md", BytesIO(b"content"), "text/markdown")},
        )
        assert upload.status_code == 201

        # Same authenticated user, different tenant: invisible.
        client.headers.update({"x-tenant-id": "t2"})
        assert client.get(f"/api/knowledge/bases/{kb_id}/documents").status_code == 404
        doc_id = upload.json()["id"]
        assert client.get(f"/api/knowledge/bases/{kb_id}/documents/{doc_id}").status_code == 404
        assert client.delete(f"/api/knowledge/bases/{kb_id}/documents/{doc_id}").status_code == 404


def test_unsupported_document_fails_visibly(monkeypatch, tmp_path):
    with _client(monkeypatch, tmp_path) as client:
        _auth(client)
        created = client.post("/api/knowledge/bases", json={"name": "kb"})
        kb_id = created.json()["id"]
        upload = client.post(
            f"/api/knowledge/bases/{kb_id}/documents",
            files={"file": ("payload.exe", BytesIO(b"MZ..."), "application/octet-stream")},
        )
        assert upload.status_code == 201
        document = upload.json()
        assert document["index_state"] == "failed"
        assert "unsupported knowledge document extension" in document["index_error"]


def test_member_grant_revoke_via_api(monkeypatch, tmp_path):
    with _client(monkeypatch, tmp_path) as client:
        _auth(client)
        created = client.post("/api/knowledge/bases", json={"name": "team-kb"})
        kb_id = created.json()["id"]
        upload = client.post(
            f"/api/knowledge/bases/{kb_id}/documents",
            files={"file": ("shared.md", BytesIO(b"team content"), "text/markdown")},
        )
        assert upload.status_code == 201
        doc_id = upload.json()["id"]

        # Grant: the member sees documents; a stranger does not.
        granted = client.post(f"/api/knowledge/bases/{kb_id}/members", json={"user_id": "member-9"})
        assert granted.status_code == 201, granted.text
        client.headers.update({"Authorization": "Bearer member-token"})
        assert client.get(f"/api/knowledge/bases/{kb_id}/documents/{doc_id}").status_code == 200

        # Revoke: immediate loss through the API.
        client.headers.update({"Authorization": "Bearer valid"})
        revoked = client.delete(f"/api/knowledge/bases/{kb_id}/members", params={"user_id": "member-9"})
        assert revoked.status_code == 200, revoked.text
        client.headers.update({"Authorization": "Bearer member-token"})
        assert client.get(f"/api/knowledge/bases/{kb_id}/documents/{doc_id}").status_code == 404

        # Only the owner can grant.
        forbidden = client.post(f"/api/knowledge/bases/{kb_id}/members", json={"user_id": "friend"})
        assert forbidden.status_code == 400
