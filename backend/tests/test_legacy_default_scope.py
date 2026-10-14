"""Default and old named execution obey current facts without global fallback."""

import asyncio
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from sqlalchemy import select
from test_skill_reference_transactions import durable_sqlite  # noqa: F401
from test_skill_scoped_commands import command_runtime as command_fixture  # noqa: F401
from test_skill_scoped_commands import configured, run, scoped_client, selected_runtime  # noqa: F401

from app.models.agents import CustomAgent
from app.models.governance import PlatformThreadBindingRecord
from deerflow.database.models import TenantMembership
from deerflow.sandbox import tools

command_runtime = command_fixture

def alter(factory, func):
    async def update():
        async with factory() as session:
            await func(session)
            await session.commit()
    asyncio.run(update())


def use_default(command_runtime):
    factory, _, _, _, runtime, _ = command_runtime
    runtime.context.pop("agent_id")
    runtime.context.pop("agent_name")
    async def change(session):
        row = await session.get(PlatformThreadBindingRecord, runtime.context["thread_id"])
        row.agent_name = "__default__"
        session.add(row)
    alter(factory, change)
    return factory, runtime


def test_default_actual_command_and_member_read_share_current_catalog(command_runtime):
    _, runtime = use_default(command_runtime)
    root = command_runtime[1]
    (root / "custom/tenant-a/other-user/foreign").mkdir(parents=True)
    (root / "custom/tenant-a/other-user/foreign/member.txt").write_text("FOREIGN PRIVATE")
    code = (
        "from pathlib import Path; print(Path('/mnt/skills/custom/tenant-a/user-a/collision/member.txt').read_text()); "
        "print(Path('/mnt/skills/custom/tenant-a/other-user/foreign/member.txt').exists()); "
        "Path('/mnt/user-data/outputs/default.txt').write_text('usable')"
    )
    result = run(runtime, code)
    assert "AUTHORIZED PERSONAL MEMBER" in result and "False" in result and "FOREIGN PRIVATE" not in result, result
    assert (Path(runtime.state["thread_data"]["outputs_path"]) / "default.txt").read_text() == "usable"
    content = tools.read_file_tool.func(runtime, "Read default resource", "/mnt/skills/custom/tenant-a/user-a/collision/member.txt")
    assert "AUTHORIZED PERSONAL MEMBER" in content, content


@pytest.mark.parametrize("change", ["member", "owner", "agent", "unbound"])
def test_default_authority_failures_never_execute_shared_sandbox(command_runtime, monkeypatch, change):
    factory, runtime = use_default(command_runtime)
    async def revoke(session):
        if change == "member":
            row = (await session.exec(select(TenantMembership))).scalars().one()
            row.status = "inactive"
        else:
            row = await session.get(PlatformThreadBindingRecord, runtime.context["thread_id"])
            if change == "owner":
                row.user_id = "other-user"
            elif change == "agent":
                row.agent_name = "other-agent"
            else:
                await session.delete(row)
                return
        session.add(row)
    alter(factory, revoke)
    monkeypatch.setattr(tools, "ensure_sandbox_initialized", lambda runtime: pytest.fail("Global fallback acquired"))
    result = run(runtime, "print('UNAUTHORIZED COMMAND')")
    assert result.startswith("Error:") and "UNAUTHORIZED COMMAND" not in result, result


def test_default_live_withdrawal_stops_actual_process_and_discards_stdout(command_runtime):
    factory, runtime = use_default(command_runtime)
    output = Path(runtime.state["thread_data"]["outputs_path"]) / "started.txt"
    code = "from pathlib import Path; import time; Path('/mnt/user-data/outputs/started.txt').write_text('started'); print('PRIVATE STDOUT',flush=True); time.sleep(8); Path('/mnt/user-data/outputs/late.txt').write_text('late')"
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(run, runtime, code)
        deadline = time.monotonic() + 15
        while not output.exists() and not future.done() and time.monotonic() < deadline:
            time.sleep(.05)
        assert output.exists(), future.result() if future.done() else "Command did not start"
        async def revoke(session):
            row = (await session.exec(select(TenantMembership))).scalars().one()
            row.status = "inactive"
            session.add(row)
        alter(factory, revoke)
        result = future.result(timeout=15)
    assert result.startswith("Error:") and "PRIVATE STDOUT" not in result, result
    assert not (output.parent / "late.txt").exists()


