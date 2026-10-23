"""File/image/presentation access through original tools and current native facts."""

import asyncio
import base64
import importlib
from pathlib import Path

import pytest
from sqlalchemy import select
from test_skill_member_tools import configured, scoped_client  # noqa: F401
from test_skill_member_tools import selected_runtime as member_runtime
from test_skill_reference_transactions import durable_sqlite  # noqa: F401

from deerflow.config.paths import Paths
from deerflow.database.models import TenantMembership
from deerflow.sandbox import tools

selected_runtime = member_runtime
image_tool = importlib.import_module("deerflow.tools.builtins.view_image_tool")
present_tool = importlib.import_module("deerflow.tools.builtins.present_file_tool")


def test_image_tool_cannot_read_host_file_outside_current_execution(selected_runtime):
    _, root, _, _, runtime = selected_runtime
    private = root.parent / "host-private.png"
    private.write_bytes(b"PRIVATE HOST IMAGE BYTES")
    result = image_tool.view_image_tool.func(runtime, str(private), "image-boundary")
    assert "viewed_images" not in result.update
    assert result.update["messages"][0].content.startswith("Error:")


def test_withdrawn_membership_cannot_retrieve_image_using_old_runtime(selected_runtime):
    factory, root, _, _, runtime = selected_runtime
    output = root.parent / "outputs"
    output.mkdir(exist_ok=True)
    image = output / "result.png"
    image.write_bytes(b"OWNED BEFORE WITHDRAWAL")

    async def withdraw():
        async with factory() as session:
            member = (await session.exec(select(TenantMembership))).scalars().one()
            member.status = "inactive"
            session.add(member)
            await session.commit()

    asyncio.run(withdraw())
    result = image_tool.view_image_tool.func(runtime, "/mnt/user-data/outputs/result.png", "image-withdrawn")
    assert "viewed_images" not in result.update
    assert result.update["messages"][0].content.startswith("Error:")


def test_forged_presentation_outputs_cannot_register_another_root(selected_runtime):
    _, root, _, _, runtime = selected_runtime
    private = root.parent / "foreign-outputs"
    private.mkdir()
    file = private / "report.txt"
    file.write_text("FOREIGN RESULT")
    runtime.state["thread_data"]["outputs_path"] = str(private)
    result = present_tool.present_file_tool.func(runtime, [str(file)], "present-forged")
    assert "artifacts" not in result.update
    assert result.update["messages"][0].content.startswith("Error:")


@pytest.fixture
def owned_runtime(selected_runtime, monkeypatch):
    from app import runtime_adapters

    factory, root, agent, calls, runtime = selected_runtime
    paths = Paths(root.parent / "file-access-owned")
    monkeypatch.setattr("deerflow.config.paths.get_paths", lambda: paths)
    monkeypatch.setattr("deerflow.runtime._file_access_provider", runtime_adapters._current_file_access)
    paths.ensure_thread_dirs("user-a", "member-thread", tenant_id="tenant-a")
    runtime.state["thread_data"] = {key + "_path": str(getattr(paths, "sandbox_" + ("work" if key == "workspace" else key) + "_dir")("user-a", "member-thread", tenant_id="tenant-a")) for key in ("workspace", "uploads", "outputs")}
    return factory, root, agent, calls, runtime


def test_current_owner_can_read_image_present_downloadable_output_and_text(owned_runtime):
    _, _, _, calls, runtime = owned_runtime
    output = Path(runtime.state["thread_data"]["outputs_path"])
    (output / "result.png").write_bytes(b"\x89PNG\x00CURRENT OWNED IMAGE")
    (output / "report.txt").write_text("CURRENT OWNED RESULT")
    image = image_tool.view_image_tool.func(runtime, "/mnt/user-data/outputs/result.png", "positive-image")
    assert base64.b64decode(image.update["viewed_images"]["/mnt/user-data/outputs/result.png"]["base64"]) == b"\x89PNG\x00CURRENT OWNED IMAGE"
    present = present_tool.present_file_tool.func(runtime, [str(output / "report.txt")], "positive-output")
    assert present.update["artifacts"] == ["/mnt/user-data/outputs/report.txt"]
    assert "CURRENT OWNED RESULT" in tools.read_file_tool.func(runtime, "Read result", "/mnt/user-data/outputs/report.txt")
    assert calls == []


