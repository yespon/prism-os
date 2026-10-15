"""Actual selected auxiliary member reads and OS commands; no model/channel calls."""
import asyncio
import json
import os
import shlex
from pathlib import Path

import pytest
from sqlalchemy import select
from test_agent_skill_references import scoped_client as reference_client
from test_skill_member_tools import configured as member_configuration
from test_skill_member_tools import selected_runtime as member_runtime
from test_skill_reference_transactions import durable_sqlite  # noqa: F401
from test_skill_scoped_commands import command_runtime as local_commands
from test_skill_scoped_commands import container_command_runtime as image_commands

from app.integrations import skill_imports
from app.integrations.agent_skill_references import save_binding
from app.integrations.octop.resources import resource_preflight
from app.integrations.octop.skill_packages import prepare_skill_package, skill_archive
from app.models.agents import CustomAgent
from deerflow.database.models import TenantMembership
from deerflow.sandbox import tools
from deerflow.skills.resource_identity import registered_resource_id

scoped_client = reference_client
configured = member_configuration
selected_runtime = member_runtime
command_runtime = local_commands
container_command_runtime = image_commands


@pytest.fixture(params=["local", "configured-image"])
def execution_runtime(request):
    return request.getfixturevalue("command_runtime" if request.param == "local" else "container_command_runtime")


def install_selected(runtime_facts, requested):
    factory, root, agent_id, _, _, _ = runtime_facts
    packages = {}

    async def install():
        selections = []
        for template, resource_root in requested:
            declaration = resource_preflight(template)
            resource = next(r for r in declaration["resources"] if r["root"] == resource_root)
            pkg = prepare_skill_package(declaration, resource)
            archive = root.parent / (pkg["name"] + ".zip")
            archive.write_bytes(skill_archive(pkg))
            _, row = await skill_imports.import_archive(archive, "tenant-a", "user-a", False, root=root)
            selections.append({"name": row.name, "scope": "personal", "resource_id": registered_resource_id(row)})
            packages[resource_root] = {
                "package": pkg,
                "host": root / "custom/tenant-a/user-a" / row.name,
                "virtual": "/mnt/skills/custom/tenant-a/user-a/" + row.name,
            }
        async with factory() as db:
            agent = await db.get(CustomAgent, agent_id)
            await save_binding(db, agent, "tenant-a", "user-a", "selected", selections, explicit=True)
            db.add(agent)
            await db.commit()
    asyncio.run(install())
    return packages


def command(facts, text):
    return tools.bash_tool.func(facts[4], "Use explicitly selected auxiliary resource", text)


def test_reference_reads_use_original_current_selection_and_reject_unselected_sources(execution_runtime):
    resource = "references/daily-learning-template.md"
    item = install_selected(execution_runtime, [("expert:clinical-learning-subscription", resource)])[resource]
    runtime = execution_runtime[4]
    expected = (item["host"] / resource).read_text().splitlines()[0]
    value = tools.read_file_tool.func(runtime, "Read selected reference", item["virtual"] + "/" + resource)
    assert expected in value
    rejected = tools.read_file_tool.func(runtime, "Reject unselected reference", "/mnt/skills/custom/tenant-a/user-a/collision/member.txt")
    assert rejected.startswith("Error:") and "AUTHORIZED PERSONAL MEMBER" not in rejected
    assert execution_runtime[3] == []


def test_clinical_stateful_cli_writes_only_owned_thread_state_and_stops_after_withdrawal(execution_runtime):
    resource = "scripts/clinical_profile.py"
    item = install_selected(execution_runtime, [("expert:clinical-learning-subscription", resource)])[resource]
    original = (item["host"] / resource).read_bytes()
    script = shlex.quote(item["virtual"] + "/host/clinical_profile.py")
    result = command(execution_runtime, "python " + script + " register --display-name Demo --region Demo --hospital Demo --department cardiology --title resident --consent-confirmed true")
    assert '"ok": true' in result and '"action": "register"' in result, result
    state = Path(execution_runtime[4].state["thread_data"]["workspace_path"]) / "octop-resources/clinical-learning-subscription/clinical_learning_state.json"
    assert json.loads(state.read_text())["profile"]["display_name"] == "Demo"
    assert not (item["host"] / "clinical_learning_state.json").exists()
    assert (item["host"] / resource).read_bytes() == original
    before = state.read_bytes()

    async def withdraw():
        async with execution_runtime[0]() as db:
            member = (await db.exec(select(TenantMembership))).scalars().one()
            member.status = "inactive"
            db.add(member)
            await db.commit()
    asyncio.run(withdraw())
    denied = command(execution_runtime, "python " + script + " get")
    assert denied.startswith("Error:") and '"display_name"' not in denied
    assert state.read_bytes() == before


def test_local_delivery_decision_simulator_runs_without_creating_real_delivery(execution_runtime):
    resource = "scripts/simulate_weixin_flow.py"
    item = install_selected(execution_runtime, [("expert:clinical-learning-subscription", resource)])[resource]
    result = command(execution_runtime, "python " + shlex.quote(item["virtual"] + "/" + resource))
    assert '"scenario"' in result and '"ok": true' in result and '"ok": false' not in result, result


def test_memory_check_reads_owned_workspace_and_reports_changes_without_modification(execution_runtime):
    resource = "scripts/check_memory_freshness.sh"
    item = install_selected(execution_runtime, [("expert:parenting-companion", resource)])[resource]
    workspace = Path(execution_runtime[4].state["thread_data"]["workspace_path"]) / "parenting-companion"
    child = workspace / "memory/child/topic.md"
    child.parent.mkdir(parents=True)
    child.write_text("Owned memory")
    index = workspace / "MEMORY.md"
    index.write_text("Owned index")
    os.utime(child, (100, 100))
    os.utime(index, (200, 200))
    invocation = "OCTOP_WORKSPACE=/mnt/user-data/workspace/parenting-companion bash " + shlex.quote(item["virtual"] + "/" + resource)
    fresh = command(execution_runtime, invocation)
    assert "All memory files in sync" in fresh, fresh
    os.utime(child, (300, 300))
    stale = command(execution_runtime, invocation)
    assert "newer than MEMORY.md" in stale, stale
    assert index.read_text() == "Owned index" and child.read_text() == "Owned memory"


def test_output_validator_requires_an_explicit_selected_policy_and_rejects_incomplete_output(execution_runtime):
    script, policy = "scripts/validate_output.py", "references/source-policy.yaml"
    packages = install_selected(execution_runtime, [("expert:clinical-learning-subscription", script), ("expert:clinical-learning-subscription", policy)])
    workspace = Path(execution_runtime[4].state["thread_data"]["workspace_path"])
    workspace.mkdir(parents=True, exist_ok=True)
    (workspace / "draft.md").write_text("# Incomplete local test output\n")
    invocation = ("python " + shlex.quote(packages[script]["virtual"] + "/" + script)
        + " --module daily_guideline_learning --policy " + shlex.quote(packages[policy]["virtual"] + "/" + policy)
        + " --text-file /mnt/user-data/workspace/draft.md")
    result = command(execution_runtime, invocation)
    assert '"ok": false' in result and '"errors"' in result, result
