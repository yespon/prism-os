"""Native asset/credential HTTP boundaries using isolated current database facts."""

import asyncio
import os

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import event, select
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool
from sqlmodel.ext.asyncio.session import AsyncSession

from app.gateway.routers import assets
from app.models.assets import AssetGroup, Keychain, LocalAsset
from deerflow.database import secrets_crypto, user_config_service
from deerflow.database.models import Tenant, TenantMembership
from deerflow.database.session import get_session


@pytest.fixture
def asset_client(tmp_path, monkeypatch, native_identity):
    native_identity("user-a")
    database_url = os.environ.get("PRISMOS_SKILL_TEST_DB_URL")
    if database_url:
        parsed = make_url(database_url)
        if parsed.drivername == "sqlite+aiosqlite":
            from pathlib import Path

            candidate = Path(parsed.database or "")
            if not candidate.is_absolute() or not candidate.resolve().is_relative_to(tmp_path.resolve()):
                raise RuntimeError("Shared SQLite fixture must remain inside this owned test directory")
            database_url = None  # This fixture owns its separate assets.sqlite database.
        elif parsed.host not in {"127.0.0.1", "localhost"} or parsed.database != "prismos_skill_probe" or parsed.drivername != "postgresql+asyncpg":
            raise RuntimeError("Asset tests require the owned loopback probe database")
    engine = create_async_engine(database_url or ("sqlite+aiosqlite:///" + str(tmp_path / "assets.sqlite")), poolclass=NullPool)

    @event.listens_for(engine.sync_engine, "connect")
    def foreign_keys(connection, _):
        if engine.dialect.name == "sqlite":
            cursor = connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def setup():
        async with engine.begin() as connection:
            if database_url:
                await connection.exec_driver_sql("DROP SCHEMA public CASCADE")
                await connection.exec_driver_sql("CREATE SCHEMA public")
            for model in (Tenant, TenantMembership, Keychain, AssetGroup, LocalAsset):
                await connection.run_sync(lambda conn, table=model.__table__: table.create(conn))
        async with factory() as db:
            db.add_all(
                [
                    Tenant(id="tenant-a", name="A", slug="asset-a"),
                    Tenant(id="tenant-b", name="B", slug="asset-b"),
                    TenantMembership(tenant_id="tenant-a", user_id="user-a"),
                    Keychain(id="foreign", tenant_id="tenant-b", user_id="user-b", name="Foreign", type="password", value="synthetic-foreign"),
                    AssetGroup(id="foreign-group", tenant_id="tenant-b", user_id="user-b", name="Foreign"),
                ]
            )
            await db.commit()

    asyncio.run(setup())
    monkeypatch.setattr(user_config_service, "get_session_factory", lambda: factory)
    monkeypatch.setenv("DEERFLOW_SECRETS_ENCRYPTION_KEY", "synthetic-asset-key-only-do-not-use-in-production")
    secrets_crypto.reset_crypto_cache()
    app = FastAPI()

    @app.middleware("http")
    async def identity(request, call_next):
        request.state.tenant_id = "tenant-a"
        request.state.user_id = "user-a"
        request.state.tenant_role = "member"
        return await call_next(request)

    async def session():
        async with factory() as db:
            yield db

    app.dependency_overrides[get_session] = session
    app.include_router(assets.router)
    with TestClient(app) as client:
        yield factory, client
    secrets_crypto.reset_crypto_cache()
    asyncio.run(engine.dispose())


def withdraw(factory):
    async def change():
        async with factory() as db:
            row = (await db.exec(select(TenantMembership))).scalars().one()
            row.status = "inactive"
            await db.commit()

    asyncio.run(change())


@pytest.mark.parametrize("path", ["/keychains", "/groups", "/local"])
def test_withdrawn_member_cannot_observe_asset_metadata(asset_client, path):
    factory, client = asset_client
    withdraw(factory)
    response = client.get("/api/v1/assets" + path)
    assert response.status_code == 403
    assert "Foreign" not in response.text


