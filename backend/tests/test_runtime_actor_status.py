"""Current native membership must not outlive the original account authority."""
import asyncio
from datetime import UTC, datetime

import pytest
from namespace_availability import requires_namespaces  # noqa: F401
from sqlalchemy import create_engine, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool
from sqlmodel.ext.asyncio.session import AsyncSession
from test_credential_asset_access import asset_client as native_asset_client
from test_runtime_source_revocation import source_runtime as native_source_runtime
from test_skill_member_tools import configured, scoped_client  # noqa: F401
from test_skill_member_tools import selected_runtime as member_runtime
from test_skill_reference_transactions import durable_sqlite  # noqa: F401
from test_skill_scoped_commands import command_runtime as native_command_runtime

from app.gateway import auth_db
from app.integrations import actor_authorization
from app.integrations.file_access import verify_member
from deerflow.database.models import Tenant, TenantMembership
from deerflow.runtime import ExecutionTrustError

command_runtime = native_command_runtime
selected_runtime = member_runtime
asset_client = native_asset_client
source_runtime = native_source_runtime


@pytest.fixture
def actor_databases(tmp_path, monkeypatch):
    import os

    from sqlalchemy.engine import make_url

    candidate = os.environ.get("PRISMOS_SKILL_TEST_DB_URL", "")
    postgres = candidate.startswith("postgresql+")
    if postgres:
        parsed = make_url(candidate)
        if parsed.drivername != "postgresql+asyncpg" or parsed.host not in {"127.0.0.1", "localhost"} or parsed.database != "prismos_skill_probe":
            raise RuntimeError("Account tests require the owned loopback probe database")
    config = create_async_engine(candidate if postgres else ("sqlite+aiosqlite:///" + str(tmp_path / "native.sqlite")), poolclass=NullPool)
    identity = create_engine(
        candidate.replace("postgresql+asyncpg://", "postgresql+psycopg://", 1) if postgres else ("sqlite+pysqlite:///" + str(tmp_path / "auth.sqlite")), **({} if postgres else {"connect_args": {"check_same_thread": False}}),
    )
    monkeypatch.setattr(actor_authorization, "auth_connection", auth_db.auth_connection)
    monkeypatch.setattr(auth_db, "_engine", identity)
    monkeypatch.setattr(auth_db, "_db_type", "postgres" if postgres else "sqlite")
    factory = async_sessionmaker(config, class_=AsyncSession, expire_on_commit=False)

    async def setup():
        async with config.begin() as conn:
            if postgres:
                await conn.exec_driver_sql("DROP SCHEMA public CASCADE")
                await conn.exec_driver_sql("CREATE SCHEMA public")
            for model in (Tenant, TenantMembership):
                await conn.run_sync(lambda connection, table=model.__table__: table.create(connection))
        async with factory() as db:
            db.add(Tenant(id="tenant-a", name="A", slug="actor-a"))
            db.add(TenantMembership(tenant_id="tenant-a", user_id="actor-a", status="active"))
            await db.commit()
    asyncio.run(setup())
    with identity.begin() as conn:
        conn.execute(text('CREATE TABLE "user" (id TEXT PRIMARY KEY, role TEXT, status TEXT, "mustChangePassword" BOOLEAN)'))
        conn.execute(text('INSERT INTO "user" VALUES (:id, :role, :status, :change)'), {"id": "actor-a", "role": "user", "status": "active", "change": False})
    yield factory, identity
    asyncio.run(config.dispose())
    identity.dispose()


def verify(factory):
    async def check():
        async with factory() as db:
            await verify_member(db, "tenant-a", "actor-a")
    asyncio.run(check())


@requires_namespaces
def test_current_active_account_and_member_are_usable(actor_databases):
    factory, _ = actor_databases
    verify(factory)


