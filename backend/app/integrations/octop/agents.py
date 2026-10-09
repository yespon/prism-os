"""Translate pinned templates into the existing CustomAgent configuration."""

from __future__ import annotations

import hashlib

from fastapi import HTTPException
from prismos_octop.catalog import get_template, provenance, render_persona


def resolve_agent_prompt(body) -> tuple[str, dict]:
    prompt = (body.system_prompt or body.soul or "").strip()
    source = {}
    if body.template_id:
        try:
            template = get_template(body.template_id, body.template_locale)
        except KeyError:
            raise HTTPException(status_code=404, detail="Agent template not found") from None
        if not prompt:
            prompt = template["system_prompt"]
        source = {
            "project": "Octop",
            "revision": template["revision"],
            "template_id": template["id"],
            "source_path": template["source_path"],
            "locale": body.template_locale,
            "template_prompt_sha256": hashlib.sha256(template["system_prompt"].encode()).hexdigest(),
            "bundled_resources_installed": False,
        }
    if body.persona_mbti:
        try:
            persona = render_persona(body.persona_mbti.upper(), body.template_locale)
        except ValueError:
            raise HTTPException(status_code=422, detail="Unknown personality type") from None
        prompt = f"{prompt}\n\n{persona}".strip()
        source.update({"project": "Octop", "revision": provenance()["revision"], "persona_mbti": body.persona_mbti.upper()})
    if source:
        source["effective_prompt_sha256"] = hashlib.sha256(prompt.encode()).hexdigest()
    return prompt, {"octop_source": source} if source else {}
