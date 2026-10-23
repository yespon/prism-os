"""Real installer/HTTP/database failure boundaries, not fake installation success."""

import asyncio
import io
import json
import os
import shutil
import threading
import uuid
import zipfile
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from app.gateway.routers import agent_catalog, skills
from app.integrations import skill_imports
from deerflow.database import user_config_service
from deerflow.database.models import TenantSkill
from deerflow.skills import install_receipts, installer


def archive_bytes(name="demo-skill"):
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr(f"{name}/SKILL.md", f"---\nname: {name}\ndescription: Recovery fixture\n---\n# Demo\n")
        archive.writestr(f"{name}/payload.txt", "complete contents")
    return output.getvalue()


def archive_file(tmp_path):
    path = tmp_path / "source.zip"
    path.write_bytes(archive_bytes())
    return path


def test_partial_copy_never_leaves_visible_final_directory(tmp_path, monkeypatch):
    path = archive_file(tmp_path)
    root = tmp_path / "skills"

    def partial(source, target, **kwargs):
        target.mkdir(parents=True, exist_ok=True)
        (target / "SKILL.md").write_bytes((source / "SKILL.md").read_bytes())
        raise OSError("injected copy failure")

    monkeypatch.setattr(shutil, "copytree", partial)
    with pytest.raises(OSError, match="injected copy failure"):
        installer.install_skill_from_archive(path, skills_root=root, target_relative_path="tenant-a/user-a")
    assert not (root / "custom/tenant-a/user-a/demo-skill").exists()


def test_concurrent_same_name_reports_conflict_without_partial_content(tmp_path, monkeypatch):
    path = archive_file(tmp_path)
    root = tmp_path / "skills"
    barrier = threading.Barrier(2)
    original = shutil.copytree

    def concurrent(source, target, **kwargs):
        barrier.wait(timeout=5)
        return original(source, target, **kwargs)

    monkeypatch.setattr(shutil, "copytree", concurrent)

    def install():
        try:
            installer.install_skill_from_archive(path, skills_root=root, target_relative_path="tenant-a/user-a")
            return "success"
        except Exception as error:
            return type(error).__name__

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: install(), range(2)))
    assert sorted(results) == ["SkillAlreadyExistsError", "success"]
    assert (root / "custom/tenant-a/user-a/demo-skill/payload.txt").read_text() == "complete contents"


def test_response_failure_after_commit_preserves_registered_files(scoped_client, monkeypatch):
    http, factory, root = scoped_client

    def fail_response(**kwargs):
        raise RuntimeError("injected response failure")

    monkeypatch.setattr(skills, "_build_skill_response", fail_response)
    response = http.post("/api/skills/personal/import", files={"archive": ("source.zip", archive_bytes())})
    assert response.status_code in {409, 500}

    async def rows():
        async with factory() as session:
            result = await session.exec(select(TenantSkill).where(TenantSkill.name == "demo-skill"))
            return result.scalars().all()

    assert len(asyncio.run(rows())) == 1
    assert (root / "custom/tenant-a/user-a/demo-skill/payload.txt").read_text() == "complete contents"


@pytest.fixture
def scoped_client(tmp_path, monkeypatch, native_identity):
    native_identity("user-a")
    root = tmp_path / "skills"
    root.mkdir()
    url = os.environ.get("PRISMOS_SKILL_TEST_DB_URL", "sqlite+aiosqlite://")
    parsed = make_url(url)
    if parsed.get_backend_name() == "postgresql":
        assert parsed.host == "127.0.0.1" and parsed.database == "prismos_skill_probe", "Only the isolated probe database is supported"
    engine = create_async_engine(url, **({"poolclass": NullPool} if parsed.get_backend_name() == "postgresql" else {}))
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def setup():
        async with engine.begin() as connection:
            await connection.run_sync(SQLModel.metadata.drop_all)
            await connection.run_sync(SQLModel.metadata.create_all)
            # WAL keeps readers unblocked while a writer commits: the terminal
            # PTY tests write the unknown audit from one connection while the
            # test asserts from another, and the default rollback journal
            # intermittently deadlocks them on slow CI runners.
            if parsed.get_backend_name() == "sqlite":
                from sqlalchemy import text as _text

                await connection.execute(_text("PRAGMA journal_mode=WAL"))
                await connection.execute(_text("PRAGMA busy_timeout=10000"))

    asyncio.run(setup())
    monkeypatch.setattr(user_config_service, "get_session_factory", lambda: factory)
    monkeypatch.setattr(skills, "get_skills_root_path", lambda: root)
    monkeypatch.setattr(skill_imports, "get_skills_root_path", lambda: root)
    app = FastAPI()

    @app.middleware("http")
    async def identity(request: Request, call_next):
        request.state.user_id = request.headers.get("x-user-id", "user-a")
        request.state.tenant_id = request.headers.get("x-tenant-id", "tenant-a")
        request.state.tenant_role = request.headers.get("x-tenant-role", "tenant_member")
        request.state.user_role = request.headers.get("x-user-role", "user")
        from resource_test_identity import persist_fixture_identity

        await persist_fixture_identity(request, factory)
        return await call_next(request)

    app.include_router(skills.router)
    app.include_router(agent_catalog.router)
    with TestClient(app) as http:
        yield http, factory, root
    asyncio.run(engine.dispose())