@pytest.mark.parametrize("change", ["suspended", "deleted", "password-reset"])
@requires_namespaces
def test_original_account_revocation_blocks_a_still_active_native_membership(actor_databases, change):
    factory, identity = actor_databases
    verify(factory)
    with identity.begin() as conn:
        if change == "suspended":
            conn.execute(text('UPDATE "user" SET status=:status WHERE id=:id'), {"status": "suspended", "id": "actor-a"})
        elif change == "deleted":
            conn.execute(text('DELETE FROM "user" WHERE id=:id'), {"id": "actor-a"})
        else:
            conn.execute(text('UPDATE "user" SET "mustChangePassword"=:change WHERE id=:id'), {"change": True, "id": "actor-a"})
    with pytest.raises(ExecutionTrustError):
        verify(factory)


@requires_namespaces
def test_auth_store_failure_is_not_permission_to_continue(actor_databases, monkeypatch):
    factory, _ = actor_databases

    def unavailable():
        raise RuntimeError("synthetic unavailable auth store")
    monkeypatch.setattr(auth_db, "get_auth_engine", unavailable)
    with pytest.raises(ExecutionTrustError):
        verify(factory)


@pytest.mark.parametrize("change", ["suspended", "deleted", "password-reset"])
@requires_namespaces
def test_account_withdrawal_stops_actual_scoped_command(command_runtime, change):
    import shlex
    import time
    from concurrent.futures import ThreadPoolExecutor
    from pathlib import Path

    from deerflow.sandbox import tools

    _, _, _, _, runtime, _ = command_runtime
    started = Path(runtime.state["thread_data"]["workspace_path"]) / "account-started"
    late = Path(runtime.state["thread_data"]["outputs_path"]) / "account-late"
    source = "from pathlib import Path;import time;Path('/mnt/user-data/workspace/account-started').write_text('ready');time.sleep(1);Path('/mnt/user-data/outputs/account-late').write_text('late');print('WITHDRAWN ACCOUNT OUTPUT')"
    with ThreadPoolExecutor(max_workers=1) as executor:
        pending = executor.submit(tools.bash_tool.func, runtime, "Account lease", "python -c " + shlex.quote(source))
        deadline = time.monotonic() + 5
        while not started.exists() and time.monotonic() < deadline:
            time.sleep(.01)
        assert started.exists()
        with auth_db.get_auth_engine().begin() as conn:
            if change == "deleted":
                conn.execute(text('DELETE FROM "user" WHERE id=:id'), {"id": "user-a"})
            elif change == "password-reset":
                conn.execute(text('UPDATE "user" SET "mustChangePassword"=:value WHERE id=:id'), {"value": True, "id": "user-a"})
            else:
                conn.execute(text('UPDATE "user" SET status=:value WHERE id=:id'), {"value": "suspended", "id": "user-a"})
        result = pending.result(timeout=5)
    assert "Error:" in result and "WITHDRAWN ACCOUNT OUTPUT" not in result
    assert not late.exists()


@requires_namespaces
def test_account_suspension_stops_actual_connection_transport(asset_client, tmp_path, monkeypatch):
    import sys
    import time
    from concurrent.futures import ThreadPoolExecutor

    from app.gateway.routers import assets

    _, client = asset_client
    started, late = tmp_path / "account-connection-started", tmp_path / "account-connection-late"
    program = f"from pathlib import Path;import time;Path({str(started)!r}).write_text('ready');time.sleep(1);Path({str(late)!r}).write_text('late')"
    monkeypatch.setattr(assets, "build_ssh_command", lambda *args, **kwargs: ([sys.executable, "-c", program], {}, []))
    with ThreadPoolExecutor(max_workers=1) as executor:
        pending = executor.submit(client.post, "/api/v1/assets/test-connection", json={"name": "Owned", "ip": "127.0.0.1", "username": "owned"})
        deadline = time.monotonic() + 5
        while not started.exists() and time.monotonic() < deadline:
            time.sleep(.01)
        assert started.exists()
        with auth_db.get_auth_engine().begin() as connection:
            connection.execute(text('UPDATE "user" SET status=:status WHERE id=:id'), {"status": "suspended", "id": "user-a"})
        response = pending.result(timeout=5)
    assert response.status_code == 503 and response.json()["detail"]["inspection_required"]
    assert not late.exists()


