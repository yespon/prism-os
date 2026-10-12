"""Real installer/HTTP/database failure boundaries, not fake installation success."""

import asyncio
import io
import os
import shutil
import threading
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
from deerflow.skills import installer


def archive_bytes():
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr("demo-skill/SKILL.md", "---\nname: demo-skill\ndescription: Recovery fixture\n---\n# Demo\n")
        archive.writestr("demo-skill/payload.txt", "complete contents")
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
def scoped_client(tmp_path, monkeypatch):
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