def test_late_empty_directory_is_never_replaced(tmp_path):
    with installer.prepare_skill_installation_from_archive(archive_file(tmp_path), skills_root=tmp_path / "skills") as prepared:
        prepared.target.mkdir()
        before = prepared.target.stat().st_ino
        with pytest.raises(FileExistsError):
            prepared.publish()
        assert prepared.target.stat().st_ino == before
        assert not list(prepared.target.iterdir())
    assert prepared.target.is_dir() and not prepared.stage.exists()


@pytest.mark.parametrize("change", ["content", "replacement"])
def test_changed_stage_is_not_published_or_deleted_as_foreign(tmp_path, change):
    with installer.prepare_skill_installation_from_archive(archive_file(tmp_path), skills_root=tmp_path / "skills") as prepared:
        if change == "replacement":
            moved = prepared.stage.with_name("old-stage")
            prepared.stage.rename(moved)
            shutil.copytree(moved, prepared.stage)
        else:
            (prepared.stage / "payload.txt").write_text("changed")
        with pytest.raises(ValueError, match="ownership or contents"):
            prepared.publish()
        assert not prepared.target.exists()
    if change == "replacement":
        assert prepared.stage.exists() and (prepared.stage / "payload.txt").read_text() == "complete contents"


def test_scope_symlink_never_writes_outside_root(tmp_path):
    root = tmp_path / "skills"
    (root / "custom").mkdir(parents=True)
    outside = tmp_path / "external"
    outside.mkdir()
    (root / "custom/tenant-a").symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError, match="alias"):
        installer.install_skill_from_archive(archive_file(tmp_path), skills_root=root, target_relative_path="tenant-a/user-a")
    assert not list(outside.iterdir())


def test_silently_incomplete_copy_is_rejected(tmp_path, monkeypatch):
    original = shutil.copytree

    def incomplete(source, target, **kwargs):
        original(source, target, **kwargs)
        (target / "payload.txt").unlink()

    monkeypatch.setattr(shutil, "copytree", incomplete)
    root = tmp_path / "skills"
    with pytest.raises(ValueError, match="differ"):
        installer.install_skill_from_archive(archive_file(tmp_path), skills_root=root)
    assert not (root / "custom/demo-skill").exists()


async def all_rows(factory):
    async with factory() as session:
        result = await session.exec(select(TenantSkill).where(TenantSkill.name == "demo-skill"))
        return result.scalars().all()


def test_registration_failure_can_be_reconciled_without_upload_or_duplicate(scoped_client, monkeypatch):
    http, factory, root = scoped_client
    with monkeypatch.context() as patch:

        async def fail(*args, **kwargs):
            raise RuntimeError("injected registration failure")

        patch.setattr(user_config_service, "create_tenant_personal_skill", fail)
        response = http.post("/api/skills/personal/import", files={"archive": ("source.zip", archive_bytes())})
    assert response.status_code == 409
    operation = response.json()["detail"]["operation_id"]
    url = f"/api/skills/personal/imports/{operation}"
    status = http.get(url).json()
    assert status["state"] == "registration_pending" and status["files_verified"] and not status["registered"]
    assert status["phase"] == "registration_unknown"
    assert len(asyncio.run(all_rows(factory))) == 0
    assert http.get(url, headers={"x-user-id": "user-b"}).status_code == 404
    assert http.get(url, headers={"x-tenant-id": "tenant-b"}).status_code == 404
    assert http.get("/api/skills/personal/imports").json()["operations"][0]["operation_id"] == operation
    assert http.post(url + "/recover").json()["registered"]
    assert http.post(url + "/recover").json()["registered"]
    assert len(asyncio.run(all_rows(factory))) == 1
    assert (root / "custom/tenant-a/user-a/demo-skill/payload.txt").read_text() == "complete contents"


