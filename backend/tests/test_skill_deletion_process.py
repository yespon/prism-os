"""Hard-killed original deletion transactions, inspected from a fresh process."""

import asyncio
import json
import os
import signal
import subprocess
import sys

import pytest
from test_skill_import_recovery import scoped_client as recovery_client
from test_skill_reference_transactions import durable_sqlite  # noqa: F401
from test_skill_resource_deletion import plan
from test_skill_resource_identity import source_tree

from deerflow.database import user_config_service as service

scoped_client = recovery_client

WORKER = r"""
import asyncio,json,os,signal,sys
from pathlib import Path
from sqlalchemy import event
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker,create_async_engine
from sqlalchemy.pool import NullPool
from sqlmodel.ext.asyncio.session import AsyncSession
from app.integrations import skill_deletions
from deerflow.database import user_config_service as service
from deerflow.database.models import TenantSkill
from deerflow.skills.resource_deletion_files import OwnedRemoval
root=Path(sys.argv[1]); point=sys.argv[2]; shared=sys.argv[3]=='1'; selection=json.loads(sys.argv[4])
url=os.environ['PRISMOS_SKILL_TEST_DB_URL']; parsed=make_url(url)
if parsed.get_backend_name()=='postgresql':
    assert parsed.host=='127.0.0.1' and parsed.database=='prismos_skill_probe'
else:
    assert parsed.get_backend_name()=='sqlite' and Path(parsed.database).parent==root.parent
engine=create_async_engine(url,poolclass=NullPool)
factory=async_sessionmaker(engine,class_=AsyncSession,expire_on_commit=False)
service.get_session_factory=lambda:factory
service.get_skills_root_path=lambda:root

def stop():
    os.kill(os.getpid(),signal.SIGKILL)
original_write=skill_deletions.write_receipt
def receipt(parent,record,**kwargs):
    result=original_write(parent,record,**kwargs)
    if (point=='prepared' and record['state']=='delete_prepared') or (point=='withdrawn' and record['state']=='delete_withdrawn'):
        stop()
    return result
skill_deletions.write_receipt=receipt
original_quarantine=OwnedRemoval.quarantine
def quarantine(self,record):
    result=original_quarantine(self,record)
    if point=='renamed':stop()
    return result
OwnedRemoval.quarantine=quarantine

def before(session):
    if any(isinstance(row,TenantSkill) and row.name=='process-delete' for row in session.deleted):
        session.info['process_delete']=True
        if point=='before_commit':stop()
def after(session):
    if point=='after_commit' and session.info.get('process_delete'):stop()
event.listen(AsyncSession.sync_session_class,'before_commit',before)
event.listen(AsyncSession.sync_session_class,'after_commit',after)
original_unlink=os.unlink
def unlink(name,*args,**kwargs):
    result=original_unlink(name,*args,**kwargs)
    if point=='one_unlink' and name=='SKILL.md':stop()
    return result
os.unlink=unlink
original_reclaim=OwnedRemoval.reclaim
def reclaim(self,record):
    result=original_reclaim(self,record)
    if point=='removed':stop()
    return result
OwnedRemoval.reclaim=reclaim
asyncio.run(skill_deletions.delete_owned(root,'tenant-a','user-a',shared,'process-delete',**selection))
raise AssertionError('Expected hard-stop point was not reached')
"""


def settings(shared):
    if shared:
        return asyncio.run(service.get_tenant_shared_skill_settings("tenant-a"))
    return asyncio.run(service.get_tenant_personal_skill_settings("tenant-a", "user-a"))


def prepare(scoped_client, monkeypatch, shared):
    http, factory, root = source_tree(scoped_client, monkeypatch)
    headers = {"x-tenant-role": "tenant_admin"} if shared else {}
    prefix = "/api/tenants/skills" if shared else "/api/skills/personal"
    created = http.post(prefix, headers=headers, json={"name": "process-delete", "description": "Owned process removal", "instructions": "ORIGINAL PROCESS CONTENT", "bound_tools": ["owned-binding"]})
    assert created.status_code == 201, created.text
    target = root / "custom/tenant-a" / ("" if shared else "user-a") / "process-delete"
    (target / "members").mkdir()
    (target / "members/remaining.txt").write_text("ORIGINAL REMAINING MEMBER")
    protected = {p: p.read_bytes() for p in root.rglob("SKILL.md") if not p.is_relative_to(target)}
    return http, factory, root, headers, prefix, created.json(), target, protected


def hard_stop(root, shared, point, selected):
    result = subprocess.run([sys.executable, "-c", WORKER, str(root), point, "1" if shared else "0", json.dumps(selected)], capture_output=True, timeout=30)
    error = result.stderr.decode(errors="replace")
    url = os.environ["PRISMOS_SKILL_TEST_DB_URL"]
    error = error.replace(url, "[owned-test-db]")
    assert result.returncode == -signal.SIGKILL, error


