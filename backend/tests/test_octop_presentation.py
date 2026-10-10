"""N06: pinned presentation, real persistence and unchanged host authorization."""

from __future__ import annotations

import ast
import asyncio
import hashlib
import json
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import HTTPException
from prismos_octop.catalog import DATA, get_template, list_personas, render_persona
from prismos_octop.presentation import _questions, avatar, list_avatars, questionnaire, score_answers
from sqlalchemy import select
from test_octop_integration import catalog_client as existing_catalog_client

from app.models.agents import CustomAgent


@pytest.fixture
def catalog_client():
    yield from existing_catalog_client.__wrapped__()


def reference_score(answers):
    # Execute only the pinned pure scoring function in a bounded test namespace.
    tree = ast.parse((DATA / "personality/mbti-source.py.txt").read_text())
    function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "_score_answers")
    namespace = {"Any": Any, "HTTPException": HTTPException, "_QUESTIONS": [SimpleNamespace(**q) for q in _questions()]}
    exec(compile(ast.Module(body=[function], type_ignores=[]), "pinned-score-test", "exec"), namespace)
    return namespace["_score_answers"](answers)


@pytest.mark.parametrize("code", [entry["code"] for entry in list_personas()])
def test_all_personality_results_preserve_upstream_score(code):
    answers = {str(q["id"]): "A" if q["a_pole"] in code else "B" for q in _questions()}
    result = score_answers(answers)
    expected, dimensions = reference_score(answers)
    assert result["code"] == expected == code
    assert result["dimensions"] == {key: list(value) for key, value in dimensions.items()}
    assert result["automatic_apply"] is False


def test_localized_questions_and_partial_score_match_source():
    for locale in ("zh", "en"):
        questions = questionnaire(locale)
        assert len(questions) == 28
        for item, source in zip(questions, _questions(), strict=True):
            assert item["question"] == source[f"question_{locale}"]
            assert item["option_a"] == source[f"option_a_{locale}"]
    # Minimum 20, missing dimension and ties keep the pinned behavior.
    for answers in ({str(i): "B" for i in range(1, 21)}, {str(i): "A" if i % 2 else "B" for i in range(1, 29)}):
        expected, dimensions = reference_score(answers)
        assert score_answers(answers)["code"] == expected
        assert score_answers(answers)["dimensions"] == {key: list(value) for key, value in dimensions.items()}


@pytest.mark.parametrize("answers", [{}, {str(i): "A" for i in range(1, 20)}, {str(i): "A" for i in range(1, 30)}, {str(i): "X" for i in range(1, 29)}, {str(i): "A" for i in range(2, 30)}])
def test_questionnaire_rejects_incomplete_or_invalid_input(catalog_client, answers):
    client, _ = catalog_client
    assert client.post("/api/agent-catalog/personality-test", json={"answers": answers}).status_code == 422


@pytest.mark.parametrize("path,method", [("personality-test", "get"), ("personality-test", "post"), ("avatars", "get"), ("avatars/personas:INTJ", "get")])
def test_presentation_catalog_requires_identity_and_tenant(catalog_client, path, method):
    client, _ = catalog_client
    body = {"json": {"answers": {str(i): "A" for i in range(1, 29)}}} if method == "post" else {}
    for headers, status in [({"x-user-id": ""}, 401), ({"x-tenant-id": ""}, 400)]:
        assert getattr(client, method)("/api/agent-catalog/" + path, headers=headers, **body).status_code == status


def test_all_52_avatars_are_exact_authenticated_source_bytes(catalog_client):
    client, _ = catalog_client
    origin = json.loads((DATA / "provenance.json").read_text())
    assert len(list_avatars()) == 52
    assert len([entry for entry in list_avatars() if entry["kind"] == "personas"]) == 16
    for entry in list_avatars():
        kind, name = entry["id"].split(":")
        path = f"data/avatars/{kind}/{name}.svg"
        receipt = next(item for item in origin["imports"] if item["target"] == path)
        data, digest = avatar(entry["id"])
        assert digest == receipt["sha256"] == hashlib.sha256(data).hexdigest()
        response = client.get("/api/agent-catalog/avatars/" + entry["id"])
        assert response.status_code == 200 and response.content == data
        assert response.headers["content-type"] == "image/svg+xml"
        assert response.headers["x-content-type-options"] == "nosniff"
        assert "sandbox" in response.headers["content-security-policy"]
        assert "no-store" in response.headers["cache-control"]
    assert client.get("/api/agent-catalog/avatars/personas:missing").status_code == 404
    assert client.get("/api/agent-catalog/avatars/..%2Fprovenance.json").status_code == 404