def test_timeout_after_real_commit_is_observed_without_second_registration(scoped_client, monkeypatch):
    http, factory, _ = scoped_client
    original = user_config_service.create_tenant_personal_skill
    calls = []
    with monkeypatch.context() as patch:

        async def committed(*args, **kwargs):
            calls.append("committed")
            await original(*args, **kwargs)
            raise TimeoutError("injected post-commit timeout")

        patch.setattr(user_config_service, "create_tenant_personal_skill", committed)
        response = http.post("/api/skills/personal/import", files={"archive": ("source.zip", archive_bytes())})
    assert response.status_code == 500
    operation = response.json()["detail"]["operation_id"]
    url = f"/api/skills/personal/imports/{operation}"
    assert http.get(url).json()["registered"]
    assert http.post(url + "/recover").json()["registered"]
    assert calls == ["committed"] and len(asyncio.run(all_rows(factory))) == 1


def test_changed_published_content_blocks_recovery_and_preserves_data(scoped_client, monkeypatch):
    http, _, root = scoped_client
    with monkeypatch.context() as patch:

        async def fail(*args, **kwargs):
            raise RuntimeError("registration unavailable")

        patch.setattr(user_config_service, "create_tenant_personal_skill", fail)
        response = http.post("/api/skills/personal/import", files={"archive": ("source.zip", archive_bytes())})
    operation = response.json()["detail"]["operation_id"]
    file = root / "custom/tenant-a/user-a/demo-skill/payload.txt"
    file.write_text("user changed this")
    assert http.post(f"/api/skills/personal/imports/{operation}/recover").status_code == 409
    assert file.read_text() == "user changed this"


def test_existing_registration_with_missing_files_does_not_get_overwritten(scoped_client):
    http, factory, root = scoped_client

    async def existing():
        async with factory() as session:
            session.add(TenantSkill(tenant_id="tenant-a", user_id="user-a", name="demo-skill", install_dir=str(root / "custom/tenant-a/user-a/demo-skill"), enabled=False))
            await session.commit()

    asyncio.run(existing())
    response = http.post("/api/skills/personal/import", files={"archive": ("source.zip", archive_bytes())})
    assert response.status_code == 409 and "already registered" in response.text
    assert not (root / "custom/tenant-a/user-a/demo-skill").exists()
    assert not asyncio.run(all_rows(factory))[0].enabled


def test_observed_registration_does_not_enable_disabled_skill(scoped_client):
    http, factory, _ = scoped_client
    assert http.post("/api/skills/personal/import", files={"archive": ("source.zip", archive_bytes())}).status_code == 201
    operation = http.get("/api/skills/personal/imports").json()["operations"][0]["operation_id"]

    async def disable():
        async with factory() as session:
            result = await session.exec(select(TenantSkill).where(TenantSkill.name == "demo-skill"))
            row = result.scalars().one()
            row.enabled = False
            session.add(row)
            await session.commit()

    asyncio.run(disable())
    body = http.post(f"/api/skills/personal/imports/{operation}/recover").json()
    assert body["registered"] and not body["enabled"] and not body["execution_ready"]
    assert body["phase"] == "registration_observed"


def test_tenant_admin_import_and_recovery_do_not_grant_member_write(scoped_client):
    http, factory, root = scoped_client
    admin = {"x-tenant-role": "tenant_admin"}
    assert http.post("/api/tenants/skills/import", files={"archive": ("source.zip", archive_bytes())}).status_code == 403
    assert http.post("/api/tenants/skills/import", headers=admin, files={"archive": ("source.zip", archive_bytes())}).status_code == 201
    operation = http.get("/api/tenants/skills/imports", headers=admin).json()["operations"][0]["operation_id"]
    url = f"/api/tenants/skills/imports/{operation}"
    assert http.get(url).status_code == 403 and http.post(url + "/recover").status_code == 403
    assert http.post(url + "/recover", headers=admin).json()["registered"]
    assert http.get(url, headers={**admin, "x-tenant-id": "tenant-b"}).status_code == 404
    row = asyncio.run(all_rows(factory))[0]
    assert row.user_id == "__tenant_shared_skill__:tenant-a"
    assert (root / "custom/tenant-a/demo-skill/payload.txt").is_file()


