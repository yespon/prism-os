"""Original terminal assets, credentials, owned sessions and live delivery boundaries."""

import asyncio

import pytest
from sqlalchemy import select
from test_agent_skill_references import configured as resource_fixture
from test_agent_skill_references import scoped_client  # noqa: F401
from test_skill_reference_transactions import durable_sqlite  # noqa: F401

from app.agent import terminal_tools
from app.models.assets import Keychain, LocalAsset
from app.models.terminal import ChatSession
from deerflow.database.models import TenantMembership

configured = resource_fixture


@pytest.fixture
def terminal_environment(configured, monkeypatch):
    from app.services.terminal import access
    _, factory, _, _ = configured
    async def create():
        async with factory() as db:
            db.add(Keychain(id="own-key", tenant_id="tenant-a", user_id="user-a", name="Own", type="password", value="test-only-placeholder"))
            db.add(Keychain(id="foreign-key", tenant_id="tenant-a", user_id="other-user", name="Foreign", type="password", value="not-a-real-secret"))
            await db.flush()
            db.add(LocalAsset(id="own-host", tenant_id="tenant-a", user_id="user-a", name="Own", ip="127.0.0.1", keychain_id="own-key"))
            db.add(LocalAsset(id="foreign-host", tenant_id="tenant-a", user_id="other-user", name="Foreign", ip="127.0.0.1"))
            db.add(ChatSession(id="own-chat", tenant_id="tenant-a", user_id="user-a", terminal_session_id="session"))
            db.add(ChatSession(id="foreign-chat", tenant_id="tenant-a", user_id="other-user", terminal_session_id="session"))
            await db.commit()
    asyncio.run(create())
    monkeypatch.setattr(access, "get_session_factory", lambda: factory)
    monkeypatch.setattr(terminal_tools, "get_session_factory", lambda: factory)
    context = {"tenant_id": "tenant-a", "user_id": "user-a", "chat_session_id": "own-chat", "terminal_session_id": "session", "selected_assets": [{"id": "own-host"}]}
    previous = terminal_tools.get_terminal_context()
    terminal_tools.set_terminal_context(context)
    try:
        yield factory, context
    finally:
        terminal_tools.set_terminal_context(previous)


def change(factory, function):
    async def update():
        async with factory() as db:
            await function(db)
            await db.commit()
    asyncio.run(update())


@pytest.mark.parametrize("problem", ["foreign-asset", "foreign-key", "withdrawn", "foreign-chat"])
def test_foreign_or_withdrawn_access_never_acquires_pty(terminal_environment, monkeypatch, problem):
    factory, context = terminal_environment
    if problem == "foreign-chat":
        terminal_tools.set_terminal_context({**context, "chat_session_id": "foreign-chat"})
    async def modify(db):
        if problem == "foreign-key":
            row = await db.get(LocalAsset, "own-host")
            row.keychain_id = "foreign-key"
        elif problem == "withdrawn":
            row = (await db.exec(select(TenantMembership))).scalars().one()
            row.status = "inactive"
        else:
            return
        db.add(row)
    change(factory, modify)
    monkeypatch.setattr(terminal_tools.session_manager, "get_or_create_session", lambda *args, **kwargs: pytest.fail("Unowned PTY acquired"))
    with pytest.raises(PermissionError):
        asyncio.run(terminal_tools._ensure_session("foreign-host" if problem == "foreign-asset" else "own-host"))


def test_same_session_strings_do_not_mix_owners_or_delimiter_lookalikes():
    from app.services.terminal.session import TerminalSessionManager
    manager = TerminalSessionManager()
    a = manager.get_or_create_session("same", "host", tenant_id="a", user_id="user")
    b = manager.get_or_create_session("same", "host", tenant_id="b", user_id="user")
    c = manager.get_or_create_session("same:host", "extra", tenant_id="a", user_id="user")
    d = manager.get_or_create_session("same", "host:extra", tenant_id="a", user_id="user")
    assert a is not b and c is not d
    assert manager.get_session("same", "host") is None
    manager.close_session("same", tenant_id="a", user_id="user")
    assert manager.get_session("same", "host", tenant_id="b", user_id="user") is b
    manager.close_session("same", tenant_id="b", user_id="user")
    manager.close_session("same:host", tenant_id="a", user_id="user")


