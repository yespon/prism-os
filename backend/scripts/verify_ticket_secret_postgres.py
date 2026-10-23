"""Verify ticket migrations/CAS in an owned disposable PostgreSQL container.

Uses a cached image; never connects to a supplied deployment database.
Run from backend: uv run --locked python -m scripts.verify_ticket_secret_postgres
"""

import argparse
import asyncio
import json
import os
import secrets
import subprocess
import sys
import tempfile
import time
from copy import deepcopy
from pathlib import Path

import yaml
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

ROOT = Path(__file__).resolve().parents[2]
HEAD = "n8h9i0j1k2l3"
TENANT = "postgres-probe-tenant"
URL = "https://tickets.example/probe-private-path?token=probe-private-query"
HEADER = "Bearer probe-private-header"


def command(args, *, env=None, data=None, timeout=120, accepted=(0,)):
    result = subprocess.run(args, cwd=ROOT / "backend", env=env, input=data, capture_output=True, timeout=timeout)
    if result.returncode not in accepted:
        raise RuntimeError("probe subprocess failed")
    return result


def config_file(directory, database_url, name="config.yaml"):
    config = yaml.safe_load((ROOT / "config.example.yaml").read_text())
    config["database"]["url"] = database_url
    config["database"]["echo"] = False
    config["database"]["auth"]["url"] = f"sqlite+aiosqlite:///{directory}/auth.db"
    path = directory / name
    path.write_text(yaml.safe_dump(config))
    path.chmod(0o600)
    return path