def test_process_exit_after_rename_recovers_from_prepared_receipt(scoped_client, tmp_path):
    import subprocess
    import sys

    http, factory, root = scoped_client
    source = archive_file(tmp_path)
    code = """
import os,sys
from pathlib import Path
from deerflow.skills import install_receipts, installer
original=install_receipts.write_receipt
def crash(parent, record, **kwargs):
    if record['state']=='published': os._exit(83)
    return original(parent,record,**kwargs)
install_receipts.write_receipt=crash
installer.install_skill_from_archive(Path(sys.argv[1]),skills_root=Path(sys.argv[2]),target_relative_path='tenant-a/user-a')
"""
    child = subprocess.run([sys.executable, "-c", code, str(source), str(root)], timeout=30, capture_output=True)
    assert child.returncode == 83, child.stderr.decode()
    operation = http.get("/api/skills/personal/imports").json()["operations"][0]
    assert operation["state"] == "registration_pending" and operation["files_verified"]
    assert len(asyncio.run(all_rows(factory))) == 0
    assert http.post(f"/api/skills/personal/imports/{operation['operation_id']}/recover").json()["registered"]
    assert len(asyncio.run(all_rows(factory))) == 1


def test_thread_archive_install_uses_scoped_registration_and_recovery(scoped_client, tmp_path, monkeypatch):
    http, factory, root = scoped_client
    source = archive_file(tmp_path)
    observed = []

    def resolve(user_id, thread, path, **kwargs):
        observed.append((user_id, thread, kwargs["tenant_id"]))
        return source

    monkeypatch.setattr(skills, "resolve_thread_virtual_path", resolve)
    response = http.post("/api/skills/install", headers={"x-tenant-role": "tenant_admin"}, json={"thread_id": "thread-a", "path": "outputs/source.zip"})
    assert response.status_code == 200
    assert observed == [("user-a", "thread-a", "tenant-a")]
    operation = response.json()["operation_id"]
    assert http.get(f"/api/tenants/skills/imports/{operation}", headers={"x-tenant-role": "tenant_admin"}).json()["registered"]
    assert len(asyncio.run(all_rows(factory))) == 1
    assert (root / "custom/tenant-a/demo-skill/payload.txt").is_file()


def test_native_database_unique_key_is_enforced(scoped_client):
    from sqlalchemy.exc import IntegrityError

    _, factory, _ = scoped_client

    async def duplicate():
        async with factory() as session:
            session.add(TenantSkill(tenant_id="tenant-a", user_id="user-a", name="demo-skill"))
            await session.commit()
        async with factory() as session:
            session.add(TenantSkill(tenant_id="tenant-a", user_id="user-a", name="demo-skill"))
            with pytest.raises(IntegrityError):
                await session.commit()
            await session.rollback()

    asyncio.run(duplicate())
    assert len(asyncio.run(all_rows(factory))) == 1


def test_registration_collision_preserves_foreign_row_and_published_files(scoped_client, monkeypatch):
    http, factory, root = scoped_client
    foreign = root / "custom/tenant-b/user-z/demo-skill"
    with monkeypatch.context() as patch:

        async def conflicting(tenant_id, user_id, **kwargs):
            async with factory() as session:
                session.add(TenantSkill(tenant_id=tenant_id, user_id=user_id, name="demo-skill", install_dir=str(foreign)))
                await session.commit()
            raise RuntimeError("another registration won")

        patch.setattr(user_config_service, "create_tenant_personal_skill", conflicting)
        response = http.post("/api/skills/personal/import", files={"archive": ("source.zip", archive_bytes())})
    operation = response.json()["detail"]["operation_id"]
    assert http.get(f"/api/skills/personal/imports/{operation}").json()["state"] == "registration_conflict"
    assert http.post(f"/api/skills/personal/imports/{operation}/recover").status_code == 409
    assert asyncio.run(all_rows(factory))[0].install_dir == str(foreign)
    assert (root / "custom/tenant-a/user-a/demo-skill/payload.txt").read_text() == "complete contents"


def test_partial_copy_is_not_visible_until_exclusive_publication(tmp_path, monkeypatch):
    root = tmp_path / "skills"
    started = threading.Event()
    release = threading.Event()
    original = shutil.copytree

    def slow(source, target, **kwargs):
        target.mkdir(exist_ok=True)
        (target / "SKILL.md").write_bytes((source / "SKILL.md").read_bytes())
        started.set()
        assert release.wait(timeout=5)
        return original(source, target, **kwargs)

    monkeypatch.setattr(shutil, "copytree", slow)
    source = archive_file(tmp_path)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(installer.install_skill_from_archive, source, skills_root=root)
        try:
            assert started.wait(timeout=5)
            assert not (root / "custom/demo-skill").exists()
        finally:
            release.set()
        assert future.result()["success"]
    assert (root / "custom/demo-skill/payload.txt").read_text() == "complete contents"