@pytest.mark.parametrize("change", ["membership", "tenant", "agent", "thread-owner", "state", "symlink", "hardlink", "ancestor"])
def test_current_owner_authority_and_path_identity_are_rechecked(owned_runtime, change):
    from app.models.agents import CustomAgent
    from app.models.governance import PlatformThreadBindingRecord
    from deerflow.database.models import Tenant

    factory, root, agent, _, runtime = owned_runtime
    output = Path(runtime.state["thread_data"]["outputs_path"])
    image = output / "result.png"
    image.write_bytes(b"PRIVATE IMAGE")

    async def revoke():
        async with factory() as session:
            if change == "membership":
                row = (await session.exec(select(TenantMembership))).scalars().one()
                row.status = "inactive"
            elif change == "tenant":
                row = await session.get(Tenant, "tenant-a")
                row.status = "inactive"
            elif change == "agent":
                row = await session.get(CustomAgent, agent)
                row.enabled = False
            else:
                row = await session.get(PlatformThreadBindingRecord, "member-thread")
                row.user_id = "another-member"
            session.add(row)
            await session.commit()

    if change in {"membership", "tenant", "agent", "thread-owner"}:
        asyncio.run(revoke())
    elif change == "state":
        runtime.state["thread_data"]["outputs_path"] = str(root.parent)
    elif change in {"symlink", "hardlink"}:
        import os

        private = root.parent / "private.png"
        private.write_bytes(b"PRIVATE IMAGE")
        image.unlink()
        image.symlink_to(private) if change == "symlink" else os.link(private, image)
    else:
        original = output.with_name("previous")
        output.rename(original)
        output.symlink_to(original, target_is_directory=True)
    result = image_tool.view_image_tool.func(runtime, "/mnt/user-data/outputs/result.png", "deny-image")
    assert "viewed_images" not in result.update
    result = present_tool.present_file_tool.func(runtime, ["/mnt/user-data/outputs/result.png"], "deny-output")
    assert "artifacts" not in result.update
    assert tools.read_file_tool.func(runtime, "Read revoked result", "/mnt/user-data/outputs/result.png").startswith("Error:")


def test_selected_skill_image_uses_current_binary_member_authority(owned_runtime):
    _, root, _, calls, runtime = owned_runtime
    (root / "custom/tenant-a/user-a/collision/image.png").write_bytes(b"\x89PNGSELECTED")
    (root / "public/collision/image.png").write_bytes(b"UNSELECTED")
    selected = "/mnt/skills/custom/tenant-a/user-a/collision/image.png"
    result = image_tool.view_image_tool.func(runtime, selected, "selected-image")
    assert base64.b64decode(result.update["viewed_images"][selected]["base64"]) == b"\x89PNGSELECTED"
    result = image_tool.view_image_tool.func(runtime, "/mnt/skills/public/collision/image.png", "unselected-image")
    assert "viewed_images" not in result.update
    assert calls == []


def test_owned_file_mutations_stay_in_current_thread_and_skills_are_read_only(owned_runtime):
    _, root, _, _, runtime = owned_runtime
    path = "/mnt/user-data/outputs/new/report.txt"
    assert tools.write_file_tool.func(runtime, "Write output", path, "first") == "OK"
    assert tools.write_file_tool.func(runtime, "Append output", path, " second", True) == "OK"
    assert tools.str_replace_tool.func(runtime, "Edit output", path, "first", "updated") == "OK"
    assert "updated second" in tools.read_file_tool.func(runtime, "Read output", path)
    selected = "/mnt/skills/custom/tenant-a/user-a/collision/member.txt"
    assert tools.write_file_tool.func(runtime, "Attempt source edit", selected, "changed").startswith("Error:")
    assert (root / "custom/tenant-a/user-a/collision/member.txt").read_text() == "AUTHORIZED PERSONAL MEMBER"
    private = root.parent / "private.txt"
    private.write_text("PRIVATE")
    output = Path(runtime.state["thread_data"]["outputs_path"])
    (output / "alias.txt").symlink_to(private)
    assert tools.write_file_tool.func(runtime, "Attempt alias edit", "/mnt/user-data/outputs/alias.txt", "changed").startswith("Error:")
    assert private.read_text() == "PRIVATE"


def test_owned_listing_keeps_two_levels_without_exposing_aliases(owned_runtime):
    _, root, _, _, runtime = owned_runtime
    output = Path(runtime.state["thread_data"]["outputs_path"])
    (output / "nested").mkdir()
    (output / "nested/report.txt").write_text("OWNED")
    (output / "foreign").symlink_to(root, target_is_directory=True)
    result = tools.ls_tool.func(runtime, "Browse owned results", "/mnt/user-data/outputs")
    assert "/mnt/user-data/outputs/nested/report.txt" in result
    assert "foreign" not in result and str(output) not in result