def test_withdrawn_member_cannot_create_persisted_credential(asset_client):
    factory, client = asset_client
    withdraw(factory)
    response = client.post("/api/v1/assets/keychains", json={"name": "blocked", "type": "password", "value": "synthetic-own-secret"})
    assert response.status_code == 403

    async def stored():
        async with factory() as db:
            return (await db.exec(select(Keychain).where(Keychain.user_id == "user-a"))).scalars().all()

    assert asyncio.run(stored()) == []


@pytest.mark.parametrize("field,value", [("keychain_id", "foreign"), ("group_id", "foreign-group"), ("keychain_id", "missing")])
def test_foreign_or_missing_reference_cannot_be_bound(asset_client, field, value):
    factory, client = asset_client
    response = client.post("/api/v1/assets/local", json={"name": "blocked", "ip": "127.0.0.1", "username": "owned", field: value})
    assert response.status_code == 404

    async def stored():
        async with factory() as db:
            return (await db.exec(select(LocalAsset))).scalars().all()

    assert asyncio.run(stored()) == []


def test_credential_is_encrypted_and_never_returned_in_dto(asset_client):
    factory, client = asset_client
    response = client.post("/api/v1/assets/keychains", json={"name": "Owned", "type": "password", "value": "synthetic-own-secret"})
    assert response.status_code == 200, response.text
    assert "value" not in response.json() and "synthetic-own-secret" not in response.text
    identifier = response.json()["id"]

    async def stored():
        async with factory() as db:
            return await db.get(Keychain, identifier)

    row = asyncio.run(stored())
    assert row.value.startswith("enc:v1:") and "synthetic-own-secret" not in row.value
    assert secrets_crypto.decrypt_text(row.value) == "synthetic-own-secret"
    observed = client.get("/api/v1/assets/keychains")
    assert observed.status_code == 200 and "synthetic-own-secret" not in observed.text
    assert observed.headers["Cache-Control"] == "private, no-store"


def test_missing_encryption_configuration_never_writes_plaintext(asset_client, monkeypatch):
    _, client = asset_client
    monkeypatch.delenv("DEERFLOW_SECRETS_ENCRYPTION_KEY")
    secrets_crypto.reset_crypto_cache()
    response = client.post("/api/v1/assets/keychains", json={"name": "blocked", "type": "password", "value": "synthetic-own-secret"})
    assert response.status_code == 503
    assert "synthetic-own-secret" not in response.text


@pytest.mark.parametrize("credential_type", ["password", "key", "ssh_key"])
def test_original_credential_types_remain_available(asset_client, credential_type):
    _, client = asset_client
    response = client.post("/api/v1/assets/keychains", json={"name": "Owned", "type": credential_type, "value": "synthetic-own-secret"})
    assert response.status_code == 200
    assert response.json()["type"] == credential_type


def test_credential_with_active_asset_reference_cannot_be_orphaned(asset_client):
    _, client = asset_client
    credential = client.post("/api/v1/assets/keychains", json={"name": "Owned", "type": "password", "value": "synthetic-own-secret"}).json()
    asset = client.post("/api/v1/assets/local", json={"name": "Owned host", "ip": "127.0.0.1", "username": "owned", "keychain_id": credential["id"]})
    assert asset.status_code == 200
    assert client.delete("/api/v1/assets/keychains/" + credential["id"]).status_code == 409
    assert client.get("/api/v1/assets/local").json()[0]["keychain_id"] == credential["id"]


def test_foreign_connection_credential_never_starts_subprocess(asset_client, monkeypatch):
    _, client = asset_client

    async def forbidden(*args, **kwargs):
        pytest.fail("Foreign credential must not start a connection")

    monkeypatch.setattr(assets.asyncio, "create_subprocess_exec", forbidden)
    response = client.post("/api/v1/assets/test-connection", json={"name": "Owned", "ip": "127.0.0.1", "username": "owned", "keychain_id": "foreign"})
    assert response.status_code == 404


def test_ciphertext_like_password_is_stored_as_literal_input(asset_client):
    factory, client = asset_client
    literal = "enc:v1:synthetic-literal-password"
    response = client.post("/api/v1/assets/keychains", json={"name": "Literal", "type": "password", "value": literal})
    assert response.status_code == 200

    async def read():
        async with factory() as db:
            return await db.get(Keychain, response.json()["id"])
    stored = asyncio.run(read())
    assert stored.value != literal and secrets_crypto.decrypt_text(stored.value) == literal