def test_publication_fsync_failure_after_rename_keeps_recoverable_files(scoped_client, monkeypatch):
    from deerflow.skills import install_receipts

    http, _, root = scoped_client
    original = install_receipts.publish_no_replace
    with monkeypatch.context() as patch:

        def uncertain(source, target):
            original(source, target)
            if not target.name.startswith("."):
                raise OSError("injected sync result uncertainty after rename")

        patch.setattr(install_receipts, "publish_no_replace", uncertain)
        response = http.post("/api/skills/personal/import", files={"archive": ("source.zip", archive_bytes())})
    assert response.status_code == 500
    operation = response.json()["detail"]["operation_id"]
    assert (root / "custom/tenant-a/user-a/demo-skill/payload.txt").is_file()
    assert http.post(f"/api/skills/personal/imports/{operation}/recover").json()["registered"]


@pytest.mark.parametrize("template_id", ["expert:cvm-cluster-doctor", "expert:office-automation", "expert:tencentcloud-api"])
def test_fixed_source_install_uses_reviewed_adapter_and_current_owner(scoped_client, template_id):
    from app.integrations.octop.resources import resource_preflight

    http, _, root = scoped_client
    declaration = resource_preflight(template_id)
    resource = next(r for r in declaration["resources"] if r["host_format"]["status"] == "needs_adapter")
    url = f"/api/agent-catalog/templates/{template_id}/resources/{resource['id']}/install"
    response = http.post(url, json={"scope": "personal", "bundle_sha256": resource["bundle_sha256"]})
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["registered"] and not body["execution_ready"] and not body["permission_grants"]
    assert (root / "custom/tenant-a/user-a" / body["name"] / "LICENSE.octop").is_file()
    assert (root / "custom/tenant-a/user-a" / body["name"] / "PRISMOS_ORIGIN.json").is_file()
    assert http.post(url, json={"bundle_sha256": resource["bundle_sha256"]}).status_code == 409
    assert http.get(f"/api/skills/personal/imports/{body['operation_id']}", headers={"x-user-id": "user-b"}).status_code == 404


def test_source_install_requires_current_digest_rejects_target_injection_and_checks_shared_admin(scoped_client):
    from app.integrations.octop.resources import resource_preflight

    http, _, root = scoped_client
    declaration = resource_preflight("expert:ai-coding-coach")
    resource = next(r for r in declaration["resources"] if r["kind"] == "skill_bundle")
    url = f"/api/agent-catalog/templates/{declaration['template_id']}/resources/{resource['id']}/install"
    body = {"bundle_sha256": resource["bundle_sha256"]}
    assert http.post(url, json={"bundle_sha256": "0" * 64}).status_code == 409
    assert http.post(url, json={**body, "install_dir": "/another-tenant"}).status_code == 422
    assert http.post(url, json={**body, "user_id": "user-b"}).status_code == 422
    assert http.post(url, json={**body, "scope": "tenant"}).status_code == 403
    assert not (root / "custom").exists()
    response = http.post(url, headers={"x-tenant-role": "tenant_admin"}, json={**body, "scope": "tenant"})
    assert response.status_code == 201 and response.json()["scope"] == "tenant"
    assert (root / "custom/tenant-a" / response.json()["name"] / "SKILL.md").is_file()


def crash_before_publication(source, root):
    import subprocess
    import sys

    code = """
import os,sys
from pathlib import Path
from deerflow.skills import install_receipts,installer
original=install_receipts.publish_no_replace
def crash(source,target):
    if source.name.startswith('.prismos-stage-'): os._exit(84)
    return original(source,target)
install_receipts.publish_no_replace=crash
installer.install_skill_from_archive(Path(sys.argv[1]),skills_root=Path(sys.argv[2]),target_relative_path='tenant-a/user-a')
"""
    child = subprocess.run([sys.executable, "-c", code, str(source), str(root)], timeout=30, capture_output=True)
    assert child.returncode == 84, child.stderr.decode()


def test_process_exit_before_publication_recovers_prepared_stage(scoped_client, tmp_path):
    http, factory, root = scoped_client
    crash_before_publication(archive_file(tmp_path), root)
    operation = http.get("/api/skills/personal/imports").json()["operations"][0]
    assert operation["state"] == "publication_pending" and operation["staged_files_verified"]
    assert not (root / "custom/tenant-a/user-a/demo-skill").exists()
    assert http.post(f"/api/skills/personal/imports/{operation['operation_id']}/recover").json()["registered"]
    assert len(asyncio.run(all_rows(factory))) == 1


