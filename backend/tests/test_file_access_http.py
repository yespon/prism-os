"""Actual HTTP routes, database membership and original durable thread facts."""

import asyncio
import zipfile
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select
from test_file_access_boundaries import owned_runtime as owned_fixture
from test_file_access_boundaries import selected_runtime  # noqa: F401
from test_skill_member_tools import configured, scoped_client  # noqa: F401
from test_skill_reference_transactions import durable_sqlite  # noqa: F401

from app.gateway import file_authorization
from app.gateway.routers import artifacts, langgraph_proxy, threads, uploads
from app.platform.execution import trust
from deerflow.database.models import Tenant, TenantMembership

owned_runtime = owned_fixture


@pytest.fixture
def file_client(owned_runtime, monkeypatch, native_identity):
    native_identity("user-b")
    factory, root, agent, calls, runtime = owned_runtime
    monkeypatch.setattr(file_authorization, "get_session_factory", lambda: factory)
    monkeypatch.setattr(langgraph_proxy, "get_session_factory", lambda: factory)
    monkeypatch.setattr(trust, "get_session_factory", lambda: factory)
    paths = __import__("deerflow.config.paths", fromlist=["get_paths"]).get_paths()
    monkeypatch.setattr(artifacts, "get_paths", lambda: paths)
    monkeypatch.setattr(threads, "get_paths", lambda: paths)
    monkeypatch.setattr(uploads, "get_paths", lambda: paths)

    async def more_members():
        async with factory() as session:
            session.add(Tenant(id="tenant-b", name="B", slug="b"))
            for tenant, actor in [("tenant-a", "user-b"), ("tenant-b", "user-a")]:
                session.add(TenantMembership(tenant_id=tenant, user_id=actor, role="member"))
            await session.commit()

    asyncio.run(more_members())
    app = FastAPI()

    @app.middleware("http")
    async def identity(request, call_next):
        request.state.user_id = request.headers.get("x-user", "user-a")
        request.state.tenant_id = request.headers.get("x-tenant", "tenant-a")
        return await call_next(request)

    for router in [artifacts.router, threads.router, langgraph_proxy.router, uploads.router]:
        app.include_router(router)
    with TestClient(app) as client:
        yield client, factory, paths, runtime


def test_owned_output_download_archive_and_history_cross_actor_guards(file_client, monkeypatch):
    from starlette.responses import Response

    client, _, paths, runtime = file_client
    output = Path(runtime.state["thread_data"]["outputs_path"])
    (output / "report.txt").write_text("OWNED RESULT 中文")
    with zipfile.ZipFile(output / "bundle.skill", "w") as archive:
        archive.writestr("bundle/SKILL.md", "OWNED ARCHIVE")
    history_calls = []

    async def forward(*args):
        history_calls.append(args[:2])
        return Response(b'{"result":"OWNED HISTORY"}', media_type="application/json")

    monkeypatch.setattr(langgraph_proxy, "_forward", forward)
    url = "/api/threads/member-thread/artifacts/mnt/user-data/outputs/report.txt"
    assert client.get(url).text == "OWNED RESULT 中文"
    download = client.get(url + "?download=true")
    assert download.text == "OWNED RESULT 中文" and download.headers["content-disposition"].startswith("attachment;")
    assert download.headers["cache-control"] == "no-store"
    assert client.get("/api/threads/member-thread/artifacts/mnt/user-data/outputs/bundle.skill/SKILL.md").text == "OWNED ARCHIVE"
    assert client.get("/api/langgraph/threads/member-thread/history").status_code == 200
    for headers in [{"x-user": "user-b"}, {"x-tenant": "tenant-b"}]:
        assert client.get(url, headers=headers).status_code == 404
        assert client.get("/api/langgraph/threads/member-thread/history", headers=headers).status_code == 404
        assert client.get("/api/threads/member-thread/uploads/list", headers=headers).status_code == 404
        assert client.delete("/api/threads/member-thread", headers=headers).status_code == 404
    assert len(history_calls) == 1 and (output / "report.txt").exists()


@pytest.mark.parametrize("endpoint", ["artifacts/mnt/user-data/outputs/report.txt", "history", "uploads/list", "delete"])
def test_stale_request_identity_cannot_access_after_membership_withdrawal(file_client, endpoint, monkeypatch):
    client, factory, _, runtime = file_client
    (Path(runtime.state["thread_data"]["outputs_path"]) / "report.txt").write_text("REVOKED SECRET")

    async def revoke():
        async with factory() as session:
            member = (await session.exec(select(TenantMembership).where(TenantMembership.user_id == "user-a", TenantMembership.tenant_id == "tenant-a"))).scalars().one()
            member.status = "inactive"
            session.add(member)
            await session.commit()

    asyncio.run(revoke())

    def should_not_delete(*args):
        pytest.fail("Unauthorized checkpoint deletion")

    monkeypatch.setattr(threads, "_delete_thread_checkpoints", should_not_delete)
    if endpoint == "history":
        response = client.get("/api/langgraph/threads/member-thread/history")
    elif endpoint == "delete":
        response = client.delete("/api/threads/member-thread")
    else:
        response = client.get("/api/threads/member-thread/" + endpoint)
    assert response.status_code == 403 and "REVOKED SECRET" not in response.text