def test_tool_factory_freezes_each_context_and_keeps_parallel_execution_isolated(terminal_environment, monkeypatch):
    _, context = terminal_environment
    async def targets(op, index):
        await asyncio.sleep(.01)
        return terminal_tools.get_terminal_context()["user_id"]
    from app.services.terminal import access
    async def member_context_only(context):
        return None, None
    # This unit isolates ContextVar scheduling; real membership boundaries
    # are exercised by the DB/HTTP/PTY cases in this same module.
    monkeypatch.setattr(access, "verify_terminal_access", member_context_only)
    monkeypatch.setattr(terminal_tools, "_run_on_targets", targets)
    terminal_tools.set_terminal_context(context)
    a = terminal_tools.get_terminal_tools()[1]
    terminal_tools.set_terminal_context({**context, "user_id": "other-user"})
    b = terminal_tools.get_terminal_tools()[1]
    async def run():
        return await asyncio.gather(a.ainvoke({"path":"/owned"}), b.ainvoke({"path":"/other"}))
    assert asyncio.run(run()) == ["user-a", "other-user"]


def test_cached_terminal_result_is_discarded_if_member_withdrawn_during_wait(terminal_environment):
    from app.services.terminal.access import current_terminal_stream
    factory, context = terminal_environment
    async def upstream():
        async with factory() as db:
            row = (await db.exec(select(TenantMembership))).scalars().one()
            row.status = "inactive"
            db.add(row)
            await db.commit()
        yield "PRIVATE RESULT"
    async def consume():
        values = []
        with pytest.raises(PermissionError):
            async for value in current_terminal_stream(upstream(), context, ["own-host"]):
                values.append(value)
        return values
    assert asyncio.run(consume()) == []


def test_actual_local_pty_closes_after_revocation_even_without_output(terminal_environment, monkeypatch):
    from app.services.terminal.access import terminal_lease_validator
    from app.services.terminal.session import TerminalSession
    factory, context = terminal_environment
    async def run():
        session = TerminalSession("owned-runtime", "own-host")
        session.authority_validator = await terminal_lease_validator(context, "own-host")
        session.start(["/bin/bash", "--noprofile", "--norc"], {}, [])
        assert session.pty.fd is not None
        async with factory() as db:
            row = (await db.exec(select(TenantMembership))).scalars().one()
            row.status = "inactive"
            db.add(row)
            await db.commit()
        for _ in range(40):
            if session.pty.fd is None:
                break
            await asyncio.sleep(.05)
        assert session.pty.fd is None
        if session.authority_task:
            await asyncio.gather(session.authority_task, return_exceptions=True)
        if session.read_task:
            await asyncio.gather(session.read_task, return_exceptions=True)
    asyncio.run(run())


@pytest.fixture
def terminal_http(configured, terminal_environment):
    from app.gateway.routers.terminal import router
    http = configured[0]
    http.app.include_router(router, prefix="/api/terminal")
    return http


@pytest.mark.parametrize("endpoint", ["execute", "invoke", "approve"])
def test_actual_http_refuses_foreign_asset_or_history_before_execution(terminal_http, terminal_environment, monkeypatch, endpoint):
    monkeypatch.setattr(terminal_tools.session_manager, "get_or_create_session", lambda *args, **kwargs: pytest.fail("Unauthorized PTY acquisition started"))
    if endpoint == "execute":
        payload = {"session_id":"session", "asset_id":"foreign-host", "command":"echo private"}
    elif endpoint == "invoke":
        payload = {"session_id":"foreign-chat", "selected_assets":[{"id":"own-host"}], "user_input":"Read private", "mode":"agent"}
    else:
        payload = {"session_id":"foreign-chat", "tool_call_id":"foreign-approval", "approved":True}
    response = terminal_http.post("/api/terminal/"+endpoint, json=payload)
    assert response.status_code == 403, response.text
    assert "not-a-real-secret" not in response.text


