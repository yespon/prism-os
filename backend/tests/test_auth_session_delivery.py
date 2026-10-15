"""Original Auth Session expiry and current in-flight response delivery."""

import asyncio
import os
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DataError
from test_file_access_http import configured, durable_sqlite, owned_runtime, scoped_client, selected_runtime  # noqa: F401
from test_file_access_http import file_client as native_file_client

from app.gateway import auth, auth_db

file_client = native_file_client


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def session_store(tmp_path, monkeypatch):
    candidate = os.environ.get("PRISMOS_SKILL_TEST_DB_URL", "")
    postgres = candidate.startswith("postgresql+")
    if postgres:
        parsed = make_url(candidate)
        if parsed.drivername != "postgresql+asyncpg" or parsed.host not in {"127.0.0.1", "localhost"} or parsed.database != "prismos_skill_probe":
            raise RuntimeError("Session tests require the owned loopback probe database")
    engine = create_engine(candidate.replace("postgresql+asyncpg://", "postgresql+psycopg://", 1) if postgres else "sqlite+pysqlite:///" + str(tmp_path / "sessions.sqlite"))
    monkeypatch.setattr(auth_db, "_engine", engine)
    monkeypatch.setattr(auth_db, "_db_type", "postgres" if postgres else "sqlite")
    monkeypatch.setattr(auth, "auth_connection", auth_db.auth_connection)
    with engine.begin() as connection:
        if postgres:
            connection.execute(text("DROP TABLE IF EXISTS session"))
            connection.execute(text('DROP TABLE IF EXISTS "user"'))
        connection.execute(
            text('CREATE TABLE "user" (id TEXT PRIMARY KEY, role TEXT, status TEXT, "mustChangePassword" BOOLEAN, name TEXT, email TEXT, "emailVerified" BOOLEAN, image TEXT, "createdAt" TEXT, "updatedAt" TEXT, "isBootstrapAdmin" BOOLEAN)')
        )
        connection.execute(text('CREATE TABLE session (id TEXT PRIMARY KEY, token TEXT UNIQUE, "userId" TEXT, "expiresAt" ' + ("TIMESTAMPTZ" if postgres else "TEXT") + ', "createdAt" TEXT, "updatedAt" TEXT)'))
        for actor in ["user-a", "user-b"]:
            connection.execute(text('INSERT INTO "user" (id,role,status,"mustChangePassword") VALUES (:id,:role,:status,:change)'), {"id": actor, "role": "user", "status": "active", "change": False})
        for sid in ["session-a", "session-b"]:
            connection.execute(text('INSERT INTO session (id,token,"userId","expiresAt") VALUES (:id,:token,:actor,:expires)'), {"id": sid, "token": "synthetic-" + sid, "actor": "user-a", "expires": datetime.now(UTC) + timedelta(hours=1)})

    async def tenant(*args, **kwargs):
        return "tenant-a"

    async def role(*args, **kwargs):
        return "member"

    monkeypatch.setattr(auth, "_resolve_tenant_id", tenant)
    monkeypatch.setattr(auth, "_resolve_tenant_role", role)
    yield engine, postgres
    engine.dispose()


@pytest.mark.parametrize("value", [None, "", "not-a-date", "999999999999999999999999", "2000-01-01T00:00:00Z"])
def test_invalid_expiry_is_never_an_unlimited_session(session_store, value):
    engine, postgres = session_store
    if postgres and value not in {None, "2000-01-01T00:00:00Z"}:
        # The real timestamp column rejects malformed values before authentication.
        with pytest.raises(DataError):
            with engine.begin() as connection:
                connection.execute(text('UPDATE session SET "expiresAt"=:expires WHERE id=:id'), {"expires": value, "id": "session-a"})
        return
    with engine.begin() as connection:
        connection.execute(text('UPDATE session SET "expiresAt"=:expires WHERE id=:id'), {"expires": value, "id": "session-a"})
    assert auth._resolve_user_from_auth_db("synthetic-session-a") is None


def test_active_session_and_distinct_session_remain_usable(session_store):
    engine, _ = session_store
    assert auth._resolve_user_from_auth_db("synthetic-session-a")[0] == "user-a"
    with engine.begin() as connection:
        connection.execute(text("DELETE FROM session WHERE id=:id"), {"id": "session-b"})
    assert auth._resolve_user_from_auth_db("synthetic-session-a")[0] == "user-a"