def test_abort_only_removes_owned_stage_and_never_published_content(scoped_client, tmp_path):
    http, _, root = scoped_client
    crash_before_publication(archive_file(tmp_path), root)
    operation = http.get("/api/skills/personal/imports").json()["operations"][0]["operation_id"]
    url = f"/api/skills/personal/imports/{operation}"
    assert http.post(url + "/abort", headers={"x-user-id": "user-b"}).status_code == 404
    assert http.post(url + "/abort").json()["state"] == "aborted"
    assert http.post(url + "/abort").json()["state"] == "aborted"
    assert not list((root / "custom/tenant-a/user-a").glob(".prismos-stage-*"))
    assert http.post("/api/skills/personal/import", files={"archive": ("source.zip", archive_bytes())}).status_code == 201
    operations = http.get("/api/skills/personal/imports").json()["operations"]
    published = next(item for item in operations if item["registered"])
    assert http.post(f"/api/skills/personal/imports/{published['operation_id']}/abort").status_code == 409
    assert (root / "custom/tenant-a/user-a/demo-skill/payload.txt").is_file()


def test_replaced_stage_cannot_be_aborted_or_published(scoped_client, tmp_path):
    http, _, root = scoped_client
    crash_before_publication(archive_file(tmp_path), root)
    operation = http.get("/api/skills/personal/imports").json()["operations"][0]["operation_id"]
    stage = root / "custom/tenant-a/user-a" / (".prismos-stage-" + operation)
    old = stage.with_name("old-owned-stage")
    stage.rename(old)
    shutil.copytree(old, stage)
    url = f"/api/skills/personal/imports/{operation}"
    assert http.post(url + "/abort").status_code == 409
    assert http.post(url + "/recover").status_code == 409
    assert (stage / "payload.txt").read_text() == "complete contents"


def install_pending(root, tmp_path, monkeypatch, number):
    name = f"pending-{number}"
    source = tmp_path / f"{name}.zip"
    source.write_bytes(archive_bytes(name))
    with monkeypatch.context() as patch:
        patch.setattr(install_receipts.uuid, "uuid4", lambda: uuid.UUID(int=number))
        result = installer.install_skill_from_archive(source, skills_root=root, target_relative_path="tenant-a/user-a")
    return result["operation_id"]


def pages(http, *, cursor=None, page_size=17, headers=None):
    seen = []
    while True:
        params = {"page_size": page_size}
        if cursor:
            params["cursor"] = cursor
        response = http.get("/api/skills/personal/imports", params=params, headers=headers)
        assert response.status_code == 200, response.text
        body = response.json()
        seen.extend(body["operations"])
        cursor = body["next_cursor"]
        if cursor is None:
            return seen


def test_pagination_reaches_an_old_pending_import_beyond_one_hundred(scoped_client, tmp_path, monkeypatch):
    http, factory, root = scoped_client
    oldest = install_pending(root, tmp_path, monkeypatch, 1)
    for number in range(2, 127):
        with monkeypatch.context() as patch:
            patch.setattr(install_receipts.uuid, "uuid4", lambda: uuid.UUID(int=number))
            response = http.post("/api/skills/personal/import", files={"archive": ("source.zip", archive_bytes(f"registered-{number}"))})
            assert response.status_code == 201, response.text
    parent = root / "custom/tenant-a/user-a"
    receipt = install_receipts.receipt_path(parent, oldest)
    os.utime(receipt, (1, 1))
    before = {p.name: p.read_bytes() for p in parent.glob(".prismos-import-*.json")}
    first = http.get("/api/skills/personal/imports").json()
    assert len(first["operations"]) == 100 and first["total"] == 126 and first["next_cursor"]
    assert first["retention"] == {"mode": "retain_all", "automatic_deletion": False, "maintenance": "owned_stage_abort_only"}
    entries = pages(http)
    ids = [item["operation_id"] for item in entries]
    assert len(ids) == len(set(ids)) == 126 and ids[-1] == oldest
    assert entries[-1]["state"] == "registration_pending"
    assert before == {p.name: p.read_bytes() for p in parent.glob(".prismos-import-*.json")}
    assert http.post(f"/api/skills/personal/imports/{oldest}/recover").json()["registered"]
    async def imported_rows():
        async with factory() as session:
            result = await session.exec(select(TenantSkill))
            return result.scalars().all()

    assert len(asyncio.run(imported_rows())) == 126


