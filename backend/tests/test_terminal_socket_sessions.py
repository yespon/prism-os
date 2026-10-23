"""Actual ASGI WebSockets, original account/asset authority and owned local PTY."""

import asyncio
import shlex
import time
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode

import pytest
from fastapi import FastAPI
from sqlalchemy import text
from test_auth_session_delivery import session_store as session_fixture
from test_terminal_access_boundaries import configured, durable_sqlite, scoped_client  # noqa: F401
from test_terminal_access_boundaries import terminal_environment as environment_fixture


@pytest.fixture
def anyio_backend():
    return "asyncio"


session_store = session_fixture
terminal_environment = environment_fixture


class SocketPeer:
    def __init__(self, app, token, headers=()):
        self.to_server, self.to_client = asyncio.Queue(), asyncio.Queue()
        scope = {
            "type": "websocket",
            "asgi": {"version": "3.0", "spec_version": "2.4"},
            "http_version": "1.1",
            "scheme": "ws",
            "path": "/api/terminal/ws",
            "raw_path": b"/api/terminal/ws",
            "query_string": urlencode({"asset_id": "own-host", "session_id": "socket-owned", "token": token}).encode(),
            "headers": list(headers),
            "client": ("127.0.0.1", 1234),
            "server": ("test", 80),
            "subprotocols": [],
            "state": {},
        }
        self.task = asyncio.create_task(app(scope, self.to_server.get, self.to_client.put))

    async def connect(self):
        await self.to_server.put({"type": "websocket.connect"})
        assert (await asyncio.wait_for(self.to_client.get(), 4))["type"] == "websocket.accept"
        return self

    async def send(self, value):
        await self.to_server.put({"type": "websocket.receive", "text": value})

    async def until(self, text):
        result = ""
        deadline = time.monotonic() + 5
        while text not in result:
            message = await asyncio.wait_for(self.to_client.get(), max(0.01, deadline - time.monotonic()))
            assert message["type"] != "websocket.close", message
            result += message.get("text", "")
        return result

    async def closed(self):
        messages = []
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            try:
                message = await asyncio.wait_for(self.to_client.get(), max(0.01, deadline - time.monotonic()))
            except TimeoutError:
                break
            messages.append(message)
            if message["type"] == "websocket.close":
                return message["code"], messages
        return None, messages

    async def finish(self):
        await self.to_server.put({"type": "websocket.disconnect", "code": 1000})
        try:
            await asyncio.wait_for(self.task, 2)
        except TimeoutError:
            self.task.cancel()
            await asyncio.gather(self.task, return_exceptions=True)


@pytest.fixture
def socket_environment(terminal_environment, session_store, monkeypatch):
    from app.agent import terminal_tools
    from app.gateway.routers import terminal
    from app.services.terminal.session import TerminalSessionManager
    from deerflow.database.session import get_session

    factory, _ = terminal_environment
    manager = TerminalSessionManager()
    monkeypatch.setattr(terminal_tools, "session_manager", manager)
    monkeypatch.setattr(terminal, "build_ssh_command", lambda *args, **kwargs: (["/bin/bash", "--noprofile", "--norc"], {}, []))
    app = FastAPI()

    async def dependency():
        async with factory() as db:
            yield db

    app.dependency_overrides[get_session] = dependency
    app.include_router(terminal.router, prefix="/api/terminal")
    yield app, manager, session_store[0]
    for session in list(manager.sessions.values()):
        session.close()


@pytest.mark.anyio
@pytest.mark.parametrize("operation", ["input", "resize", "idle"])
@pytest.mark.parametrize("change", ["deleted", "expired", "owner", "store-down"])
async def test_revoked_socket_session_cannot_write_resize_or_stay_idle(socket_environment, tmp_path, monkeypatch, operation, change):
    app, manager, engine = socket_environment
    peer = await SocketPeer(app, "synthetic-session-a").connect()
    try:
        await peer.send("printf 'SOCKET_READY\\n'\n")
        await peer.until("SOCKET_READY")
        session = next(iter(manager.sessions.values()))
        writes, resizes = [], []
        write, resize = session.pty.write, session.pty.resize
        session.pty.write = lambda value: writes.append(value) or write(value)
        session.pty.resize = lambda rows, cols: resizes.append((rows, cols)) or resize(rows, cols)
        if change == "store-down":
            from app.gateway import auth

            def unavailable():
                raise RuntimeError("Synthetic session store unavailable")

            monkeypatch.setattr(auth, "auth_connection", unavailable)
        else:
            with engine.begin() as connection:
                if change == "deleted":
                    connection.execute(text("DELETE FROM session WHERE id=:id"), {"id": "session-a"})
                elif change == "expired":
                    connection.execute(text('UPDATE session SET "expiresAt"=:expires WHERE id=:id'), {"expires": datetime.now(UTC) - timedelta(seconds=1), "id": "session-a"})
                else:
                    connection.execute(text('UPDATE session SET "userId"=:actor WHERE id=:id'), {"actor": "user-b", "id": "session-a"})
        late = tmp_path / "late-socket-effect"
        if operation == "input":
            await peer.send("printf late > " + shlex.quote(str(late)) + "\n")
        elif operation == "resize":
            await peer.send('{"type":"resize","rows":41,"cols":121}')
        code, _ = await peer.closed()
        assert code == 1008
        assert not writes and not resizes and not late.exists()
    finally:
        await peer.finish()


