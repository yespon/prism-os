"""Verify retained source, immutable contexts and host isolation of worker preparation."""

import hashlib
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import octop_worker_compat as worker  # noqa: E402


@pytest.fixture
def context(tmp_path, monkeypatch):
    # Keep the real verified source; redirect only the owned output directory.
    original = worker.ROOT
    stage = tmp_path / "root"
    stage.mkdir()
    for name in ["vendor", "docker"]:
        (stage / name).symlink_to(original / name, target_is_directory=True)
    (stage / "backend").mkdir()
    (stage / "backend/uv.lock").write_bytes((original / "backend/uv.lock").read_bytes())
    monkeypatch.setattr(worker, "ROOT", stage)
    return stage / "backend/tmp/context"


def test_worker_exports_only_verified_source_and_keeps_host_lock(context):
    host = worker.ROOT / "backend/uv.lock"
    before = host.read_bytes()
    worker.prepare(context)
    receipt = json.loads((context / "source-receipt.json").read_text())
    assert receipt["excluded_harness_members"] == 51
    assert not receipt["native_execution_enabled"]
    assert len(list((context / "archives").glob("*.whl"))) == 3
    assert not list((context / "archives").glob("*harness*"))
    retained = receipt["harness_retained_source_sha256"]
    actual = {p.relative_to(context / "harness").as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
              for p in (context / "harness").rglob("*") if p.is_file()}
    assert actual == retained
    assert not any("skills/pptx/" in p for p in retained)
    assert (context / "requirements.lock").read_bytes() == (worker.ROOT / "docker/octop-worker-compat/requirements.lock").read_bytes()
    worker.prepare(context)
    assert host.read_bytes() == before
    (context / "worker_rpc.py").write_text("changed")
    with pytest.raises(ValueError, match="different contents"):
        worker.prepare(context)
    assert host.read_bytes() == before


@pytest.mark.parametrize("kind", ["outside", "alias"])
def test_worker_rejects_unowned_or_aliased_context(context, kind):
    target = worker.ROOT / "outside"
    if kind == "alias":
        actual = worker.ROOT / "backend/tmp/actual"
        actual.mkdir(parents=True)
        target = actual.parent / "alias"
        target.symlink_to(actual, target_is_directory=True)
    with pytest.raises(ValueError, match="non-aliased owned"):
        worker.prepare(target)


def test_new_source_requirements_cannot_silently_reuse_old_worker_lock(tmp_path):
    lock = tmp_path / "requirements.lock"
    lock.write_text("langchain-mcp-adapters==0.3.0 \\\n    --hash=sha256:example\n")
    worker.validate_lock(lock, ["langchain-mcp-adapters>=0.3.0"], {"langchain-mcp-adapters": {"0.3.0"}})
    with pytest.raises(ValueError, match="retained source requirements"):
        worker.validate_lock(lock, ["langchain-mcp-adapters>=0.4.0"], {})
    with pytest.raises(ValueError, match="unique upstream version"):
        worker.validate_lock(lock, [], {"langchain-mcp-adapters": {"0.4.0"}})