def test_live_cursor_is_stable_through_recovery_and_concurrent_new_imports(scoped_client, tmp_path, monkeypatch):
    http, _, root = scoped_client
    original = {install_pending(root, tmp_path, monkeypatch, number) for number in [100, 200, 300, 400]}
    first = http.get("/api/skills/personal/imports", params={"page_size": 2}).json()
    visited = [item["operation_id"] for item in first["operations"]]
    assert http.post(f"/api/skills/personal/imports/{visited[0]}/recover").json()["registered"]
    inserted = {install_pending(root, tmp_path, monkeypatch, number) for number in [150, 350, 500]}
    rest = pages(http, cursor=first["next_cursor"], page_size=2)
    all_visited = visited + [item["operation_id"] for item in rest]
    assert len(all_visited) == len(set(all_visited)) and original <= set(all_visited)
    refreshed = pages(http, page_size=2)
    assert {item["operation_id"] for item in refreshed} == original | inserted
    assert next(item for item in refreshed if item["operation_id"] == visited[0])["registered"]


def test_import_cursor_cannot_cross_user_tenant_scope_or_page_size(scoped_client, tmp_path, monkeypatch):
    http, _, root = scoped_client
    for number in [1, 2]:
        install_pending(root, tmp_path, monkeypatch, number)
    cursor = http.get("/api/skills/personal/imports", params={"page_size": 1}).json()["next_cursor"]
    for headers in [{"x-user-id": "user-b"}, {"x-tenant-id": "tenant-b"}]:
        assert http.get("/api/skills/personal/imports", params={"cursor": cursor, "page_size": 1}, headers=headers).status_code == 400
    assert http.get("/api/skills/personal/imports", params={"cursor": cursor, "page_size": 2}).status_code == 400
    assert http.get("/api/tenants/skills/imports", params={"cursor": cursor, "page_size": 1}).status_code == 403
    assert http.get("/api/tenants/skills/imports", params={"cursor": cursor, "page_size": 1}, headers={"x-tenant-role": "tenant_admin"}).status_code == 400
    assert http.get("/api/skills/personal/imports", params={"cursor": cursor}, headers={"x-user-id": ""}).status_code == 401


@pytest.mark.parametrize("cursor", ["", "broken", "a" * 513, "e30"])
def test_invalid_import_cursor_is_rejected_without_creating_storage(scoped_client, cursor):
    http, _, root = scoped_client
    response = http.get("/api/skills/personal/imports", params={"cursor": cursor})
    assert response.status_code in {400, 422}
    assert not (root / "custom").exists()


@pytest.mark.parametrize("payload", [None, [], "private text", {}, {"skill_name": []}, {"state": []}, {"state": "invented"}])
def test_bad_receipt_is_isolated_and_does_not_hide_a_recoverable_import(scoped_client, tmp_path, monkeypatch, payload):
    http, _, root = scoped_client
    operation = install_pending(root, tmp_path, monkeypatch, 1)
    bad = root / "custom/tenant-a/user-a" / (".prismos-import-" + "f" * 32 + ".json")
    bad.write_text(json.dumps(payload))
    original = bad.read_bytes()
    first = http.get("/api/skills/personal/imports", params={"page_size": 1}).json()
    item = first["operations"][0]
    assert item["state"] == "receipt_unavailable" and item["name"] == "" and not item["registered"]
    next_page = pages(http, cursor=first["next_cursor"], page_size=1)
    assert next_page[0]["operation_id"] == operation and next_page[0]["files_verified"]
    assert http.post(f"/api/skills/personal/imports/{operation}/recover").json()["registered"]
    assert bad.read_bytes() == original


def test_alias_and_invalid_receipt_names_are_preserved_without_reading_targets(scoped_client, tmp_path, monkeypatch):
    http, _, root = scoped_client
    operation = install_pending(root, tmp_path, monkeypatch, 1)
    parent = root / "custom/tenant-a/user-a"
    outside = tmp_path / "private.json"
    outside.write_text('{"secret":"private target"}')
    alias = parent / (".prismos-import-" + "f" * 32 + ".json")
    alias.symlink_to(outside)
    ignored = parent / ".prismos-import-private-label.json"
    ignored.write_text("private name")
    original_read = type(outside).read_text

    def guarded(path, *args, **kwargs):
        if path in {alias, ignored, outside}:
            raise AssertionError("An untrusted receipt target was read")
        return original_read(path, *args, **kwargs)

    monkeypatch.setattr(type(outside), "read_text", guarded)
    response = http.get("/api/skills/personal/imports")
    assert response.status_code == 200 and response.json()["ignored_entries"] == 1
    assert "private target" not in response.text and "private-label" not in response.text
    assert next(item for item in response.json()["operations"] if item["operation_id"] == operation)["files_verified"]
    assert alias.is_symlink() and ignored.exists() and outside.exists()