@pytest.mark.anyio
async def test_withdrawn_socket_receives_no_output_and_does_not_close_legal_peer(socket_environment):
    app, manager, engine = socket_environment
    first = await SocketPeer(app, "synthetic-session-a").connect()
    second = None
    try:
        await first.send("printf 'FIRST_READY\\n'\n")
        await first.until("FIRST_READY")
        second = await SocketPeer(app, "synthetic-session-b").connect()
        await second.send("printf 'SECOND_READY\\n'\n")
        await second.until("SECOND_READY")
        assert len(manager.sessions) == 1
        session = next(iter(manager.sessions.values()))
        pid = session.pty.pid
        with engine.begin() as connection:
            connection.execute(text("DELETE FROM session WHERE id=:id"), {"id": "session-a"})
        await second.send("printf 'LEGAL_PEER_OUTPUT\\n'\n")
        assert "LEGAL_PEER_OUTPUT" in await second.until("LEGAL_PEER_OUTPUT")
        code, messages = await first.closed()
        assert code == 1008 and all("LEGAL_PEER_OUTPUT" not in m.get("text", "") for m in messages)
        assert session.pty.pid == pid and session.pty.fd is not None
    finally:
        await first.finish()
        if second is not None:
            await second.finish()


@pytest.mark.anyio
@pytest.mark.parametrize("credential", ["header", "query-over-cookie", "revoked-header"])
async def test_socket_uses_original_http_token_precedence(socket_environment, credential):
    app, manager, engine = socket_environment
    with engine.begin() as connection:
        connection.execute(text("DELETE FROM session WHERE id=:id"), {"id": "session-a"})
    if credential == "header":
        token, headers = "", [(b"authorization", b"Bearer synthetic-session-b")]
    elif credential == "query-over-cookie":
        token, headers = "synthetic-session-b", [(b"cookie", b"better-auth.session_token=synthetic-session-a")]
    else:
        token, headers = "synthetic-session-b", [(b"authorization", b"Bearer synthetic-session-a")]
    peer = await SocketPeer(app, token, headers).connect()
    try:
        if credential == "revoked-header":
            code, _ = await peer.closed()
            assert code == 1008 and not manager.sessions
        else:
            await peer.send("printf 'CANONICAL_TOKEN_READY\\n'\n")
            assert "CANONICAL_TOKEN_READY" in await peer.until("CANONICAL_TOKEN_READY")
    finally:
        await peer.finish()


@pytest.mark.anyio
async def test_session_lost_during_asset_lookup_never_acquires_a_pty(socket_environment, monkeypatch):
    from app.services.terminal import access

    app, manager, engine = socket_environment
    original = access.verify_terminal_access

    async def withdraw_after_current_asset(*args, **kwargs):
        result = await original(*args, **kwargs)
        with engine.begin() as connection:
            connection.execute(text("DELETE FROM session WHERE id=:id"), {"id": "session-a"})
        return result

    monkeypatch.setattr(access, "verify_terminal_access", withdraw_after_current_asset)
    peer = await SocketPeer(app, "synthetic-session-a").connect()
    try:
        code, _ = await peer.closed()
        assert code == 1008 and not manager.sessions
    finally:
        await peer.finish()


@pytest.mark.anyio
async def test_original_broadcast_tolerates_concurrent_detach_without_losing_a_peer():
    from app.services.terminal.session import TerminalSession

    session = TerminalSession("race", "owned")
    delivered = []

    class Detached:
        async def send_text(self, value):
            session.detach_websocket(self)
            raise RuntimeError("Synthetic disconnected transport")

    class Legal:
        async def send_text(self, value):
            delivered.append(value)

    detached, legal = Detached(), Legal()
    session.attach_websocket(detached)
    session.attach_websocket(legal)
    await session._on_pty_output("AUTHORIZED PEER FRAME")
    assert delivered == ["AUTHORIZED PEER FRAME"]
    assert session.websockets == {legal}

@pytest.mark.anyio
async def test_revoked_blocked_sender_does_not_stall_original_legal_broadcast(session_store):
    from app.gateway.auth import current_session_verifier
    from app.services.terminal.session import TerminalSession
    from app.services.terminal.socket_access import CurrentTerminalSocket

    engine, _ = session_store
    blocked, cancelled, close_cancelled = asyncio.Event(), asyncio.Event(), asyncio.Event()
    delivered = []
    class Slow:
        async def send_text(self, value):
            blocked.set()
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.set()
        async def close(self, **kwargs):
            assert cancelled.is_set()
            try:
                await asyncio.Event().wait()
            finally:
                close_cancelled.set()
    class Legal:
        async def send_text(self, value):
            delivered.append(value)
        async def close(self, **kwargs):
            pass
    async def isolated_transport_test_authority():
        return None
    a = CurrentTerminalSocket(Slow(), current_session_verifier("synthetic-session-a", "user-a"), isolated_transport_test_authority)
    b = CurrentTerminalSocket(Legal(), current_session_verifier("synthetic-session-b", "user-a"), isolated_transport_test_authority)
    session = TerminalSession("backpressure", "owned")
    session.attach_websocket(a)
    session.attach_websocket(b)
    broadcasting = asyncio.create_task(session._on_pty_output("LEGAL CURRENT FRAME"))
    await asyncio.wait_for(blocked.wait(), 2)
    with engine.begin() as connection:
        connection.execute(text('DELETE FROM session WHERE id=:id'), {"id": "session-a"})
    await asyncio.wait_for(broadcasting, 3)
    assert cancelled.is_set() and close_cancelled.is_set()
    assert delivered == ["LEGAL CURRENT FRAME"] and session.websockets == {b}
