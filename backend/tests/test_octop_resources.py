"""N09 declarations cover all retained expert bytes without changing rights."""

from __future__ import annotations

import asyncio
import hashlib
import json
import shutil

import pytest
from prismos_octop import catalog
from prismos_octop.resources import resource_declaration
from sqlalchemy import select
from test_octop_integration import catalog_client as existing_catalog_client

from app.integrations.octop.resources import resource_preflight
from app.models.agents import CustomAgent

EXPERTS = [t["id"] for t in catalog.list_templates("zh", "expert")]


@pytest.fixture
def catalog_client():
    yield from existing_catalog_client.__wrapped__()


@pytest.mark.parametrize("template_id", EXPERTS)
def test_all_expert_resource_declarations_cover_retained_members_and_languages(template_id):
    zh = resource_declaration(template_id)
    en = resource_declaration(template_id, "en")
    assert zh["declaration_sha256"] == en["declaration_sha256"]
    assert zh["resources"] == en["resources"]
    assert zh["source_verified"] and not zh["execution_ready"] and not zh["installation_checked"]
    base = (catalog.ROOT / zh["template_source"]["target"]).parent
    members = [m for r in zh["resources"] for m in r["members"]]
    assert len(members) == len({m["path"] for m in members}) == zh["member_count"]
    all_members = members + zh["template_members"]
    actual = {p.relative_to(base).as_posix() for p in base.rglob("*") if p.is_file() and p.suffix != ".pyc"}
    assert {m["path"] for m in all_members} == actual
    assert zh["verified_source_member_count"] == len(actual)
    for member in all_members:
        assert hashlib.sha256((base / member["path"]).read_bytes()).hexdigest() == member["sha256"]
    for resource in zh["resources"]:
        expected = [{key: member[key] for key in ("path", "sha256")} for member in resource["members"]]
        expected_digest = hashlib.sha256(json.dumps(expected, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()
        assert resource["bundle_sha256"] == expected_digest


def test_auxiliary_references_knowledge_and_seed_profiles_are_retained():
    all_declarations = [resource_declaration(template_id) for template_id in EXPERTS]
    assert sum(d["verified_source_member_count"] for d in all_declarations) == 352
    assert sum(d["member_count"] for d in all_declarations) == 297
    assert sum(d["additional_member_count"] for d in all_declarations) == 27
    clinical = resource_declaration("expert:clinical-learning-subscription")
    files = {m["path"] for r in clinical["resources"] for m in r["members"]}
    assert {"USER.md", "references/source-policy.yaml", "references/cron-presets.json"} <= files
    knowledge = resource_declaration("expert:karpathy-knowledge-base")
    files = {m["path"] for r in knowledge["resources"] for m in r["members"]}
    assert {"MEMORY.md", "knowledge-base/wiki/index.md"} <= files


def test_office_exclusions_remain_functional_gaps_and_cannot_enter_resources():
    declaration = resource_preflight("expert:office-automation")
    assert declaration["excluded_resources"] == ["skills/docx", "skills/pdf", "skills/pptx", "skills/xlsx"]
    assert not declaration["execution_ready"]
    for resource in declaration["resources"]:
        assert not any(m["path"].startswith(tuple(declaration["excluded_resources"])) for m in resource["members"])


def test_native_format_success_and_failure_are_not_installation_or_execution():
    healthy = resource_preflight("expert:cvm-ai-doctor")
    assert next(r for r in healthy["resources"] if r["kind"] == "skill_bundle")["host_format"]["status"] == "compatible"
    incompatible = resource_preflight("expert:cvm-cluster-doctor")
    assert next(r for r in incompatible["resources"] if r["kind"] == "skill_bundle")["host_format"]["status"] == "needs_adapter"
    assert next(r for r in incompatible["resources"] if r["kind"] == "skill_bundle")["host_format"]["detail"]
    for declaration in (healthy, incompatible):
        assert not any(declaration[key] for key in ("execution_ready", "permission_grants", "installation_checked", "runtime_dependencies_checked"))
        assert all(r["installation_status"] == "not_checked" and r["remaining_checks"] for r in declaration["resources"])


def test_subagent_source_is_fixed_without_inventing_resources():
    for locale in ("zh", "en"):
        template = catalog.list_templates(locale, "subagent")[0]
        declaration = resource_declaration(template["id"], locale)
        assert declaration["template_source"]["source"] == template["source_path"]
        assert declaration["resources"] == [] and declaration["member_count"] == 0
        assert declaration["verified_source_member_count"] == len(declaration["template_members"]) == 1


@pytest.fixture
def source_stage(tmp_path, monkeypatch):
    root = tmp_path / "package"
    shutil.copytree(catalog.ROOT, root, ignore=shutil.ignore_patterns("__pycache__"))
    monkeypatch.setattr(catalog, "ROOT", root)
    monkeypatch.setattr(catalog, "DATA", root / "data")
    catalog.provenance.cache_clear()
    catalog._templates.cache_clear()
    try:
        yield root
    finally:
        catalog.provenance.cache_clear()
        catalog._templates.cache_clear()


@pytest.mark.parametrize("mutation", ["changed", "unexpected", "symlink"])
def test_warm_catalog_cannot_bless_changed_or_aliased_resource_bytes(source_stage, mutation):
    declaration = resource_declaration("expert:cvm-ai-doctor")
    folder = (source_stage / declaration["template_source"]["target"]).parent
    file = folder / declaration["resources"][0]["members"][0]["path"]
    if mutation == "changed":
        file.write_text("changed after catalog validation")
    elif mutation == "unexpected":
        (folder / "unreviewed.md").write_text("unreviewed")
    else:
        copy = file.read_bytes()
        outside = source_stage.parent / "outside"
        outside.write_bytes(copy)
        file.unlink()
        file.symlink_to(outside)
    with pytest.raises(ValueError, match="Resource source"):
        resource_declaration("expert:cvm-ai-doctor")


def test_readonly_api_requires_identity_and_tenant_and_rejects_unknown_input(catalog_client):
    client, _ = catalog_client
    url = "/api/agent-catalog/templates/expert:cvm-ai-doctor/resources"
    assert client.get(url, headers={"x-user-id": ""}).status_code == 401
    assert client.get(url, headers={"x-tenant-id": ""}).status_code == 400
    assert client.get(url + "?locale=invalid").status_code == 422
    assert client.get("/api/agent-catalog/templates/expert:missing/resources").status_code == 404
    assert client.get("/api/agent-catalog/templates/expert:..%2Fcvm-ai-doctor/resources").status_code == 404
    assert client.get(url).status_code == 200
    assert client.post(url, json={"install": True}).status_code == 405


def test_preflight_never_updates_agent_resource_installation(catalog_client):
    client, factory = catalog_client
    created = client.post("/api/agents", json={"name": "resource-draft", "template_id": "expert:cvm-ai-doctor"})
    assert created.status_code == 201
    for _ in range(2):
        result = client.get("/api/agent-catalog/templates/expert:cvm-ai-doctor/resources")
        assert result.status_code == 200 and not result.json()["permission_grants"]
    reloaded = client.get("/api/agents/resource-draft").json()
    assert reloaded["presentation"]["bundled_resources_installed"] is False
    assert reloaded["skills"] == [] and reloaded["tool_groups"] == []

    async def count():
        async with factory() as session:
            rows = await session.exec(select(CustomAgent))
            return len(rows.scalars().all())

    assert asyncio.run(count()) == 1
