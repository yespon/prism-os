"""Translate pinned content through existing CustomAgent ownership and persistence."""

from __future__ import annotations

import hashlib
from typing import Literal

from fastapi import HTTPException
from prismos_octop.catalog import get_template, provenance, render_persona
from prismos_octop.presentation import avatar
from pydantic import BaseModel, Field


class AgentQuickPrompt(BaseModel):
    title: str = Field(min_length=1, max_length=100)
    prompt: str = Field(min_length=1, max_length=4000)
    description: str = Field(default="", max_length=300)


class AgentPresentation(BaseModel):
    quick_prompts: list[AgentQuickPrompt] = Field(default_factory=list, max_length=32)
    welcome_message: str = Field(default="", max_length=2000)
    avatar_id: str | None = Field(default=None, max_length=100)
    template_locale: Literal["zh", "en"] = "zh"
    persona_mbti: str | None = Field(default=None, max_length=4)
    template_id: str | None = None
    bundled_resources_installed: bool = False
    excluded_resources: list[str] = Field(default_factory=list)


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _persona(code: str | None, locale: str) -> str:
    if not code:
        return ""
    try:
        return render_persona(code.upper(), locale)
    except ValueError:
        raise HTTPException(status_code=422, detail="Unknown personality type") from None


def _validate_avatar(value: str | None) -> None:
    if value:
        try:
            avatar(value)
        except ValueError:
            raise HTTPException(status_code=422, detail="Unknown avatar") from None


def agent_content(agent) -> tuple[str, AgentPresentation]:
    """Only expose typed presentation fields; recover legacy appended personas safely."""
    meta = agent.meta_info or {}
    source = meta.get("octop_source", {})
    stored = meta.get("agent_presentation", {})
    locale = stored.get("template_locale", source.get("locale", "zh"))
    code = stored.get("persona_mbti", source.get("persona_mbti"))
    prompt = agent.system_prompt or ""
    base = prompt
    if stored and source.get("effective_prompt_sha256") == _hash(prompt):
        base = stored.get("base_prompt", prompt)
    elif code and source.get("effective_prompt_sha256") == _hash(prompt):
        rendered = _persona(code, locale)
        if prompt.endswith(rendered):
            base = prompt[: -len(rendered)].rstrip()
        else:
            code = None
    else:
        code = None
    return base, AgentPresentation(
        welcome_message=stored.get("welcome_message", ""),
        quick_prompts=stored.get("quick_prompts", []),
        avatar_id=stored.get("avatar_id"),
        template_locale=locale,
        persona_mbti=code,
        template_id=source.get("template_id"),
        # Presentation never claims that companion tools have been installed.
        excluded_resources=source.get("excluded_resources", []),
    )


def resolve_agent_prompt(body) -> tuple[str, dict]:
    base = (body.system_prompt or body.soul or "").strip()
    source, defaults = {}, {}
    if body.template_id:
        try:
            template = get_template(body.template_id, body.template_locale)
        except KeyError:
            raise HTTPException(status_code=404, detail="Agent template not found") from None
        base = base or template["system_prompt"]
        defaults = template
        source = {
            "project": "Octop",
            "revision": template["revision"],
            "template_id": template["id"],
            "source_path": template["source_path"],
            "locale": body.template_locale,
            "template_prompt_sha256": _hash(template["system_prompt"]),
            "bundled_resources_installed": False,
            "excluded_resources": template.get("excluded_resources", []),
        }
    code = body.persona_mbti.upper() if body.persona_mbti else None
    rendered = _persona(code, body.template_locale)
    prompt = (base + "\n\n" + rendered).strip() if rendered else base
    if code:
        source.update({"project": "Octop", "persona_mbti": code, "persona_revision": provenance()["revision"]})
        source.setdefault("revision", provenance()["revision"])
    if source:
        source["effective_prompt_sha256"] = _hash(prompt)
    avatar_id = body.avatar_id if "avatar_id" in body.model_fields_set else defaults.get("avatar_id")
    welcome = body.welcome_message if "welcome_message" in body.model_fields_set else defaults.get("welcome_message", "")
    _validate_avatar(avatar_id)
    quick_prompts = [item.model_dump() for item in body.quick_prompts] if "quick_prompts" in body.model_fields_set else defaults.get("quick_prompts", [])
    # Manual agents also use the existing metadata column; no schema/lifecycle change.
    return prompt, {
        "octop_source": source,
        "agent_presentation": {"base_prompt": base, "template_locale": body.template_locale, "persona_mbti": code, "avatar_id": avatar_id, "welcome_message": welcome or "", "quick_prompts": quick_prompts},
    }


def update_agent_content(agent, body) -> None:
    fields = body.model_fields_set
    relevant = {"system_prompt", "soul", "persona_mbti", "template_locale", "avatar_id", "welcome_message", "quick_prompts"}
    if not fields & relevant:
        return
    base, presentation = agent_content(agent)
    if body.system_prompt is not None or body.soul is not None:
        incoming = (body.system_prompt if body.system_prompt is not None else body.soul).strip()
        if not incoming:
            raise HTTPException(status_code=422, detail="system_prompt must not be empty or whitespace-only")
        # Old clients round-trip effective prompts. Keep the existing base in this case.
        if incoming != agent.system_prompt:
            base = incoming
    locale = body.template_locale or presentation.template_locale
    code = body.persona_mbti.upper() if body.persona_mbti else None
    if "persona_mbti" not in fields:
        code = presentation.persona_mbti
    rendered = _persona(code, locale)
    prompt = (base + "\n\n" + rendered).strip() if rendered else base
    if not prompt:
        raise HTTPException(status_code=422, detail="system_prompt must not be empty")
    avatar_id = body.avatar_id if "avatar_id" in fields else presentation.avatar_id
    welcome = body.welcome_message if "welcome_message" in fields else presentation.welcome_message
    _validate_avatar(avatar_id)
    quick_prompts = [item.model_dump() for item in body.quick_prompts or []] if "quick_prompts" in fields else [item.model_dump() for item in presentation.quick_prompts]
    meta = dict(agent.meta_info or {})
    source = dict(meta.get("octop_source", {}))
    source.update({"effective_prompt_sha256": _hash(prompt), "persona_mbti": code, "locale": locale})
    if code:
        source["persona_revision"] = provenance()["revision"]
    meta["octop_source"] = source
    meta["agent_presentation"] = {"base_prompt": base, "template_locale": locale, "persona_mbti": code, "avatar_id": avatar_id, "welcome_message": welcome or "", "quick_prompts": quick_prompts}
    agent.system_prompt, agent.meta_info = prompt, meta
