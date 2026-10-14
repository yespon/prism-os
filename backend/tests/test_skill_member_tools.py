"""Current native Skill member reads through the original Sandbox tools."""

import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest
from langchain.tools import ToolRuntime
from sqlalchemy import select
from test_agent_skill_references import configured as reference_configuration
from test_agent_skill_references import scoped_client as shared_client
from test_skill_reference_transactions import durable_sqlite  # noqa: F401

from app.models.agents import CustomAgent
from deerflow.database.models import Tenant, TenantMembership, TenantSkill
from deerflow.sandbox import tools

configured = reference_configuration
scoped_client = shared_client


@pytest.fixture
def selected_runtime(configured, monkeypatch):
    from app import runtime_adapters
    from app.integrations import agent_skill_members

    monkeypatch.setattr(agent_skill_members, "get_skills_root_path", lambda: configured[2])

    http, factory, root, resources = configured
    created = http.post("/api/agents", json={"name": "member-agent", "system_prompt": "Member role", "skill_binding_mode": "selected", "skill_resources": [resources["personal"]]})
    assert created.status_code == 201, created.text
    native_id = created.json()["id"]
    from app.platform.execution.trust import ThreadBindingRepository
    asyncio.run(ThreadBindingRepository(factory).create("member-thread", "tenant-a", "user-a"))
    asyncio.run(ThreadBindingRepository(factory).bind_agent("member-thread", "tenant-a", "user-a", "member-agent"))
    for folder, content in [(root / "custom/tenant-a/user-a/collision", "AUTHORIZED PERSONAL MEMBER"), (root / "custom/tenant-a/collision", "UNSELECTED SHARED MEMBER"), (root / "public/collision", "UNSELECTED PUBLIC MEMBER")]:
        (folder / "member.txt").write_text(content)
    calls = []

    def path(value):
        return root / value.removeprefix("/mnt/skills/") if value.startswith("/mnt/skills/") else Path(value)

    def read(value):
        calls.append(("read", value))
        return path(value).read_text()

    def listing(value):
        calls.append(("ls", value))
        return sorted(p.name for p in path(value).iterdir())

    monkeypatch.setattr(tools, "ensure_sandbox_initialized", lambda runtime: SimpleNamespace(read_file=read, list_dir=listing))
    monkeypatch.setattr(tools, "ensure_thread_directories_exist", lambda runtime: None)
    monkeypatch.setattr(tools, "_get_skills_container_path", lambda: "/mnt/skills")
    monkeypatch.setattr(tools, "_get_skills_host_path", lambda: str(root))
    monkeypatch.setattr(runtime_adapters, "get_session_factory", lambda: factory)
    if hasattr(tools, "get_skill_file_provider"):
        monkeypatch.setattr(tools, "get_skill_file_provider", lambda: runtime_adapters._current_skill_member)
        monkeypatch.setattr(tools, "load_runtime_adapters", lambda: None)
    runtime = ToolRuntime(
        state={"thread_data": {"workspace_path": str(root.parent / "workspace"), "uploads_path": str(root.parent / "uploads"), "outputs_path": str(root.parent / "outputs")}},
        context={"tenant_id": "tenant-a", "user_id": "user-a", "thread_id": "member-thread", "agent_name": "member-agent", "agent_id": native_id},
        config={},
        stream_writer=lambda value: None,
        tool_call_id="member-read",
        store=None,
    )
    return factory, root, native_id, calls, runtime


@pytest.mark.parametrize("local", [False, True])
@pytest.mark.parametrize("change", [None, "disabled", "membership", "generation", "unselected", "alias", "agent", "tenant"])
def test_native_member_read_rechecks_current_scope_without_unchecked_sandbox_read(selected_runtime, monkeypatch, local, change):
    factory, root, agent_id, calls, runtime = selected_runtime
    monkeypatch.setattr(tools, "is_local_sandbox", lambda runtime: local)
    requested = "/mnt/skills/custom/tenant-a/user-a/collision/member.txt"

    async def alter():
        async with factory() as session:
            if change in {"disabled", "generation"}:
                row = (await session.exec(select(TenantSkill).where(TenantSkill.user_id == "user-a"))).scalars().one()
                if change == "disabled":
                    row.enabled = False
                else:
                    from datetime import timedelta

                    row.created_at += timedelta(seconds=1)
            elif change == "membership":
                row = (await session.exec(select(TenantMembership))).scalars().one()
                row.status = "inactive"
            elif change == "agent":
                row = await session.get(CustomAgent, agent_id)
                row.enabled = False
            elif change == "tenant":
                row = await session.get(Tenant, "tenant-a")
                row.status = "inactive"
            else:
                return
            session.add(row)
            await session.commit()

    asyncio.run(alter())
    if change == "unselected":
        requested = "/mnt/skills/public/collision/member.txt"
    if change == "alias":
        member = root / "custom/tenant-a/user-a/collision/member.txt"
        member.unlink()
        member.symlink_to(root / "public/collision/member.txt")
    content = tools.read_file_tool.func(runtime, "Read selected member", requested)
    if change is None:
        assert "AUTHORIZED PERSONAL MEMBER" in content
    else:
        assert content.startswith("Error:") and "MEMBER" not in content
    assert calls == []


