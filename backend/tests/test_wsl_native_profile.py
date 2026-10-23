"""Native test profile must never stop an unrelated or active service."""

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest


def load_script(name):
    path = Path(__file__).resolve().parents[2] / "scripts" / (name + ".py")
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("change", ["identity", "session", "active-run"])
def test_restart_rejects_changed_process_or_active_run_before_any_signal(tmp_path, monkeypatch, change):
    module = load_script("octop_wsl_native_env")
    native = tmp_path / "native"
    native.mkdir()
    state = tmp_path / "state"
    state.mkdir()
    (state / "compose.yaml").write_text("unchanged-main-stack")
    known = {"pid": 12345, "starttime": "100", "cmdline_sha256": "owned-command"}
    (native / "processes.json").write_text(json.dumps({"gateway": known, "langgraph": known}))
    (native / "ownership.json").write_text("{}")
    monkeypatch.setattr(module, "NATIVE", native)
    monkeypatch.setattr(module, "STATE", state)

    class Client:
        def __init__(self, **_):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_):
            pass

        def post(self, *_args, **_kwargs):
            return SimpleNamespace(status_code=200, json=lambda: [{"thread_id": "owned-thread"}] if change == "active-run" else [])

        def get(self, *_args, **_kwargs):
            return SimpleNamespace(json=lambda: [{"status": "running"}])

    monkeypatch.setattr(module.httpx, "Client", Client)
    monkeypatch.setattr(module, "process_identity", lambda _: {"starttime": "other" if change == "identity" else "100", "cmdline_sha256": "owned-command"})
    monkeypatch.setattr(module.os, "getpgid", lambda _: 54321 if change == "session" else 12345)
    monkeypatch.setattr(module.os, "killpg", lambda *_: pytest.fail("Unrelated or active process was signalled"))
    monkeypatch.setattr(module.subprocess, "Popen", lambda *_args, **_kwargs: pytest.fail("Unexpected replacement was started"))
    with pytest.raises(AssertionError):
        module.restart(tmp_path / "result.json")
    assert (state / "compose.yaml").read_text() == "unchanged-main-stack"


def test_process_identity_waits_for_exact_exec_argv():
    import subprocess
    import sys

    module = load_script("octop_wsl_native_env")
    command = [sys.executable, "-c", "import time; time.sleep(60)"]
    process = subprocess.Popen(command)
    try:
        actual = module.settled_process_identity(process, command)
        assert actual == module.process_identity(process.pid)
        assert (Path("/proc") / str(process.pid) / "cmdline").read_bytes().split(b"\0")[:-1] == [x.encode() for x in command]
    finally:
        process.terminate()
        process.wait(timeout=5)
