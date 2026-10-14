"""Actual native bash commands in kernel namespaces using original host facts."""

import asyncio
import os
import shlex
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from sqlalchemy import select
from test_skill_member_tools import configured, scoped_client  # noqa: F401
from test_skill_member_tools import selected_runtime as member_runtime
from test_skill_reference_transactions import durable_sqlite  # noqa: F401

from app.models.agents import CustomAgent
from deerflow.database.models import TenantSkill
from deerflow.sandbox import tools
from deerflow.sandbox.local.local_sandbox_provider import LocalSandboxProvider

selected_runtime = member_runtime


@pytest.fixture
def command_runtime(selected_runtime, monkeypatch):
    from app import runtime_adapters
    from app.integrations import skill_command_views
    from deerflow.config.paths import Paths

    factory, root, agent_id, calls, runtime = selected_runtime
    paths = Paths(str(root.parent / "owned-thread-data"))
    thread_id = runtime.context["thread_id"]
    thread_data = {key + "_path": str(getattr(paths, "sandbox_" + ("work" if key == "workspace" else key) + "_dir")("user-a", thread_id, tenant_id="tenant-a")) for key in ("workspace", "uploads", "outputs")}
    runtime.state["thread_data"] = thread_data
    runtime.state["sandbox"] = {"sandbox_id": "local"}
    sandbox = LocalSandboxProvider()
    monkeypatch.setattr(tools, "get_sandbox_provider", lambda: sandbox)
    monkeypatch.setattr(tools, "_get_text2image_env", lambda *args: {})
    monkeypatch.setattr(skill_command_views, "get_skills_root_path", lambda: root)
    # The adapter loads the original path service at call time.
    monkeypatch.setattr("deerflow.config.paths.get_paths", lambda: paths)
    if hasattr(tools, "get_skill_command_provider"):
        monkeypatch.setattr(tools, "get_skill_command_provider", lambda: runtime_adapters._current_skill_command)
    return factory, root, agent_id, calls, runtime, sandbox


def run(runtime, code):
    return tools.bash_tool.func(runtime, "Use selected resource", "python -c " + shlex.quote(code))


def test_actual_python_reads_selected_source_and_persists_owned_output(command_runtime):
    _, root, _, _, runtime, _ = command_runtime
    result = run(runtime, "from pathlib import Path; p=Path('/mnt/skills/custom/tenant-a/user-a/collision/member.txt'); text=p.read_text(); Path('/mnt/user-data/outputs/result.txt').write_text(text); print(text)")
    assert "AUTHORIZED PERSONAL MEMBER" in result, result
    assert (Path(runtime.state["thread_data"]["outputs_path"]) / "result.txt").read_text() == "AUTHORIZED PERSONAL MEMBER"
    assert "UNSELECTED" not in result and str(root) not in result


@pytest.mark.parametrize("target", ["public", "shared", "host", "proc-root"])
def test_computed_paths_cannot_access_unselected_or_host_files(command_runtime, target):
    _, root, _, _, runtime, _ = command_runtime
    secret = root.parent / "host-only.txt"
    secret.write_text("HOST-ONLY CONTENT")
    path = {"public": "/mnt/skills/public/collision/member.txt", "shared": "/mnt/skills/custom/tenant-a/collision/member.txt", "host": str(secret), "proc-root": "/proc/self/root" + str(secret)}[target]
    code = "from pathlib import Path; p=Path(" + repr(path) + "); print(p.read_text() if p.exists() else 'unavailable')"
    result = run(runtime, code)
    assert "unavailable" in result and "CONTENT" not in result and "MEMBER" not in result, result


def test_selected_resources_are_readonly_and_do_not_inherit_host_environment(command_runtime, monkeypatch):
    _, root, _, _, runtime, _ = command_runtime
    monkeypatch.setenv("PRISMOS_HOST_PRIVATE_CANARY", "HOST ENVIRONMENT CANARY")
    code = (
        "import os; from pathlib import Path; print('host-env-present', 'PRISMOS_HOST_PRIVATE_CANARY' in os.environ); "
        "p=Path('/mnt/skills/custom/tenant-a/user-a/collision/member.txt');\n"
        "try: p.write_text('CHANGED')\nexcept OSError: print('readonly')"
    )
    result = run(runtime, code)
    assert "host-env-present False" in result and "readonly" in result, result
    assert (root / "custom/tenant-a/user-a/collision/member.txt").read_text() == "AUTHORIZED PERSONAL MEMBER"