def test_actual_http_invoke_disallows_foreign_checkpoint_even_with_owned_chat(terminal_http, monkeypatch):
    from types import SimpleNamespace

    from app.agent.terminal_graph import terminal_graph
    async def foreign(config):
        return SimpleNamespace(values={"tenant_id":"other-tenant","user_id":"foreign-user","session_id":"own-chat","messages":["PRIVATE HISTORY"]})
    monkeypatch.setattr(terminal_graph, "aget_state", foreign)
    response = terminal_http.post("/api/terminal/invoke", json={"session_id":"own-chat","selected_assets":[{"id":"own-host"}],"user_input":"Read"})
    assert response.status_code == 403 and "PRIVATE HISTORY" not in response.text, response.text


def test_actual_http_rechecks_member_before_cached_terminal_result_delivery(terminal_http, terminal_environment, monkeypatch):
    from types import SimpleNamespace

    from app.agent.terminal_graph import terminal_graph
    factory, _ = terminal_environment
    async def checkpoint(config):
        return SimpleNamespace(values={})
    async def events(*args, **kwargs):
        async with factory() as db:
            row = (await db.exec(select(TenantMembership))).scalars().one()
            row.status = "inactive"
            db.add(row)
            await db.commit()
        yield {"event":"on_chat_model_stream", "name":"intent", "data":{"chunk":SimpleNamespace(content="PRIVATE CACHED CONTENT")}}
    monkeypatch.setattr(terminal_graph, "aget_state", checkpoint)
    monkeypatch.setattr(terminal_graph, "astream_events", events)
    response = terminal_http.post("/api/terminal/invoke", json={"session_id":"own-chat","selected_assets":[{"id":"own-host"}],"user_input":"Read"})
    assert response.status_code == 200 and response.headers["cache-control"] == "no-store"
    assert "PRIVATE CACHED CONTENT" not in response.text and "RUN_FINISHED" not in response.text


@pytest.mark.parametrize("admin_role", ["tenant_admin", "admin", "owner"])
def test_actual_http_audit_outputs_use_current_owner_or_current_admin(terminal_http, terminal_environment, admin_role):
    from app.models.terminal import CommandAuditLog
    factory, _ = terminal_environment
    async def logs(db):
        db.add(CommandAuditLog(id="own-log",tenant_id="tenant-a",user_id="user-a",terminal_session_id="session",asset_id="own-host",command="echo own",mode="agent",security_action="allow",stdout="OWN OUTPUT"))
        db.add(CommandAuditLog(id="foreign-log",tenant_id="tenant-a",user_id="other-user",terminal_session_id="other-session",asset_id="foreign-host",command="echo private",mode="agent",security_action="allow",stdout="FOREIGN OUTPUT"))
    change(factory, logs)
    async def role(db):
        row = (await db.exec(select(TenantMembership))).scalars().one()
        row.role = admin_role
        db.add(row)
    change(factory, role)
    admin = terminal_http.get("/api/terminal/audit-logs")
    assert admin.status_code == 200 and "FOREIGN OUTPUT" in admin.text, admin.text
    async def downgrade(db):
        row = (await db.exec(select(TenantMembership))).scalars().one()
        row.role = "tenant_member"
        db.add(row)
    change(factory, downgrade)
    member = terminal_http.get("/api/terminal/audit-logs")
    assert member.status_code == 200 and "OWN OUTPUT" in member.text and "FOREIGN OUTPUT" not in member.text, member.text
    async def withdraw(db):
        row = (await db.exec(select(TenantMembership))).scalars().one()
        row.status = "inactive"
        db.add(row)
    change(factory, withdraw)
    assert terminal_http.get("/api/terminal/audit-logs").status_code == 403