async def verify_database(value, *, initialize=False, rotate=False):
    from fastapi import FastAPI
    from httpx import ASGITransport, AsyncClient

    from app.alerting import ticket_secret_migration
    from app.alerting.ticket_secret_migration import TicketMigrationError
    from app.alerting.ticket_secrets import TicketSecretRepository
    from app.gateway.routers import ticket_secrets
    from app.models.alerting import AlertSource
    from app.models.governance import PlatformAuditEventRecord, PlatformTicketSecretRecord
    from app.platform.contracts import SecretRef

    engine = create_async_engine(value, echo=False, hide_parameters=True, pool_pre_ping=True)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    try:
        async with factory() as session:
            assert (await session.exec(text("SELECT version_num FROM alembic_version"))).scalar_one() == HEAD
            version = (await session.exec(text("SELECT version()"))).scalar_one().split(" on ", 1)[0]
            if initialize:
                legacy = {"ticket": {"provider": "webhook", "webhook_url": URL, "headers": {"Authorization": HEADER}, "template": {"title": "{{ incident.title }}"}}, "other": {"unicode": "配置", "enabled": False}}
                session.add_all(
                    [
                        AlertSource(id="probe-a", tenant_id=TENANT, name="active", config_json=legacy),
                        AlertSource(id="probe-disabled", tenant_id=TENANT, name="disabled", status="disabled", config_json=legacy),
                        AlertSource(id="probe-other", tenant_id="other-tenant", name="other", config_json=legacy),
                    ]
                )
                await session.commit()
                return {"server": version, "seeded": True}
            source = await session.get(AlertSource, "probe-a")
            config = deepcopy(source.config_json)
            ref = SecretRef.model_validate(config["ticket"]["secret_ref"])
            assert "webhook_url" not in config["ticket"] and "headers" not in config["ticket"]
            assert config["other"] == {"unicode": "配置", "enabled": False}
            assert (await TicketSecretRepository().read(session, TENANT, source.id, ref)).webhook_url == URL
            assert (await session.get(AlertSource, "probe-disabled")).status == "disabled"
            assert "webhook_url" in (await session.get(AlertSource, "probe-other")).config_json["ticket"]
            events = (await session.exec(select(PlatformAuditEventRecord))).all()
            assert len([event for event in events if event.event_type == "secret.migrated"]) == 2
            for event in events:
                assert all(private not in event.model_dump_json() for private in ("probe-private-path", "probe-private-query", "probe-private-header"))
            if not rotate:
                return {"server": version, "binding": True, "audit": True, "tenant_isolation": True, "disabled_preserved": True}

        # Actual PostgreSQL JSON CAS rejects stale entire configuration.
        async with factory() as session:
            source = await session.get(AlertSource, "probe-a")
            previous = deepcopy(source.config_json)
            source.config_json = {**previous, "changed": True}
            await session.flush()
            try:
                await ticket_secret_migration._replace_config(session, source, previous, previous)
            except TicketMigrationError as error:
                assert str(error) == "source_configuration_changed"
            else:
                raise AssertionError("stale JSON CAS was accepted")
            await session.rollback()

        # Auth states are controlled test fixtures; this does not prove live identity propagation.
        app = FastAPI()
        app.include_router(ticket_secrets.router)

        @app.middleware("http")
        async def identity(request, call_next):
            request.state.tenant_id = TENANT
            request.state.tenant_role = "admin"
            request.state.user_id = "probe-admin"
            return await call_next(request)

        async def dependency():
            async with factory() as session:
                yield session

        app.dependency_overrides[ticket_secrets.get_session] = dependency
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            responses = await asyncio.gather(*[client.put("/api/alert-sources/probe-a/ticket-secret", json={"webhook_url": URL, "headers": {"Authorization": HEADER}, "expected_ref_id": ref.id}) for _ in range(2)])
            assert sorted(response.status_code for response in responses) == [200, 409]
            winner = next(response.json()["secret_ref"]["id"] for response in responses if response.status_code == 200)

        async with factory() as session:
            source = await session.get(AlertSource, "probe-a")
            assert source.config_json["ticket"]["secret_ref"]["id"] == winner
            rows = (await session.exec(select(PlatformTicketSecretRecord).where(PlatformTicketSecretRecord.source_id == "probe-a"))).all()
            assert len(rows) == 2 and [row.id for row in rows if row.active] == [winner]
        # A failure on the second audit must roll back both sources and credentials.
        from app.platform.audit.repository import AuditEventRepository

        original = AuditEventRepository.append_in_session
        count = 0

        async def fail_second(session, event):
            nonlocal count
            count += 1
            if count == 2:
                raise RuntimeError("probe audit unavailable")
            await original(session, event)

        async with factory() as session:
            for number in (1, 2):
                session.add(AlertSource(id=f"rollback-{number}", tenant_id="rollback-tenant", name=f"rollback-{number}", config_json={"ticket": {"webhook_url": URL, "headers": {"Authorization": HEADER}}}))
            await session.commit()
        AuditEventRepository.append_in_session = staticmethod(fail_second)
        try:
            try:
                await ticket_secret_migration.migrate_ticket_secret_refs(factory, "rollback-tenant", apply=True)
            except TicketMigrationError as error:
                assert str(error) == "storage_or_audit_unavailable"
            else:
                raise AssertionError("audit failure was accepted")
        finally:
            AuditEventRepository.append_in_session = staticmethod(original)
        async with factory() as session:
            assert not (await session.exec(select(PlatformTicketSecretRecord).where(PlatformTicketSecretRecord.tenant_id == "rollback-tenant"))).all()
            assert not (await session.exec(select(PlatformAuditEventRecord).where(PlatformAuditEventRecord.tenant_id == "rollback-tenant"))).all()
            for number in (1, 2):
                assert "webhook_url" in (await session.get(AlertSource, f"rollback-{number}")).config_json["ticket"]
        return {"json_cas": True, "rotation_single_winner": True, "atomic_audit_rollback": True}
    finally:
        await engine.dispose()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", default="postgres:16-alpine")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    owned = None
    owned_volume = None
    phase = "cached image"
    report = {"task": "N04", "scope": "isolated PostgreSQL only", "m1_exit": False, "pending": ["target deployment", "real model and webhook", "Gateway/LangGraph live identity", "deployment tracing", "feature-switch rollback"]}
    try:
        image = json.loads(command(["docker", "image", "inspect", args.image]).stdout)[0]
        report["image_id"] = image["Id"]
        report["image"] = args.image
        with tempfile.TemporaryDirectory(prefix="prismos-ticket-postgres-") as folder:
            directory = Path(folder)
            name = f"prismos-ticket-probe-{secrets.token_hex(6)}"
            password = secrets.token_urlsafe(24)
            phase = "owned container"
            owned_volume = command(["docker", "volume", "create", "--label", "com.prismos.test=octop-n04", name + "-data"]).stdout.decode().strip()
            owned = (
                command(
                    [
                        "docker",
                        "run",
                        "--detach",
                        "--name",
                        name,
                        "--label",
                        "com.prismos.test=octop-n04",
                        "--publish",
                        "127.0.0.1::5432",
                        "--mount",
                        f"type=volume,source={owned_volume},target=/var/lib/postgresql/data",
                        "--env",
                        "POSTGRES_USER=prismos_test",
                        "--env",
                        f"POSTGRES_PASSWORD={password}",
                        "--env",
                        "POSTGRES_DB=prismos_test",
                        args.image,
                    ]
                )
                .stdout.decode()
                .strip()
            )
            for _ in range(60):
                ready = command(["docker", "exec", owned, "pg_isready", "-h", "127.0.0.1", "-U", "prismos_test"], accepted=(0, 1, 2))
                if ready.returncode == 0:
                    break
                time.sleep(0.5)
            else:
                raise RuntimeError("database did not become ready")
            port = command(["docker", "port", owned, "5432/tcp"]).stdout.decode().strip().rsplit(":", 1)[1]
            value = make_url("postgresql+asyncpg://prismos_test@127.0.0.1/prismos_test").set(password=password, port=int(port)).render_as_string(hide_password=False)
            config = config_file(directory, value)
            env = {key: os.environ[key] for key in ("PATH", "HOME", "LANG", "LC_ALL") if key in os.environ}
            env.update(PRISMOS_CONFIG_PATH=str(config), PRISMOS_HOME=str(directory / "home"), PYTHONPATH=str(ROOT / "backend"), DEERFLOW_SECRETS_ENCRYPTION_KEY="isolated-postgres-probe-key", PRISMOS_TICKET_SECRET_ADMIN_TENANT=TENANT)
            os.environ["DEERFLOW_SECRETS_ENCRYPTION_KEY"] = env["DEERFLOW_SECRETS_ENCRYPTION_KEY"]
            os.environ["PRISMOS_TICKET_SECRET_ADMIN_TENANT"] = TENANT
            phase = "Alembic full-chain upgrade"
            command([sys.executable, "-m", "alembic", "upgrade", "head"], env=env)
            command([sys.executable, "-m", "alembic", "downgrade", "m7g8h9i0j1k2"], env=env)
            command([sys.executable, "-m", "alembic", "upgrade", "head"], env=env)
            report["empty_downgrade_reupgrade"] = True
            report["upgrade_head"] = HEAD
            report.update(asyncio.run(verify_database(value, initialize=True)))
            phase = "protected pre-migration backup"
            backup = command(["docker", "exec", owned, "pg_dump", "-U", "prismos_test", "-d", "prismos_test", "-Fc"]).stdout
            backup_path = directory / "before-migration.dump"
            backup_path.write_bytes(backup)
            backup_path.chmod(0o600)
            report["pre_migration_backup"] = True
            phase = "migration CLI"
            cli = [sys.executable, "-m", "scripts.migrate_ticket_secret_refs", "--tenant", TENANT, "--config", str(config)]
            for suffix, mode, expected in [([], "dry-run", 0), (["--apply"], "apply", 2), (["--apply"], "apply", 0)]:
                result = command(cli + suffix, env=env)
                output = json.loads(result.stdout)
                assert output["status"] == "succeeded" and output["mode"] == mode and output["migrated"] == expected
                assert not result.stderr and all(private.encode() not in result.stdout for private in ("probe-private-path", "probe-private-query", "probe-private-header"))
            report["cli_dry_run_apply_repeat"] = True
            report.update(asyncio.run(verify_database(value, rotate=True)))
            phase = "container restart"
            command(["docker", "restart", owned])
            for _ in range(60):
                if command(["docker", "exec", owned, "pg_isready", "-h", "127.0.0.1", "-U", "prismos_test"], accepted=(0, 1, 2)).returncode == 0:
                    break
                time.sleep(0.5)
            port = command(["docker", "port", owned, "5432/tcp"]).stdout.decode().strip().rsplit(":", 1)[1]
            value = make_url(value).set(port=int(port)).render_as_string(hide_password=False)
            report.update(asyncio.run(verify_database(value)))
            report["restart_storage_verified"] = True
            phase = "encrypted backup restore"
            backup = command(["docker", "exec", owned, "pg_dump", "-U", "prismos_test", "-d", "prismos_test", "-Fc"]).stdout
            command(["docker", "exec", owned, "psql", "-U", "prismos_test", "-d", "prismos_test", "-c", "CREATE DATABASE prismos_restore"])
            command(["docker", "exec", "-i", owned, "pg_restore", "-U", "prismos_test", "-d", "prismos_restore", "--exit-on-error"], data=backup)
            restored = make_url(value).set(database="prismos_restore").render_as_string(hide_password=False)
            report.update(asyncio.run(verify_database(restored)))
            report["encrypted_backup_restore"] = True
            phase = "nonempty downgrade protection"
            restore_config = config_file(directory, restored, "restore.yaml")
            restore_env = {**env, "PRISMOS_CONFIG_PATH": str(restore_config)}
            rejected = command([sys.executable, "-m", "alembic", "downgrade", "m7g8h9i0j1k2"], env=restore_env, accepted=(1,))
            assert b"records exist" in rejected.stderr
            asyncio.run(verify_database(restored))
            report["nonempty_downgrade_blocked"] = True
            phase = "pre-migration backup restore and remigration"
            command(["docker", "exec", owned, "psql", "-U", "prismos_test", "-d", "prismos_test", "-c", "CREATE DATABASE prismos_before_restore"])
            command(["docker", "exec", "-i", owned, "pg_restore", "-U", "prismos_test", "-d", "prismos_before_restore", "--exit-on-error"], data=backup_path.read_bytes())
            before_url = make_url(value).set(database="prismos_before_restore").render_as_string(hide_password=False)
            before_config = config_file(directory, before_url, "before-restore.yaml")
            before_env = {**env, "PRISMOS_CONFIG_PATH": str(before_config)}
            before_cli = [sys.executable, "-m", "scripts.migrate_ticket_secret_refs", "--tenant", TENANT, "--config", str(before_config)]
            preview = json.loads(command(before_cli, env=before_env).stdout)
            assert preview["status"] == "succeeded" and preview["eligible"] == 2 and preview["migrated"] == 0
            reapplied = json.loads(command(before_cli + ["--apply"], env=before_env).stdout)
            assert reapplied["status"] == "succeeded" and reapplied["migrated"] == 2
            asyncio.run(verify_database(before_url))
            report["pre_migration_backup_restore_remigrate"] = True
            report["status"] = "passed"
    except Exception as error:
        report.update(status="failed", phase=phase, error_type=type(error).__name__)
    finally:
        if owned:
            result = subprocess.run(["docker", "rm", "--force", owned], capture_output=True, timeout=30)
            report["owned_container_removed"] = result.returncode == 0
        if owned_volume:
            result = subprocess.run(["docker", "volume", "rm", owned_volume], capture_output=True, timeout=30)
            report["owned_volume_removed"] = result.returncode == 0
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0 if report.get("status") == "passed" and report.get("owned_container_removed") and report.get("owned_volume_removed") else 1


if __name__ == "__main__":
    raise SystemExit(main())