def test_executable_members_and_thread_virtual_environment_remain_usable(command_runtime):
    _, root, _, _, runtime, _ = command_runtime
    script = root / "custom/tenant-a/user-a/collision/run.sh"
    script.write_text('#!/bin/sh\nprintf "SELECTED SCRIPT\\n"\n')
    script.chmod(0o755)
    result = tools.bash_tool.func(
        runtime, "Run selected script with owned Python", '/mnt/skills/custom/tenant-a/user-a/collision/run.sh && python -m venv /mnt/user-data/workspace/.venv && /mnt/user-data/workspace/.venv/bin/python -c "import sys; print(sys.prefix)"'
    )
    assert "SELECTED SCRIPT" in result and "/mnt/user-data/workspace/.venv" in result, result
    assert "Exit Code:" not in result


def test_unregistered_nested_source_is_not_granted_by_selected_parent(command_runtime):
    _, root, _, _, runtime, _ = command_runtime
    unknown = root / "custom/tenant-a/user-a/collision/unknown"
    unknown.mkdir()
    (unknown / "SKILL.md").write_text("---\nname: unknown\ndescription: independent unknown\n---\nUNKNOWN")
    (unknown / "secret.txt").write_text("UNKNOWN SOURCE CONTENT")
    result = run(runtime, "from pathlib import Path; p=Path('/mnt/skills/custom/tenant-a/user-a/collision/unknown/secret.txt'); print(p.read_text() if p.exists() else 'unavailable')")
    assert "unavailable" in result and "UNKNOWN" not in result, result


@pytest.mark.parametrize("change", ["agent", "skill"])
def test_committed_withdrawal_terminates_actual_namespace_and_discards_output(command_runtime, change):
    factory, _, agent_id, _, runtime, _ = command_runtime
    output = Path(runtime.state["thread_data"]["outputs_path"]) / "ticks.txt"
    code = (
        "import os,time; from pathlib import Path; p=Path('/mnt/user-data/outputs/ticks.txt'); "
        "print('EARLY AUTHORIZED OUTPUT',flush=True); child=os.fork();\n"
        "if child==0: os.setsid()\nwhile True:\n p.write_text(str(time.time()))\n time.sleep(.05)"
    )
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(run, runtime, code)
        deadline = time.monotonic() + 15
        while not output.exists() and not future.done() and time.monotonic() < deadline:
            time.sleep(0.05)
        assert output.exists(), future.result() if future.done() else "Process did not start"

        async def disable():
            async with factory() as session:
                row = await session.get(CustomAgent, agent_id) if change == "agent" else (await session.exec(select(TenantSkill).where(TenantSkill.user_id == "user-a"))).scalars().one()
                row.enabled = False
                session.add(row)
                await session.commit()

        asyncio.run(disable())
        result = future.result(timeout=15)
    assert result.startswith("Error:") and "EARLY AUTHORIZED OUTPUT" not in result, result
    stopped = output.read_bytes()
    time.sleep(0.3)
    assert output.read_bytes() == stopped


def test_forged_state_directory_is_rejected_before_command_execution(command_runtime):
    _, root, _, _, runtime, _ = command_runtime
    runtime.state["thread_data"]["workspace_path"] = str(root)
    result = run(runtime, "print('MUST NOT EXECUTE')")
    assert result.startswith("Error:") and "MUST NOT EXECUTE" not in result


@pytest.fixture
def container_command_runtime(command_runtime, monkeypatch):
    from deerflow.community.aio_sandbox.aio_sandbox_provider import AioSandboxProvider
    from deerflow.community.aio_sandbox.local_backend import LocalContainerBackend
    from deerflow.config.paths import get_paths

    provider = object.__new__(AioSandboxProvider)
    image = os.getenv('PRISMOS_SCOPED_TEST_IMAGE', 'prismos-scoped-execution:test')
    provider._config = {'image': image}
    provider._backend = LocalContainerBackend(image=image, base_port=8090, container_prefix="unused-original", config_mounts=[], environment={})
    paths = get_paths()
    monkeypatch.setattr("deerflow.community.aio_sandbox.aio_sandbox_provider.get_paths", lambda: paths)
    monkeypatch.setattr(tools, "get_sandbox_provider", lambda: provider)
    return command_runtime