def test_create_edit_reopen_persona_welcome_avatar_no_duplicate_prompt(catalog_client):
    client, factory = catalog_client
    base = "Edited expert instructions"
    created = client.post(
        "/api/agents", json={"name": "n06-expert", "template_id": "expert:general-assistant", "template_locale": "en", "system_prompt": base, "persona_mbti": "INTJ", "welcome_message": "Hello\nworld", "avatar_id": "personas:INTJ"}
    )
    assert created.status_code == 201
    value = created.json()
    assert value["base_system_prompt"] == base
    assert value["presentation"]["welcome_message"] == "Hello\nworld"
    assert value["presentation"]["avatar_id"] == "personas:INTJ"
    assert value["system_prompt"] == base + "\n\n" + render_persona("INTJ", "en")
    for _ in range(3):
        response = client.put("/api/agents/n06-expert", json={"system_prompt": base, "persona_mbti": "ENFP", "template_locale": "zh", "welcome_message": "欢迎回来", "avatar_id": "experts:general-assistant"})
        assert response.status_code == 200
    reopened = client.get("/api/agents/n06-expert").json()
    assert reopened["base_system_prompt"] == base
    assert reopened["system_prompt"] == base + "\n\n" + render_persona("ENFP", "zh")
    assert reopened["presentation"]["persona_mbti"] == "ENFP"
    assert reopened["presentation"]["template_id"] == "expert:general-assistant"
    assert reopened["presentation"]["welcome_message"] == "欢迎回来"
    assert reopened["skills"] == [] and reopened["tool_groups"] == []
    # Existing clients send the effective prompt; this must not append twice.
    assert client.put("/api/agents/n06-expert", json={"system_prompt": reopened["system_prompt"]}).json()["system_prompt"] == reopened["system_prompt"]
    cleared = client.put("/api/agents/n06-expert", json={"persona_mbti": None, "avatar_id": None, "welcome_message": ""}).json()
    assert cleared["system_prompt"] == base and cleared["presentation"]["avatar_id"] is None
    assert cleared["presentation"]["welcome_message"] == ""
    assert "meta_info" not in cleared and "octop_source" not in cleared

    async def check_saved():
        async with factory() as session:
            row = (await session.exec(select(CustomAgent).where(CustomAgent.name == "n06-expert"))).scalars().one()
            assert row.meta_info["octop_source"]["effective_prompt_sha256"] == hashlib.sha256(base.encode()).hexdigest()
            assert row.meta_info["octop_source"]["bundled_resources_installed"] is False

    asyncio.run(check_saved())


def test_default_localized_welcome_and_resources_are_not_installed(catalog_client):
    client, _ = catalog_client
    for locale in ("zh", "en"):
        value = client.post("/api/agents", json={"name": "default-" + locale, "template_id": "expert:general-assistant", "template_locale": locale}).json()
        template = get_template("expert:general-assistant", locale)
        assert value["presentation"]["welcome_message"] == template["welcome_message"]
        assert value["presentation"]["avatar_id"] == "experts:general-assistant"
        assert value["presentation"]["bundled_resources_installed"] is False
    office = client.post("/api/agents", json={"name": "office", "template_id": "expert:office-automation"}).json()
    assert office["presentation"]["excluded_resources"] == ["skills/docx", "skills/pdf", "skills/pptx", "skills/xlsx"]
    assert office["skills"] == [] and office["tool_groups"] == []


@pytest.mark.parametrize("changes", [{"avatar_id": "https://example.test/x.svg"}, {"avatar_id": "experts:../../private"}, {"persona_mbti": "ZZZZ"}, {"welcome_message": "a" * 2001}])
def test_invalid_presentation_cannot_mutate_existing_agent(catalog_client, changes):
    client, _ = catalog_client
    assert client.post("/api/agents", json={"name": "valid", "system_prompt": "original"}).status_code == 201
    assert client.put("/api/agents/valid", json={"description": "must roll back", **changes}).status_code == 422
    value = client.get("/api/agents/valid").json()
    assert value["system_prompt"] == "original" and value["description"] == ""
    assert client.post("/api/agents", json={"name": "invalid", "system_prompt": "original", **changes}).status_code == 422