def test_artifact_alias_and_revocation_during_read_do_not_publish_bytes(file_client, monkeypatch):
    client, factory, _, runtime = file_client
    output = Path(runtime.state["thread_data"]["outputs_path"])
    private = output.parent / "private.txt"
    private.write_text("PRIVATE CONTENT")
    (output / "alias.txt").symlink_to(private)
    prefix = "/api/threads/member-thread/artifacts/mnt/user-data/outputs/"
    assert client.get(prefix + "alias.txt").status_code == 403
    (output / "report.txt").write_text("REVOKED DURING READ")
    original = artifacts.read_owned_file

    def revoke_after_read(path):
        data = original(path)

        async def revoke():
            async with factory() as session:
                member = (await session.exec(select(TenantMembership).where(TenantMembership.user_id == "user-a", TenantMembership.tenant_id == "tenant-a"))).scalars().one()
                member.status = "inactive"
                session.add(member)
                await session.commit()

        from app.runtime_adapters import _run_async

        _run_async(revoke())
        return data

    monkeypatch.setattr(artifacts, "read_owned_file", revoke_after_read)
    response = client.get(prefix + "report.txt")
    assert response.status_code == 403 and "REVOKED DURING READ" not in response.text


@pytest.mark.parametrize("range_value", ["bytes=1-3", "bytes=-3", "bytes=0-1,5-7", "bytes=900-1000", "invalid"])
def test_authorized_download_preserves_range_contract(file_client, range_value):
    client, _, _, runtime = file_client
    output = Path(runtime.state["thread_data"]["outputs_path"])
    (output / "report.txt").write_bytes(b"0123456789")
    url = "/api/threads/member-thread/artifacts/mnt/user-data/outputs/report.txt?download=true"
    response = client.get(url, headers={"range": range_value})
    if range_value == "bytes=1-3":
        assert response.status_code == 206 and response.content == b"123"
        assert response.headers["content-range"] == "bytes 1-3/10"
    elif range_value == "bytes=-3":
        assert response.status_code == 206 and response.content == b"789"
    elif "," in range_value:
        assert response.status_code == 206 and response.headers["content-type"].startswith("multipart/byteranges")
        assert b"01" in response.content and b"567" in response.content
    else:
        assert response.status_code == (416 if range_value.startswith("bytes=") else 400)
    assert response.headers["cache-control"] == "no-store"

@pytest.mark.parametrize("endpoint", ["artifacts/mnt/user-data/outputs/report.txt?download=true", "history", "uploads/list", "delete"])
@pytest.mark.parametrize("change", ["suspended", "deleted", "password-reset"])
def test_current_original_account_guards_http_downloads_and_history(file_client, endpoint, change, monkeypatch):
    from sqlalchemy import text

    from app.gateway import auth_db

    client, _, _, runtime = file_client
    output = Path(runtime.state["thread_data"]["outputs_path"]) / "report.txt"
    output.write_text("REVOKED ACCOUNT SECRET")
    with auth_db.get_auth_engine().begin() as connection:
        if change == "deleted":
            connection.execute(text('DELETE FROM "user" WHERE id=:id'), {"id": "user-a"})
        elif change == "password-reset":
            connection.execute(text('UPDATE "user" SET "mustChangePassword"=:value WHERE id=:id'), {"value": True, "id": "user-a"})
        else:
            connection.execute(text('UPDATE "user" SET status=:value WHERE id=:id'), {"value": "suspended", "id": "user-a"})

    async def forbidden_history(*args):
        pytest.fail("Revoked account forwarded to history")

    monkeypatch.setattr(langgraph_proxy, "_forward", forbidden_history)
    monkeypatch.setattr(threads, "_delete_thread_checkpoints", lambda *args: pytest.fail("Revoked checkpoint deletion"))
    if endpoint == "history":
        response = client.get("/api/langgraph/threads/member-thread/history")
    elif endpoint == "delete":
        response = client.delete("/api/threads/member-thread")
    else:
        response = client.get("/api/threads/member-thread/" + endpoint)
    assert response.status_code == 403 and "REVOKED ACCOUNT SECRET" not in response.text
    assert output.read_text() == "REVOKED ACCOUNT SECRET"