def test_host_terminal_admission_rechecks_owned_thread_and_targets_before_model(terminal_environment, monkeypatch):
    from test_lead_agent_model_resolution import _make_app_config, _make_model

    from app import runtime_adapters
    from app.platform.execution.trust import ThreadBindingRepository
    from deerflow.agents.lead_agent import agent as lead
    factory, context = terminal_environment
    async def thread():
        repository = ThreadBindingRepository(factory)
        await repository.create("terminal-thread", "tenant-a", "user-a")
        await repository.bind_agent("terminal-thread", "tenant-a", "user-a", "terminal-agent")
    asyncio.run(thread())
    model_calls = []
    provider = {
        "authorize":runtime_adapters._authorize_terminal_context, "set_context":terminal_tools.set_terminal_context,
        "get_tools":terminal_tools.get_terminal_tools, "system_prompt":"Terminal",
    }
    monkeypatch.setattr(lead, "get_terminal_agent_provider", lambda: provider)
    monkeypatch.setattr(lead, "load_enabled_tenant_model_names", lambda tenant: ["safe"])
    monkeypatch.setattr(lead, "get_app_config", lambda: _make_app_config([_make_model("safe",supports_thinking=False)]))
    monkeypatch.setattr(lead, "create_chat_model", lambda **kwargs: model_calls.append(kwargs) or object())
    monkeypatch.setattr(lead, "create_agent", lambda **kwargs: kwargs)
    request = {"context":{**context,"thread_id":"terminal-thread","model_name":"safe"}}
    assert lead._make_terminal_agent(request)["model"] is not None
    assert len(model_calls) == 1
    model_calls.clear()
    bad = {"context":{**request["context"],"selected_assets":[{"id":"foreign-host"}]}}
    with pytest.raises(PermissionError):
        lead._make_terminal_agent(bad)
    assert model_calls == []
    async def withdraw(db):
        row = (await db.exec(select(TenantMembership))).scalars().one()
        row.status = "inactive"
        db.add(row)
    change(factory, withdraw)
    with pytest.raises(PermissionError):
        lead._make_terminal_agent(request)
    assert model_calls == []


def test_actual_pty_withdrawal_records_original_audit_unknown_once_without_stdout(terminal_environment):
    from app.models.terminal import CommandAuditLog
    from app.services.terminal.access import record_terminal_unknown, terminal_lease_validator
    from app.services.terminal.session import TerminalSession
    factory, context = terminal_environment
    async def run():
        session = TerminalSession("session", "own-host")
        session.authority_validator = await terminal_lease_validator(context, "own-host")
        async def audit(command, audit_id, reason):
            await record_terminal_unknown(context, "own-host", command, audit_id, reason)
        session.unknown_writer = audit
        session.start(["/bin/bash", "--noprofile", "--norc"], {}, [])
        pending = asyncio.create_task(session.execute_command("printf 'PRIVATE BEFORE WITHDRAWAL\\n'; sleep 5; printf 'LATE\\n'", broadcast=False))
        for _ in range(40):
            if session.is_executing_command:
                break
            await asyncio.sleep(.01)
        async with factory() as db:
            row = (await db.exec(select(TenantMembership))).scalars().one()
            row.status = "inactive"
            db.add(row)
            await db.commit()
        with pytest.raises((PermissionError, asyncio.CancelledError)):
            await asyncio.wait_for(pending, timeout=5)
        assert session.pty.fd is None and session.command_output_buffer == ""
        await asyncio.gather(*[task for task in [session.read_task, session.authority_task] if task], return_exceptions=True)
        async with factory() as db:
            rows = (await db.exec(select(CommandAuditLog))).scalars().all()
            assert len(rows) == 1
            assert rows[0].return_code is None and rows[0].stdout is None
            assert "remote external effects unknown" in rows[0].stderr
            assert (rows[0].tenant_id, rows[0].user_id, rows[0].asset_id) == ("tenant-a","user-a","own-host")
    asyncio.run(run())