@requires_namespaces
def test_legacy_auth_schema_still_requires_an_existing_account(actor_databases):
    factory, identity = actor_databases
    with identity.begin() as connection:
        connection.execute(text('ALTER TABLE "user" DROP COLUMN status'))
        connection.execute(text('ALTER TABLE "user" DROP COLUMN "mustChangePassword"'))
    verify(factory)
    with identity.begin() as connection:
        connection.execute(text('DELETE FROM "user" WHERE id=:id'), {"id": "actor-a"})
    with pytest.raises(ExecutionTrustError):
        verify(factory)


@pytest.mark.parametrize("entry", ["source", "capability"])
@pytest.mark.parametrize("change", ["suspended", "deleted", "password-reset"])
@requires_namespaces
def test_revoked_account_cannot_authorize_auto_source_or_mint_capability(source_runtime, entry, change):
    from app.alerting import diagnosis_authorization
    from app.runtime_adapters import verify_native_selection

    factory, _, agent, _, runtime, _ = source_runtime
    with auth_db.get_auth_engine().begin() as connection:
        if change == "deleted":
            connection.execute(text('DELETE FROM "user" WHERE id=:id'), {"id": "user-a"})
        elif change == "password-reset":
            connection.execute(text('UPDATE "user" SET "mustChangePassword"=:value WHERE id=:id'), {"value": True, "id": "user-a"})
        else:
            connection.execute(text('UPDATE "user" SET status=:value WHERE id=:id'), {"value": "suspended", "id": "user-a"})

    async def attempt():
        async with factory() as db:
            if entry == "source":
                await diagnosis_authorization.current_authorization(db, "live-source", "tenant-a", agent, expected_actor="user-a", severity="critical")
            else:
                await verify_native_selection(db, "tenant-a", "user-a", runtime.context["agent_name"], agent)
    with pytest.raises(ExecutionTrustError):
        asyncio.run(attempt())

@pytest.mark.parametrize("change", ["active", "suspended", "deleted", "password-reset"])
@requires_namespaces
def test_default_graph_checks_current_actor_before_capability_consumption(actor_databases, monkeypatch, change):
    from app import runtime_adapters
    from app.models.governance import PlatformThreadBindingRecord

    factory, identity = actor_databases
    calls = []

    async def setup():
        async with factory() as db:
            await db.run_sync(lambda session: PlatformThreadBindingRecord.__table__.create(session.connection()))
            db.add(PlatformThreadBindingRecord(thread_id="default-owned", tenant_id="tenant-a", user_id="actor-a", agent_name="__default__", created_at=datetime.now(UTC)))
            await db.commit()
    asyncio.run(setup())
    if change != "active":
        with identity.begin() as connection:
            if change == "deleted":
                connection.execute(text('DELETE FROM "user" WHERE id=:id'), {"id": "actor-a"})
            elif change == "password-reset":
                connection.execute(text('UPDATE "user" SET "mustChangePassword"=:value WHERE id=:id'), {"value": True, "id": "actor-a"})
            else:
                connection.execute(text('UPDATE "user" SET status=:value WHERE id=:id'), {"value": "suspended", "id": "actor-a"})

    class Capabilities:
        def __init__(self, *args, **kwargs):
            pass

        async def consume(self, *args, **kwargs):
            calls.append(args)
            return {"agent_id": None}

    monkeypatch.setattr(runtime_adapters, "get_session_factory", lambda: factory)
    monkeypatch.setattr(runtime_adapters, "ExecutionCapabilityRepository", Capabilities)
    operation = runtime_adapters._consume_graph_capability("opaque", "tenant-a", "actor-a", "default-owned", None)
    if change == "active":
        assert asyncio.run(operation) == {"agent_id": None}
        assert len(calls) == 1
    else:
        with pytest.raises(ExecutionTrustError):
            asyncio.run(operation)
        assert not calls