def test_actual_configured_image_reads_only_current_selected_view(container_command_runtime):
    _, root, _, _, runtime, _ = container_command_runtime
    code = (
        "from pathlib import Path; print(Path('/mnt/skills/custom/tenant-a/user-a/collision/member.txt').read_text()); "
        "print('public-present',Path('/mnt/skills/public/collision/member.txt').exists()); "
        "Path('/mnt/user-data/outputs/container.txt').write_text('CONTAINER OUTPUT')"
    )
    result = run(runtime, code)
    assert "AUTHORIZED PERSONAL MEMBER" in result and "public-present False" in result, result
    assert str(root) not in result and "UNSELECTED" not in result
    assert (Path(runtime.state["thread_data"]["outputs_path"]) / "container.txt").read_text() == "CONTAINER OUTPUT"


def test_actual_container_selected_source_is_readonly_and_host_env_is_absent(container_command_runtime, monkeypatch):
    _, root, _, _, runtime, _ = container_command_runtime
    monkeypatch.setenv("PRISMOS_HOST_PRIVATE_CANARY", "HOST-ENV CANARY")
    code = (
        "import os; from pathlib import Path; print('host-env-present','PRISMOS_HOST_PRIVATE_CANARY' in os.environ); "
        "p=Path('/mnt/skills/custom/tenant-a/user-a/collision/member.txt');\ntry: p.write_text('CHANGED')\nexcept OSError: print('readonly')"
    )
    result = run(runtime, code)
    assert "host-env-present False" in result and "readonly" in result, result
    assert (root / "custom/tenant-a/user-a/collision/member.txt").read_text() == "AUTHORIZED PERSONAL MEMBER"


def test_actual_container_withdrawal_stops_detached_children(container_command_runtime):
    test_committed_withdrawal_terminates_actual_namespace_and_discards_output(container_command_runtime, "skill")


def test_real_container_create_reply_loss_is_checked_and_owned_lease_reclaimed(container_command_runtime, monkeypatch):
    import subprocess

    from deerflow.community.aio_sandbox import scoped_command as worker

    _, _, _, _, runtime, _ = container_command_runtime
    original = worker.subprocess.run
    names = []

    def lost_reply(args, *positional, **kwargs):
        result = original(args, *positional, **kwargs)
        if args[:2] == ["docker", "create"]:
            assert result.returncode == 0
            names.append(args[args.index("--name") + 1])
            raise subprocess.TimeoutExpired(args, 30)
        return result

    monkeypatch.setattr(worker.subprocess, "run", lost_reply)
    result = run(runtime, "print('MUST NOT START')")
    assert result.startswith("Error:") and "MUST NOT START" not in result
    assert len(names) == 1
    checked = original(["docker", "inspect", names[0]], capture_output=True, text=True)
    assert checked.returncode != 0 and "No such" in checked.stderr


def test_missing_scoped_provider_never_launches_original_global_sandbox(command_runtime, monkeypatch):
    _, _, _, _, runtime, _ = command_runtime
    monkeypatch.setattr(tools, "get_skill_command_provider", lambda: None)

    def forbidden(*args):
        raise AssertionError("Original unrestricted Sandbox must not be acquired")

    monkeypatch.setattr(tools, "ensure_sandbox_initialized", forbidden)
    result = run(runtime, "print('MUST NOT START')")
    assert result.startswith("Error:") and "MUST NOT START" not in result


def test_javascript_runtime_reads_authorized_member_without_host_home(command_runtime):
    _, _, _, _, runtime, _ = command_runtime
    code = "console.log(require('fs').readFileSync('/mnt/skills/custom/tenant-a/user-a/collision/member.txt','utf8')); console.log('host-home-present',require('fs').existsSync('/root'));"
    result = tools.bash_tool.func(runtime, 'Use selected JavaScript helper', 'node -e '+shlex.quote(code))
    assert 'AUTHORIZED PERSONAL MEMBER' in result and 'host-home-present false' in result, result