def test_duplicate_credential_has_private_conflict_response(asset_client):
    _, client = asset_client
    body = {"name": "Owned", "type": "password", "value": "synthetic-own-secret"}
    assert client.post("/api/v1/assets/keychains", json=body).status_code == 200
    response = client.post("/api/v1/assets/keychains", json=body)
    assert response.status_code == 409
    assert "synthetic-own-secret" not in response.text and "INSERT" not in response.text


def test_failed_asset_commit_rolls_back_inline_credential(asset_client):
    from sqlalchemy.exc import IntegrityError

    factory, client = asset_client
    engine = factory.kw["bind"].sync_engine

    def fail_asset(_conn, _cursor, statement, _parameters, _context, _many):
        if statement.startswith("INSERT INTO local_assets"):
            raise IntegrityError("synthetic asset failure", {}, RuntimeError("owned fault"))
    event.listen(engine, "before_cursor_execute", fail_asset)
    try:
        response = client.post("/api/v1/assets/local", json={"name": "Owned host", "ip": "127.0.0.1", "username": "owned", "password": "synthetic-own-secret"})
        assert response.status_code == 409
    finally:
        event.remove(engine, "before_cursor_execute", fail_asset)

    async def rows():
        async with factory() as db:
            return (await db.exec(select(Keychain).where(Keychain.user_id == "user-a"))).scalars().all(), (await db.exec(select(LocalAsset))).scalars().all()
    assert asyncio.run(rows()) == ([], [])


def test_update_cannot_attach_foreign_reference_or_overwrite_existing_asset(asset_client):
    _, client = asset_client
    initial = {"name": "Owned", "ip": "127.0.0.1", "username": "owned"}
    created = client.post("/api/v1/assets/local", json=initial)
    assert created.status_code == 200
    changed = initial | {"name": "Forbidden change", "keychain_id": "foreign"}
    response = client.put("/api/v1/assets/local/" + created.json()["id"], json=changed)
    assert response.status_code == 404
    assert client.get("/api/v1/assets/local").json()[0]["name"] == "Owned"


def test_encrypted_ssh_consumption_is_owned_and_wrong_key_fails_closed(asset_client, monkeypatch):
    from pathlib import Path

    from app.services.terminal.session import build_ssh_command

    factory, client = asset_client
    created = client.post("/api/v1/assets/keychains", json={"name": "Owned", "type": "password", "value": "synthetic-own-secret"})

    async def read():
        async with factory() as db:
            return await db.get(Keychain, created.json()["id"])
    credential = asyncio.run(read())
    target = LocalAsset(id="owned", tenant_id="tenant-a", user_id="user-a", name="Owned", ip="127.0.0.1", username="owned")
    _, _, files = build_ssh_command(target, credential)
    try:
        assert len(files) == 1 and "synthetic-own-secret" in Path(files[0]).read_text()
        assert Path(files[0]).stat().st_mode & 0o077 == 0
    finally:
        for path in files:
            Path(path).unlink()
    with pytest.raises(PermissionError, match="owner"):
        build_ssh_command(target, credential.model_copy(update={"tenant_id": "tenant-b"}))
    monkeypatch.setenv("DEERFLOW_SECRETS_ENCRYPTION_KEY", "synthetic-other-key")
    secrets_crypto.reset_crypto_cache()
    with pytest.raises(PermissionError, match="decrypt"):
        build_ssh_command(target, credential)