@pytest.mark.parametrize("claim", [{"user_id":"other-user"}, {"tenant_id":"other-tenant"}, {"thread_id":"other-chat"}])
def test_cached_terminal_tool_refuses_different_actual_execution_identity(terminal_environment, monkeypatch, claim):
    async def forbidden(*args):
        pytest.fail("Cached tool used old owner for a different actual caller")
    monkeypatch.setattr(terminal_tools, "_run_on_targets", forbidden)
    tool = terminal_tools.get_terminal_tools()[1]
    with pytest.raises(PermissionError):
        asyncio.run(tool.ainvoke({"path":"/private"}, config={"configurable":claim}))
    assert "config" not in tool.args


@pytest.mark.parametrize("kind", [None, "key", "ssh_key"])
def test_effective_ssh_configuration_uses_only_selected_identity_and_literal_target(tmp_path, kind):
    import subprocess

    from app.services.terminal.session import build_ssh_command
    asset = LocalAsset(id="effective-host",tenant_id="tenant-a",user_id="user-a",name="Owned",ip="127.0.0.1",username="role-user")
    keychain = Keychain(id="owned-key",tenant_id="tenant-a",user_id="user-a",name="Owned",type=kind,value="test-placeholder-key") if kind else None
    command, _, files = build_ssh_command(asset, keychain)
    try:
        output = subprocess.run([command[0],"-G",*command[1:]],capture_output=True,text=True,timeout=10,check=True).stdout
        fields = {}
        for line in output.splitlines():
            key, _, value = line.partition(" ")
            fields.setdefault(key,[]).append(value)
        assert fields["hostname"] == ["127.0.0.1"]
        assert fields["user"] == ["role-user"]
        assert fields["identityagent"] == ["none"] and fields["identitiesonly"] == ["yes"]
        assert fields["identityfile"] == ["/dev/null",*files]
        assert "untrusted-command" not in fields.get("proxycommand",[])
    finally:
        from pathlib import Path
        for file in files:
            Path(file).unlink(missing_ok=True)


@pytest.mark.parametrize("username,host", [("-oProxyCommand=untrusted-command","127.0.0.1"), ("root","other-user@127.0.0.1"), ("root","-oProxyCommand=untrusted-command")])
def test_ssh_options_or_destination_cannot_change_selected_target_identity(username, host):
    from app.services.terminal.session import build_ssh_command
    asset = LocalAsset(id="literal-host",tenant_id="tenant-a",user_id="user-a",name="Own",ip=host,username=username)
    with pytest.raises(PermissionError):
        build_ssh_command(asset)


def test_selected_credential_cannot_fall_back_to_a_different_ssh_purpose():
    from app.services.terminal.session import build_ssh_command
    asset = LocalAsset(id="purpose-host",tenant_id="tenant-a",user_id="user-a",name="Own",ip="127.0.0.1")
    key = Keychain(id="other-purpose",tenant_id="tenant-a",user_id="user-a",name="Other",type="http_token",value="not-a-real-token")
    with pytest.raises(PermissionError):
        build_ssh_command(asset,key)


def test_revoked_terminal_tool_cannot_read_security_config_or_raise_approval(terminal_environment, monkeypatch):
    factory, _ = terminal_environment
    tool = terminal_tools.get_terminal_tools()[0]
    async def withdraw(db):
        row = (await db.exec(select(TenantMembership))).scalars().one()
        row.status = "inactive"
        db.add(row)
    change(factory, withdraw)
    monkeypatch.setattr(terminal_tools, "get_session_factory", lambda: pytest.fail("Revoked tool read security configuration before current member gate"))
    with pytest.raises(PermissionError):
        asyncio.run(tool.ainvoke({"command":"rm -rf /private"}))