def test_presentation_edits_keep_existing_ownership_and_shared_permissions(catalog_client):
    client, _ = catalog_client
    client.post("/api/agents", json={"name": "owned", "system_prompt": "private"})
    for headers in ({"x-user-id": "user-b"}, {"x-tenant-id": "tenant-b"}):
        assert client.put("/api/agents/owned", json={"welcome_message": "forbidden"}, headers=headers).status_code == 404
    assert client.put("/api/agents/owned", json={"welcome_message": "allowed"}).status_code == 200
    admin = {"x-tenant-role": "tenant_admin"}
    assert client.post("/api/agents", json={"name": "shared", "system_prompt": "shared", "is_shared": True}, headers=admin).status_code == 201
    assert client.put("/api/agents/shared", json={"welcome_message": "forbidden"}).status_code == 404
    assert client.put("/api/agents/shared", json={"welcome_message": "allowed"}, headers=admin).status_code == 200


def test_legacy_persona_is_editable_without_exposing_other_metadata(catalog_client):
    client, factory = catalog_client
    client.post("/api/agents", json={"name": "legacy", "system_prompt": "base", "persona_mbti": "INTJ"})

    async def make_legacy():
        async with factory() as session:
            row = (await session.exec(select(CustomAgent).where(CustomAgent.name == "legacy"))).scalars().one()
            meta = dict(row.meta_info)
            meta.pop("agent_presentation")
            meta["internal_only"] = "must not be projected"
            row.meta_info = meta
            session.add(row)
            await session.commit()

    asyncio.run(make_legacy())
    value = client.get("/api/agents/legacy").json()
    assert value["base_system_prompt"] == "base" and value["presentation"]["persona_mbti"] == "INTJ"
    assert "must not be projected" not in str(value)
    assert client.put("/api/agents/legacy", json={"persona_mbti": None}).json()["system_prompt"] == "base"


def test_quick_prompts_are_localized_persisted_and_bounded(catalog_client):
    client, _ = catalog_client
    for locale in ("zh", "en"):
        template = get_template("expert:general-assistant", locale)
        response = client.post("/api/agents", json={"name": "starters-" + locale, "template_id": template["id"], "template_locale": locale})
        assert response.status_code == 201
        assert response.json()["presentation"]["quick_prompts"] == template["quick_prompts"]
        assert template["quick_prompts"]
    prompts = [{"title": "Custom question", "description": "Draft only", "prompt": "Please inspect this"}]
    assert client.put("/api/agents/starters-zh", json={"quick_prompts": prompts}).status_code == 200
    assert client.get("/api/agents/starters-zh").json()["presentation"]["quick_prompts"] == prompts
    for bad in ([{"title": "", "prompt": "x"}], [{"title": "x", "prompt": "x"}] * 33, [{"title": "x", "prompt": "x" * 4001}]):
        assert client.put("/api/agents/starters-zh", json={"quick_prompts": bad}).status_code == 422
        assert client.get("/api/agents/starters-zh").json()["presentation"]["quick_prompts"] == prompts
    assert client.put("/api/agents/starters-zh", json={"quick_prompts": None}).json()["presentation"]["quick_prompts"] == []


@pytest.mark.parametrize("locale", ["zh", "en"])
def test_all_experts_have_bounded_valid_presentation_defaults(locale):
    from prismos_octop.catalog import list_templates

    from app.integrations.octop.agents import AgentPresentation

    for template in list_templates(locale, "expert"):
        value = AgentPresentation(welcome_message=template["welcome_message"], quick_prompts=template["quick_prompts"], avatar_id=template["avatar_id"])
        assert value.welcome_message
        assert value.avatar_id in {entry["id"] for entry in list_avatars()}


@pytest.mark.parametrize(
    "content", ["<script>alert(1)</script>", "<foreignObject />", '<path onload="alert(1)" />', '<use href="https://example.test/x.svg" />', '<path style="fill:red" />', '<path fill="url(https://example.test/x.svg)" />']
)
def test_avatar_candidate_rejects_active_or_external_content(tmp_path, monkeypatch, content):
    import prismos_octop.presentation as presentation

    (tmp_path / "avatars/personas").mkdir(parents=True)
    (tmp_path / "avatars/personas/INTJ.svg").write_text('<svg xmlns="http://www.w3.org/2000/svg">' + content + "</svg>")
    monkeypatch.setattr(presentation, "DATA", tmp_path)
    monkeypatch.setattr(presentation, "provenance", lambda: {})
    presentation._avatars.cache_clear()
    try:
        with pytest.raises(ValueError, match="Active avatar|Unsupported avatar"):
            presentation.list_avatars()
    finally:
        presentation._avatars.cache_clear()