def test_database_failure_does_not_masquerade_as_a_damaged_receipt(scoped_client, tmp_path, monkeypatch):
    http, _, root = scoped_client
    operation = install_pending(root, tmp_path, monkeypatch, 1)

    async def unavailable(*args, **kwargs):
        raise RuntimeError("injected database inspection outage")

    monkeypatch.setattr(skill_imports, "current_row", unavailable)
    response = http.get("/api/skills/personal/imports")
    assert response.status_code == 503 and "operations" not in response.json()
    assert (root / "custom/tenant-a/user-a" / (".prismos-import-" + operation + ".json")).is_file()


def test_registered_disabled_aborted_and_ancient_receipts_are_retained(scoped_client, tmp_path):
    http, factory, root = scoped_client
    assert http.post("/api/skills/personal/import", files={"archive": ("source.zip", archive_bytes())}).status_code == 201
    assert http.post("/api/skills/personal/import", files={"archive": ("source.zip", archive_bytes())}).status_code == 409

    async def disable():
        async with factory() as session:
            result = await session.exec(select(TenantSkill))
            row = result.scalars().one()
            row.enabled = False
            session.add(row)
            await session.commit()

    asyncio.run(disable())
    parent = root / "custom/tenant-a/user-a"
    before = {p.name: p.read_bytes() for p in parent.glob(".prismos-import-*.json")}
    for path in parent.glob(".prismos-import-*.json"):
        os.utime(path, (1, 1))
    entries = pages(http, page_size=1)
    assert len(entries) == 2 and {item["state"] for item in entries} == {"registered", "aborted"}
    assert next(item for item in entries if item["registered"])["enabled"] is False
    assert before == {p.name: p.read_bytes() for p in parent.glob(".prismos-import-*.json")}
    assert (parent / "demo-skill/payload.txt").read_text() == "complete contents"


def test_shared_pagination_requires_current_admin_and_binds_cursor_to_actor(scoped_client):
    http, _, root = scoped_client
    admin = {"x-tenant-role": "tenant_admin"}
    for name in ["shared-one", "shared-two"]:
        assert http.post("/api/tenants/skills/import", files={"archive": ("source.zip", archive_bytes(name))}, headers=admin).status_code == 201
    first = http.get("/api/tenants/skills/imports", params={"page_size": 1}, headers=admin).json()
    assert first["operations"][0]["scope"] == "tenant" and first["next_cursor"]
    params = {"page_size": 1, "cursor": first["next_cursor"]}
    second = http.get("/api/tenants/skills/imports", params=params, headers=admin).json()
    assert second["next_cursor"] is None and second["operations"][0]["operation_id"] != first["operations"][0]["operation_id"]
    assert http.get("/api/tenants/skills/imports", params=params).status_code == 403
    assert http.get("/api/tenants/skills/imports", params=params, headers={**admin, "x-user-id": "user-b"}).status_code == 400
    assert http.get("/api/tenants/skills/imports", params=params, headers={**admin, "x-tenant-id": "tenant-b"}).status_code == 400
    assert len(http.get("/api/tenants/skills/imports", headers={**admin, "x-user-id": "user-b"}).json()["operations"]) == 2
    assert not (root / "custom/tenant-a/user-b").exists()


def test_receipt_corrupted_between_listing_checks_is_isolated(scoped_client, tmp_path, monkeypatch):
    http, _, root = scoped_client
    operation = install_pending(root, tmp_path, monkeypatch, 1)
    other = install_pending(root, tmp_path, monkeypatch, 2)
    read = skill_imports.read_receipt
    calls = 0

    def racing_read(skills_root, scope, identifier):
        nonlocal calls
        if identifier == operation:
            calls += 1
            if calls == 2:
                install_receipts.receipt_path(root / "custom/tenant-a/user-a", operation).write_text("[]")
        return read(skills_root, scope, identifier)

    monkeypatch.setattr(skill_imports, "read_receipt", racing_read)
    response = http.get("/api/skills/personal/imports")
    assert response.status_code == 200
    entries = {item["operation_id"]: item for item in response.json()["operations"]}
    assert entries[operation]["state"] == "receipt_unavailable"
    assert entries[other]["files_verified"]