@pytest.mark.parametrize("shared", [False, True])
@pytest.mark.parametrize("point", ["prepared", "renamed", "before_commit", "after_commit", "withdrawn", "one_unlink", "removed"])
def test_hard_killed_delete_preserves_original_facts_and_explicit_recovery(scoped_client, monkeypatch, shared, point):
    http, factory, root, headers, prefix, created, target, protected = prepare(scoped_client, monkeypatch, shared)
    selected = plan(http, "process-delete", shared)
    hard_stop(root, shared, point, selected)
    listed = http.get(prefix + "/imports", headers=headers)
    assert listed.status_code == 200
    operations = [r for r in listed.json()["operations"] if r.get("kind") == "resource_delete"]
    assert len(operations) == 1
    operation = operations[0]
    url = prefix + "/imports/" + operation["operation_id"]
    observed = http.get(url, headers=headers)
    assert observed.status_code == 200, observed.text
    state = observed.json()
    committed = point in {"after_commit", "withdrawn", "one_unlink", "removed"}
    assert state["registered"] is not committed and state["withdrawn"] is committed
    assert state["files_verified"]
    assert ("process-delete" in settings(shared)) is not committed
    assert target.exists() is (point == "prepared")
    assert all(p.exists() and p.read_bytes() == value for p, value in protected.items())
    recovered = http.post(url + "/recover", headers=headers)
    assert recovered.status_code == 200, recovered.text
    assert recovered.json()["state"] == "reclaimed" and not recovered.json()["registered"]
    assert not target.exists() and "process-delete" not in settings(shared)
    assert not list(target.parent.glob(".prismos-stage-*"))
    assert all(p.exists() and p.read_bytes() == value for p, value in protected.items())
    assert http.post(prefix + "/imports/" + created["operation_id"] + "/recover", headers=headers).status_code == 409
    assert http.post(url + "/recover", headers=headers).json()["state"] == "reclaimed"


@pytest.mark.parametrize("shared", [False, True])
def test_hard_killed_delete_recovery_preserves_added_unknown_quarantine_members(scoped_client, monkeypatch, shared):
    http, factory, root, headers, prefix, created, target, protected = prepare(scoped_client, monkeypatch, shared)
    hard_stop(root, shared, "after_commit", plan(http, "process-delete", shared))
    operations = http.get(prefix + "/imports", headers=headers).json()["operations"]
    record = next(item for item in operations if item.get("kind") == "resource_delete")
    stage = target.parent / (".prismos-stage-" + record["operation_id"])
    foreign = stage / "foreign.txt"
    foreign.write_text("UNKNOWN CONTENT MUST REMAIN")
    original = (stage / "SKILL.md").read_bytes()
    url = prefix + "/imports/" + record["operation_id"]
    assert http.get(url, headers=headers).json()["state"] == "deletion_files_unverified"
    assert http.post(url + "/recover", headers=headers).status_code == 409
    assert foreign.read_text() == "UNKNOWN CONTENT MUST REMAIN" and (stage / "SKILL.md").read_bytes() == original
    assert "process-delete" not in settings(shared)
    assert all(p.exists() and p.read_bytes() == value for p, value in protected.items())


@pytest.mark.parametrize("shared", [False, True])
def test_hard_killed_old_delete_does_not_withdraw_same_name_new_instance_or_configuration(scoped_client, monkeypatch, shared):
    http, factory, root, headers, prefix, created, target, protected = prepare(scoped_client, monkeypatch, shared)
    hard_stop(root, shared, "after_commit", plan(http, "process-delete", shared))
    operations = http.get(prefix + "/imports", headers=headers).json()["operations"]
    old = next(item for item in operations if item.get("kind") == "resource_delete")
    replacement = http.post(prefix, headers=headers, json={"name": "process-delete", "description": "New instance", "instructions": "NEW INSTANCE CONTENT", "bound_tools": ["new-binding"]})
    assert replacement.status_code == 201, replacement.text
    current = replacement.json()
    assert current["resource_id"] != created["resource_id"]
    before = (target / "SKILL.md").read_bytes()
    url = prefix + "/imports/" + old["operation_id"]
    assert http.post(url + "/recover", headers=headers).json()["state"] == "reclaimed"
    assert http.post(url + "/recover", headers=headers).json()["state"] == "reclaimed"
    assert (target / "SKILL.md").read_bytes() == before and "NEW INSTANCE CONTENT" in before.decode()
    assert settings(shared)["process-delete"]["bound_tools"] == ["new-binding"]
    assert http.post(prefix + "/imports/" + created["operation_id"] + "/recover", headers=headers).status_code == 409
    assert all(p.exists() and p.read_bytes() == value for p, value in protected.items())


@pytest.mark.parametrize("shared", [False, True])
def test_hard_killed_delete_recovery_preserves_replaced_quarantine_directory(scoped_client, monkeypatch, shared):
    http, factory, root, headers, prefix, created, target, protected = prepare(scoped_client, monkeypatch, shared)
    hard_stop(root, shared, "after_commit", plan(http, "process-delete", shared))
    operations = http.get(prefix + "/imports", headers=headers).json()["operations"]
    old = next(item for item in operations if item.get("kind") == "resource_delete")
    stage = target.parent / (".prismos-stage-" + old["operation_id"])
    saved = stage.with_name(".kept-original-" + old["operation_id"])
    stage.rename(saved)
    stage.mkdir()
    foreign = stage / "SKILL.md"
    foreign.write_text("REPLACEMENT DIRECTORY MUST REMAIN")
    original = (saved / "SKILL.md").read_bytes()
    url = prefix + "/imports/" + old["operation_id"]
    assert http.get(url, headers=headers).json()["state"] == "deletion_files_unverified"
    assert http.post(url + "/recover", headers=headers).status_code == 409
    assert foreign.read_text() == "REPLACEMENT DIRECTORY MUST REMAIN" and (saved / "SKILL.md").read_bytes() == original
    assert "process-delete" not in settings(shared)
    assert all(p.exists() and p.read_bytes() == value for p, value in protected.items())