@pytest.mark.anyio
@pytest.mark.parametrize("method", ["GET", "POST"])
@pytest.mark.parametrize("change", ["deleted", "expired", "owner"])
async def test_revoke_while_waiting_does_not_deliver_result(session_store, method, change):
    engine, _ = session_store
    started, release = asyncio.Event(), asyncio.Event()
    writes = []
    app = FastAPI()
    app.add_middleware(auth.AuthMiddleware)

    @app.api_route("/api/owned-result", methods=["GET", "POST"])
    async def result():
        if method == "POST":
            writes.append("original authorized operation")
        started.set()
        await release.wait()
        return {"result": "WITHDRAWN SESSION RESULT"}

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        pending = asyncio.create_task(client.request(method, "/api/owned-result", headers={"Authorization": "Bearer synthetic-session-a"}))
        await asyncio.wait_for(started.wait(), 3)
        with engine.begin() as connection:
            if change == "deleted":
                connection.execute(text("DELETE FROM session WHERE id=:id"), {"id": "session-a"})
            elif change == "expired":
                connection.execute(text('UPDATE session SET "expiresAt"=:expires WHERE id=:id'), {"expires": datetime.now(UTC) - timedelta(seconds=1), "id": "session-a"})
            else:
                connection.execute(text('UPDATE session SET "userId"=:actor WHERE id=:id'), {"actor": "user-b", "id": "session-a"})
        release.set()
        response = await asyncio.wait_for(pending, 3)
    assert response.status_code == (401 if method == "GET" else 503)
    assert "WITHDRAWN SESSION RESULT" not in response.text
    if method == "POST":
        assert response.json()["detail"]["inspection_required"] and len(writes) == 1


def test_session_storage_failure_does_not_log_bearer_material(session_store, monkeypatch, caplog):
    def unavailable():
        raise RuntimeError("synthetic-session-a private storage exception")

    monkeypatch.setattr(auth, "auth_connection", unavailable)
    assert auth._resolve_user_from_auth_db("synthetic-session-a") is None
    assert "synthetic-session-a" not in caplog.text


@pytest.mark.parametrize(
    "raw, valid",
    [
        (datetime(2030, 1, 1, tzinfo=UTC), True),
        (datetime(2030, 1, 1), True),
        ("2030-01-01T00:00:00+08:00", True),
        ("2030-01-01 00:00:00", True),
        (None, False),
        ("", False),
        ("invalid", False),
        (True, False),
        (123456, False),
    ],
)
def test_original_database_expiry_types_are_explicit(raw, valid):
    value = auth._parse_iso_datetime(raw)
    assert (value is not None) == valid
    if value is not None:
        assert value.tzinfo is UTC


@pytest.mark.anyio
@pytest.mark.parametrize("change", ["deleted", "expired", "owner", "store-down", "other-session"])
async def test_actual_response_stream_checks_session_during_idle_wait(session_store, monkeypatch, change):
    from starlette.responses import StreamingResponse

    from app.gateway.session_authorization import SessionAuthorityUnavailable

    engine, _ = session_store
    delivered, waiting, stopped, release = [asyncio.Event() for _ in range(4)]
    sent = []
    app = FastAPI()
    app.add_middleware(auth.AuthMiddleware)

    async def events():
        try:
            yield b"event: data\ndata: AUTHORIZED FIRST\n\n"
            waiting.set()
            await release.wait()
            yield b"event: data\ndata: PRIVATE LATE RESULT\n\nevent: RUN_FINISHED\n\n"
        finally:
            stopped.set()

    @app.get("/api/owned-stream")
    async def stream():
        return StreamingResponse(events(), media_type="text/event-stream")

    async def observed(scope, receive, send):
        async def record(message):
            if message["type"] == "http.response.body":
                sent.append(message.get("body", b""))
                if b"AUTHORIZED FIRST" in sent[-1]:
                    delivered.set()
            await send(message)

        await app(scope, receive, record)

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=observed), base_url="http://test") as client:
        pending = asyncio.create_task(client.get("/api/owned-stream", headers={"Authorization": "Bearer synthetic-session-a"}))
        await asyncio.wait_for(delivered.wait(), 3)
        await asyncio.wait_for(waiting.wait(), 3)
        if change == "store-down":

            def unavailable():
                raise RuntimeError("Synthetic lost session store")

            monkeypatch.setattr(auth, "auth_connection", unavailable)
        else:
            with engine.begin() as connection:
                if change in {"deleted", "other-session"}:
                    connection.execute(text("DELETE FROM session WHERE id=:id"), {"id": "session-b" if change == "other-session" else "session-a"})
                elif change == "expired":
                    connection.execute(text('UPDATE session SET "expiresAt"=:expires WHERE id=:id'), {"expires": datetime.now(UTC) - timedelta(seconds=1), "id": "session-a"})
                else:
                    connection.execute(text('UPDATE session SET "userId"=:actor WHERE id=:id'), {"actor": "user-b", "id": "session-a"})
        if change == "other-session":
            await asyncio.sleep(0.35)
            assert not pending.done()
            release.set()
            response = await asyncio.wait_for(pending, 3)
            assert response.status_code == 200 and "RUN_FINISHED" in response.text
        else:
            with pytest.raises(Exception) as outcome:
                await asyncio.wait_for(pending, 3)

            def has_withdrawal(error):
                return isinstance(error, SessionAuthorityUnavailable) or any(has_withdrawal(child) for child in getattr(error, "exceptions", ()))

            assert has_withdrawal(outcome.value), repr(outcome.value)
            assert b"PRIVATE LATE RESULT" not in b"".join(sent) and b"RUN_FINISHED" not in b"".join(sent)
        await asyncio.wait_for(stopped.wait(), 3)


