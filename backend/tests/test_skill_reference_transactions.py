"""Real two-connection Agent CRUD/Skill withdrawal ordering on SQLite/PostgreSQL."""

import asyncio
import os
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest
from test_skill_import_recovery import scoped_client as recovery_client
from test_skill_resource_identity import source_tree

from app.gateway.routers import agents
from app.integrations import skill_deletions
from deerflow.database.session import get_session

scoped_client = recovery_client
ADMIN = {"x-tenant-role": "tenant_admin"}


@pytest.fixture(autouse=True)
def durable_sqlite(tmp_path, monkeypatch):
    # Shared in-memory SQLite connections cannot represent a competing writer.
    # Preserve the owned loopback PostgreSQL URL when invoked by the PG probe.
    if not os.environ.get("PRISMOS_SKILL_TEST_DB_URL"):
        monkeypatch.setenv("PRISMOS_SKILL_TEST_DB_URL", "sqlite+aiosqlite:///" + str(tmp_path / "reference.db"))


def prepare(scoped_client, monkeypatch):
    http, factory, root = source_tree(scoped_client, monkeypatch)

    async def session():
        async with factory() as value:
            yield value

    http.app.include_router(agents.router)
    http.app.dependency_overrides[get_session] = session
    return http, factory, root


@pytest.mark.parametrize("shared", [False, True])
@pytest.mark.parametrize("action", ["create", "update"])
def test_new_reference_writer_waits_for_withdrawal_transaction(scoped_client, monkeypatch, shared, action):
    http, factory, root = prepare(scoped_client, monkeypatch)
    headers = ADMIN if shared else {}
    if action == "update":
        assert http.post("/api/agents", headers=headers, json={"name": "writer", "system_prompt": "writer", "is_shared": shared}).status_code == 201
    checked = threading.Event()
    release = threading.Event()
    writer_started = threading.Event()
    writer_acquired = threading.Event()
    original_references = skill_deletions._references
    original_lock = agents.begin_reference_transaction

    async def pause_after_check(*args, **kwargs):
        count = await original_references(*args, **kwargs)
        checked.set()
        assert await asyncio.to_thread(release.wait, 5), "Test withdrawal release was not delivered"
        return count

    async def trace_writer(*args, **kwargs):
        writer_started.set()
        if os.environ.get("PRISMOS_REFERENCE_BASELINE_PROBE") != "1":
            await original_lock(*args, **kwargs)
        writer_acquired.set()

    monkeypatch.setattr(skill_deletions, "_references", pause_after_check)
    monkeypatch.setattr(agents, "begin_reference_transaction", trace_writer)
    prefix = "/api/tenants/skills/collision" if shared else "/api/skills/personal/collision"
    # Do not invoke the deliberately paused mutation checker from preflight.
    selected = next(item for item in http.get("/api/skills/available", headers=headers).json()["skills"] if item["scope"] == ("tenant" if shared else "personal"))
    with ThreadPoolExecutor(max_workers=2) as pool:
        deletion = pool.submit(http.delete, prefix, headers=headers, params={"expected_resource_id": selected["resource_id"]})
        try:
            assert checked.wait(5)
            if action == "create":
                writing = pool.submit(http.post, "/api/agents", headers=headers, json={"name": "writer", "system_prompt": "writer", "skills": ["collision"], "is_shared": shared})
            else:
                writing = pool.submit(http.put, "/api/agents/writer", headers=headers, json={"skills": ["collision"]})
            assert writer_started.wait(5)
            completed = threading.Event()
            writing.add_done_callback(lambda _: completed.set())
            assert not completed.wait(0.35), "Agent write committed after reference check but before withdrawal commit"
            assert not writer_acquired.is_set(), "Agent writer entered after reference check but before withdrawal commit"
        finally:
            release.set()
        assert deletion.result(timeout=10).status_code == 204
        assert writing.result(timeout=10).status_code in {200, 201}
        assert writer_acquired.is_set()
    target = root / "custom/tenant-a" / ("" if shared else "user-a") / "collision"
    assert not target.exists()


@pytest.mark.parametrize("shared", [False, True])
def test_committed_agent_reference_wins_before_deletion_and_preserves_files(scoped_client, monkeypatch, shared):
    http, factory, root = prepare(scoped_client, monkeypatch)
    headers = ADMIN if shared else {}
    response = http.post("/api/agents", headers=headers, json={"name": "first-writer", "system_prompt": "writer", "skills": ["collision"], "is_shared": shared})
    assert response.status_code == 201, response.text
    prefix = "/api/tenants/skills/collision" if shared else "/api/skills/personal/collision"
    target = root / "custom/tenant-a" / ("" if shared else "user-a") / "collision/SKILL.md"
    before = target.read_bytes()
    assert http.delete(prefix, headers=headers).status_code == 409
    assert target.read_bytes() == before
    assert http.put("/api/agents/first-writer", headers=headers, json={"skills": []}).status_code == 200
    assert http.delete(prefix, headers=headers).status_code == 204