def test_old_named_agent_uses_concrete_selection_without_native_id(command_runtime):
    runtime = command_runtime[4]
    runtime.context.pop("agent_id")
    result = run(runtime, "from pathlib import Path; print(Path('/mnt/skills/custom/tenant-a/user-a/collision/member.txt').read_text()); print(Path('/mnt/skills/public/collision/member.txt').exists())")
    assert "AUTHORIZED PERSONAL MEMBER" in result and "False" in result, result
    content = tools.read_file_tool.func(runtime, "Read old configured resource", "/mnt/skills/custom/tenant-a/user-a/collision/member.txt")
    assert "AUTHORIZED PERSONAL MEMBER" in content, content


@pytest.mark.parametrize("names", [[], ["collision"]])
def test_legacy_names_require_source_choice_but_empty_agent_remains_usable(command_runtime, names):
    factory, _, agent_id, _, runtime, _ = command_runtime
    runtime.context.pop("agent_id")
    async def legacy(session):
        agent = await session.get(CustomAgent, agent_id)
        agent.meta_info = {}
        agent.skills = names
        session.add(agent)
    alter(factory, legacy)
    result = run(runtime, "from pathlib import Path; print('OWN THREAD USABLE'); print(Path('/mnt/skills/public/collision/member.txt').exists())")
    if names:
        assert result.startswith("Error:") and "OWN THREAD USABLE" not in result, result
    else:
        assert "OWN THREAD USABLE" in result and "False" in result, result


def test_default_prompt_uses_same_current_authorized_catalog(command_runtime):
    from app import runtime_adapters
    factory, _ = use_default(command_runtime)
    prompt = runtime_adapters._current_skill_prompt(None, "tenant-a", "user-a")
    assert "resource_id=" in prompt
    assert "custom/tenant-a/user-a/collision/SKILL.md" in prompt
    async def revoke(session):
        member = (await session.exec(select(TenantMembership))).scalars().one()
        member.status = "inactive"
        session.add(member)
    alter(factory, revoke)
    with pytest.raises(runtime_adapters.ExecutionTrustError):
        runtime_adapters._current_skill_prompt(None, "tenant-a", "user-a")


def test_missing_provider_for_default_host_never_falls_back(command_runtime, monkeypatch):
    _, runtime = use_default(command_runtime)
    monkeypatch.setattr(tools, "get_skill_command_provider", lambda: None)
    result = run(runtime, "print('UNAUTHORIZED COMMAND')")
    assert result.startswith("Error:") and "UNAUTHORIZED COMMAND" not in result, result


def test_empty_scope_provider_for_host_never_falls_back(command_runtime, monkeypatch):
    _, runtime = use_default(command_runtime)
    monkeypatch.setattr(tools, "get_skill_command_provider", lambda: lambda *args: None)
    monkeypatch.setattr(tools, "ensure_sandbox_initialized", lambda runtime: pytest.fail("Global fallback acquired"))
    result = run(runtime, "print('UNAUTHORIZED COMMAND')")
    assert result.startswith("Error:") and "UNAUTHORIZED COMMAND" not in result, result


def test_default_disabled_resource_is_absent_from_command_and_member_read(command_runtime):
    from deerflow.database.models import TenantSkill

    factory, runtime = use_default(command_runtime)
    async def disable(session):
        resource = (await session.exec(select(TenantSkill).where(TenantSkill.user_id == "user-a"))).scalars().one()
        resource.enabled = False
        session.add(resource)
    alter(factory, disable)
    result = run(runtime, "from pathlib import Path; print(Path('/mnt/skills/custom/tenant-a/user-a/collision/member.txt').exists())")
    assert "False" in result and "MEMBER" not in result, result
    content = tools.read_file_tool.func(runtime, "Read disabled resource", "/mnt/skills/custom/tenant-a/user-a/collision/member.txt")
    assert content.startswith("Error:") and "AUTHORIZED PERSONAL MEMBER" not in content, content