@pytest.mark.parametrize("value", [None, "bad-expiry", "2000-01-01T00:00:00Z", "2030-01-01T00:00:00Z", datetime(2030, 1, 1, tzinfo=UTC)])
def test_original_session_endpoint_uses_the_same_expiry_contract(value, monkeypatch):
    from starlette.requests import Request

    from app.gateway.routers import auth as endpoint

    row = {"expiresAt": value, "user_id": "user-a", "userId": "user-a"}
    monkeypatch.setattr(endpoint, "_resolve_session", lambda token: row)
    request = Request({"type": "http", "headers": [(b"authorization", b"Bearer synthetic-session-a")], "query_string": b""})
    result = endpoint.get_session(request)
    assert (result.user is not None) == (value is not None and value not in {"bad-expiry", "2000-01-01T00:00:00Z"})


@pytest.mark.anyio
@pytest.mark.parametrize("transport", ["header", "query", "cookie"])
async def test_actual_original_logout_and_session_endpoints_preserve_other_sessions(session_store, transport):
    from app.gateway.routers import auth as endpoint

    app = FastAPI()
    app.add_middleware(auth.AuthMiddleware)
    app.include_router(endpoint.router)

    @app.get("/api/secure-session")
    async def protected():
        return {"ok": True}

    options = {"headers": {"Authorization": "Bearer synthetic-session-a"}} if transport == "header" else {"params": {"token": "synthetic-session-a"}} if transport == "query" else {"cookies": {endpoint.SESSION_COOKIE: "synthetic-session-a"}}
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        before = await client.get("/api/auth/session", **options)
        assert before.status_code == 200 and before.json()["user"]["id"] == "user-a"
        assert (await client.get("/api/secure-session", **options)).status_code == 200
        logout = await client.post("/api/auth/logout", **options)
        assert logout.status_code == 200 and logout.json()["success"]
        after = await client.get("/api/auth/session", **options)
        assert after.status_code == 200 and after.json()["user"] is None
        assert (await client.get("/api/secure-session", **options)).status_code == 401
        assert (await client.get("/api/secure-session", headers={"Authorization": "Bearer synthetic-session-b"})).status_code == 200


def test_original_legacy_auth_column_is_checked_without_aborting_postgres_transaction(session_store):
    engine, _ = session_store
    with engine.begin() as connection:
        connection.execute(text('ALTER TABLE "user" DROP COLUMN "mustChangePassword"'))
    assert auth._resolve_user_from_auth_db("synthetic-session-a") == ("user-a", "user", False)

@pytest.mark.parametrize("entry", ["artifact", "history"])
@pytest.mark.parametrize("withdraw", [False, True])
def test_original_native_file_and_history_routes_recheck_the_actual_session(file_client, session_store, monkeypatch, entry, withdraw):
    from pathlib import Path

    from fastapi.testclient import TestClient
    from starlette.responses import Response

    from app.gateway.routers import artifacts, langgraph_proxy

    _, _, _, runtime = file_client
    engine, _ = session_store
    output = Path(runtime.state["thread_data"]["outputs_path"]) / "session-report.txt"
    output.write_text("PRIVATE NATIVE RESULT")
    app = FastAPI()
    app.add_middleware(auth.AuthMiddleware)
    app.include_router(artifacts.router)
    app.include_router(langgraph_proxy.router)

    def revoke():
        if withdraw:
            with engine.begin() as connection:
                connection.execute(text('DELETE FROM session WHERE id=:id'), {"id": "session-a"})

    original = artifacts.read_owned_file
    def read_and_revoke(path):
        value = original(path)
        revoke()
        return value
    monkeypatch.setattr(artifacts, "read_owned_file", read_and_revoke)
    async def forward(*args):
        revoke()
        return Response(b'{"result":"PRIVATE NATIVE RESULT"}', media_type="application/json")
    monkeypatch.setattr(langgraph_proxy, "_forward", forward)
    url = "/api/threads/member-thread/artifacts/mnt/user-data/outputs/session-report.txt?download=true" if entry == "artifact" else "/api/langgraph/threads/member-thread/history"
    with TestClient(app) as client:
        response = client.get(url, headers={"Authorization": "Bearer synthetic-session-a"})
    assert response.status_code == (401 if withdraw else 200), response.text
    assert ("PRIVATE NATIVE RESULT" in response.text) == (not withdraw)
    assert response.headers["cache-control"] == "private, no-store"


def test_actual_session_guard_preserves_original_authorized_range_download(file_client, session_store):
    from pathlib import Path

    from fastapi.testclient import TestClient

    from app.gateway.routers import artifacts

    _, _, _, runtime = file_client
    output = Path(runtime.state["thread_data"]["outputs_path"]) / "session-range.txt"
    output.write_bytes(b"0123456789")
    app = FastAPI()
    app.add_middleware(auth.AuthMiddleware)
    app.include_router(artifacts.router)
    with TestClient(app) as client:
        response = client.get("/api/threads/member-thread/artifacts/mnt/user-data/outputs/session-range.txt?download=true&token=synthetic-session-a", headers={"Range": "bytes=2-4"})
    assert response.status_code == 206 and response.content == b"234"
    assert response.headers["content-range"] == "bytes 2-4/10"
    assert response.headers["content-disposition"].startswith("attachment;")