@pytest.mark.parametrize("local", [False, True])
def test_listing_projects_selected_sources_and_never_uses_shared_sandbox(selected_runtime, monkeypatch, local):
    _, root, _, calls, runtime = selected_runtime
    monkeypatch.setattr(tools, "is_local_sandbox", lambda runtime: local)
    folder = root / "custom/tenant-a/user-a/collision"
    (folder / "nested").mkdir()
    (folder / "nested/example.txt").write_text("second level\nlast\n")
    broad = tools.ls_tool.func(runtime, "Browse selected sources", "/mnt/skills")
    assert "/mnt/skills/custom/" in broad and "/public/" not in broad
    own = tools.ls_tool.func(runtime, "Browse selected members", "/mnt/skills/custom/tenant-a/user-a/collision")
    assert "/mnt/skills/custom/tenant-a/user-a/collision/nested/example.txt" in own
    assert str(root) not in own
    denied = tools.ls_tool.func(runtime, "Browse unselected source", "/mnt/skills/public/collision")
    assert denied.startswith("Error:")
    content = tools.read_file_tool.func(runtime, "Read a line", "/mnt/skills/custom/tenant-a/user-a/collision/nested/example.txt", 2, 2)
    assert "last" in content and "second level" not in content
    assert calls == []


@pytest.mark.parametrize("replacement", ["body", "directory"])
def test_member_change_after_source_resolution_does_not_return_bytes(selected_runtime, monkeypatch, replacement):
    from app.integrations import agent_skill_members as members

    _, root, _, calls, runtime = selected_runtime
    original = members._snapshot_read

    def change(directory, *args):
        if replacement == "body":
            (directory / "member.txt").write_text("LATE SECRET")
        else:
            original_main = (directory / "SKILL.md").read_bytes()
            directory.rename(directory.with_name("previous"))
            directory.mkdir()
            (directory / "SKILL.md").write_bytes(original_main)
            (directory / "member.txt").write_text("LATE SECRET")
        return original(directory, *args)

    monkeypatch.setattr(members, "_snapshot_read", change)
    result = tools.read_file_tool.func(runtime, "Read current member", "/mnt/skills/custom/tenant-a/user-a/collision/member.txt")
    assert result.startswith("Error:") and "SECRET" not in result and str(root) not in result
    assert calls == []


def test_selected_shared_root_cannot_read_nested_private_resource(selected_runtime):
    from app.integrations.agent_skill_references import KEY, SkillBinding, SkillResourceReference
    from deerflow.skills.resource_identity import registered_resource_id

    factory, root, agent_id, calls, runtime = selected_runtime
    folder = root / "custom/tenant-a/user-a"
    (folder / "SKILL.md").write_text("---\nname: user-a\ndescription: shared overlap\n---\nSHARED ROLE")

    async def select_parent():
        async with factory() as session:
            row = TenantSkill(tenant_id="tenant-a", user_id="__tenant_shared_skill__:tenant-a", name="user-a", enabled=True, category="custom", install_dir=str(folder))
            session.add(row)
            await session.flush()
            agent = await session.get(CustomAgent, agent_id)
            agent.meta_info = {KEY: SkillBinding(mode="selected", resources=[SkillResourceReference(name="user-a", scope="tenant", resource_id=registered_resource_id(row))]).model_dump()}
            session.add(agent)
            await session.commit()

    asyncio.run(select_parent())
    denied = tools.read_file_tool.func(runtime, "Read nested unselected private member", "/mnt/skills/custom/tenant-a/user-a/collision/member.txt")
    assert denied.startswith("Error:") and "MEMBER" not in denied
    listing = tools.ls_tool.func(runtime, "Browse shared members", "/mnt/skills/custom/tenant-a/user-a")
    assert "collision" not in listing and "SKILL.md" in listing
    assert calls == []


@pytest.mark.parametrize("path", ["//mnt/skills/public/collision/member.txt", "/mnt/other/../skills/public/collision/member.txt", "/mnt/skills/custom/tenant-a/user-a/collision/../collision/member.txt"])
def test_equivalent_or_traversing_paths_cannot_bypass_member_authority(selected_runtime, path):
    _, _, _, calls, runtime = selected_runtime
    result = tools.read_file_tool.func(runtime, "Read untrusted path", path)
    assert result.startswith("Error:") and "MEMBER" not in result
    assert calls == []


def test_provider_failure_never_falls_back_to_unchecked_sandbox(selected_runtime, monkeypatch):
    _, _, _, calls, runtime = selected_runtime
    monkeypatch.setattr(tools, "get_skill_file_provider", lambda: None)
    result = tools.read_file_tool.func(runtime, "Read selected source", "/mnt/skills/custom/tenant-a/user-a/collision/member.txt")
    assert result.startswith("Error:")
    assert calls == []


@pytest.mark.parametrize("change", ["selection", "disable"])
def test_post_read_authority_change_discards_member_result(selected_runtime, monkeypatch, change):
    from app.integrations import agent_skill_members as members
    from app.integrations.agent_skill_references import KEY, SkillBinding

    _, _, agent_id, calls, runtime = selected_runtime
    original = members.current_member

    async def change_after_read(session, *args):
        result = await original(session, *args)
        if change == "selection":
            row = await session.get(CustomAgent, agent_id)
            row.meta_info = {KEY: SkillBinding(mode="selected", resources=[]).model_dump()}
        else:
            row = (await session.exec(select(TenantSkill).where(TenantSkill.user_id == "user-a"))).scalars().one()
            row.enabled = False
        session.add(row)
        await session.flush()
        return result

    monkeypatch.setattr(members, "current_member", change_after_read)
    result = tools.read_file_tool.func(runtime, "Read current source", "/mnt/skills/custom/tenant-a/user-a/collision/member.txt")
    assert result.startswith("Error:") and "MEMBER" not in result
    assert calls == []