@pytest.mark.parametrize("change", ["member", "credential"])
def test_connection_probe_stops_actual_local_transport_children_on_withdrawal(asset_client, tmp_path, monkeypatch, change):
    """Actual isolated process group; SSH/network are deliberately not exercised."""
    import sys
    import time
    from concurrent.futures import ThreadPoolExecutor

    factory, client = asset_client
    credential = client.post("/api/v1/assets/keychains", json={"name": "Owned", "type": "password", "value": "synthetic-own-secret"}).json()
    started, late = tmp_path / "started", tmp_path / "late"
    program = (
        "import os,time;from pathlib import Path;"
        + f"Path({str(started)!r}).write_text('started');"
        + "child=os.fork();\n"
        + f"if child==0:\n time.sleep(2);Path({str(late)!r}).write_text('late');os._exit(0)\n"
        + "time.sleep(30)"
    )
    monkeypatch.setattr(assets, "build_ssh_command", lambda *args, **kwargs: ([sys.executable, "-c", program], {}, []))
    with ThreadPoolExecutor(max_workers=1) as executor:
        pending = executor.submit(client.post, "/api/v1/assets/test-connection", json={"name": "Owned", "ip": "127.0.0.1", "username": "owned", "keychain_id": credential["id"]})
        deadline = time.monotonic() + 5
        while not started.exists() and time.monotonic() < deadline:
            time.sleep(0.01)
        assert started.exists()
        if change == "member":
            withdraw(factory)
        else:
            rotated = client.put("/api/v1/assets/keychains/" + credential["id"], json={"name": "Owned", "type": "password", "value": "synthetic-rotated-secret"})
            assert rotated.status_code == 200
        response = pending.result(timeout=5)
    assert response.status_code == 503 and response.json()["detail"]["inspection_required"]
    time.sleep(2.1)
    assert not late.exists()


def test_connection_probe_never_inherits_host_environment(asset_client, monkeypatch):
    import sys

    _, client = asset_client
    monkeypatch.setenv("PRISMOS_HOST_CREDENTIAL_CANARY", "must-not-reach-child")
    program = "import os;assert 'PRISMOS_HOST_CREDENTIAL_CANARY' not in os.environ;assert 'SSH_AUTH_SOCK' not in os.environ"
    monkeypatch.setattr(assets, "build_ssh_command", lambda *args, **kwargs: ([sys.executable, "-c", program], {}, []))
    response = client.post("/api/v1/assets/test-connection", json={"name": "Owned", "ip": "127.0.0.1", "username": "owned"})
    assert response.status_code == 200 and response.json()["status"] == "ok"


def test_original_rotation_seals_legacy_rows_and_rotates_keychains_atomically(asset_client, monkeypatch):
    import importlib.util
    import os
    from pathlib import Path

    from app.models.governance import PlatformTicketSecretRecord
    from deerflow.database.models import TenantMcpServer, TenantModelConfig, UserConfig

    factory, client = asset_client
    owned = client.post("/api/v1/assets/keychains", json={"name": "Owned", "type": "password", "value": "enc:literal-owned-password"}).json()
    engine = factory.kw["bind"]

    async def prepare():
        async with engine.begin() as connection:
            for model in (UserConfig, TenantModelConfig, TenantMcpServer, PlatformTicketSecretRecord):
                await connection.run_sync(lambda conn, table=model.__table__: table.create(conn))

    async def values():
        async with factory() as db:
            return {row.id: row.value for row in (await db.exec(select(Keychain))).scalars().all()}

    asyncio.run(prepare())
    path = Path(__file__).resolve().parents[1] / "scripts/rotate_encrypted_secrets.py"
    spec = importlib.util.spec_from_file_location("credential_rotation_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "get_session_factory", lambda: factory)
    old_key = os.environ["DEERFLOW_SECRETS_ENCRYPTION_KEY"]
    new_key = "synthetic-maintenance-new-key"
    original = asyncio.run(values())
    asyncio.run(module._rotate(old_key, new_key, True))
    assert asyncio.run(values()) == original
    asyncio.run(module._rotate(old_key, new_key, False))
    rotated = asyncio.run(values())
    assert all(value.startswith("enc:v1:") for value in rotated.values())
    assert secrets_crypto.decrypt_text_strict(rotated[owned["id"]], new_key) == "enc:literal-owned-password"
    assert secrets_crypto.decrypt_text_strict(rotated["foreign"], new_key) == "synthetic-foreign"
    with pytest.raises(ValueError, match="decryption"):
        asyncio.run(module._rotate("synthetic-wrong-old-key", "synthetic-other-new-key", False))
    assert asyncio.run(values()) == rotated
