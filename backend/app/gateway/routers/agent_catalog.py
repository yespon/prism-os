"""Authenticated read-only catalog; creation goes through the existing Agent API."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException, Query, Request, Response
from prismos_octop.catalog import get_template, list_personas, list_templates, provenance
from prismos_octop.presentation import avatar, list_avatars, questionnaire, score_answers
from pydantic import BaseModel, Field

from app.gateway.authorization import require_tenant_context
from app.integrations.octop.resources import resource_preflight

router = APIRouter(prefix="/api/agent-catalog", tags=["agents"])


def _authorize(request: Request) -> None:
    if not getattr(request.state, "user_id", None):
        raise HTTPException(status_code=401, detail="Authentication required")
    require_tenant_context(request)


@router.get("/templates")
async def templates(request: Request, locale: Literal["zh", "en"] = "zh", kind: Literal["expert", "subagent"] | None = None) -> dict:
    _authorize(request)
    return {"templates": list_templates(locale, kind)}


@router.get("/templates/{template_id}")
async def template(template_id: str, request: Request, locale: Literal["zh", "en"] = "zh") -> dict:
    _authorize(request)
    try:
        return get_template(template_id, locale)
    except KeyError:
        raise HTTPException(status_code=404, detail="Agent template not found") from None


@router.get("/personas")
async def personas(request: Request) -> dict:
    _authorize(request)
    return {"personas": list_personas()}


@router.get("/status")
async def status(request: Request, locale: Literal["zh", "en"] = Query("zh")) -> dict:
    _authorize(request)
    origin = provenance()
    return {
        "release": origin["release"],
        "revision": origin["revision"],
        "templates": len(list_templates(locale)),
        "personas": len(list_personas()),
        "integrity_verified": True,
        "mode": "prompt_templates",
        "automatic_resource_installation": False,
    }


class PersonalityAnswers(BaseModel):
    answers: dict[str, Literal["A", "B", "a", "b"]] = Field(min_length=20, max_length=28)


@router.get("/personality-test")
async def personality_test(request: Request, locale: Literal["zh", "en"] = "zh") -> dict:
    _authorize(request)
    return {"questions": questionnaire(locale), "minimum_answers": 20, "revision": provenance()["revision"]}


@router.post("/personality-test")
async def personality_result(request: Request, body: PersonalityAnswers) -> dict:
    _authorize(request)
    try:
        return score_answers(body.answers)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from None


@router.get("/avatars")
async def avatars(request: Request) -> dict:
    _authorize(request)
    return {"avatars": list_avatars()}


@router.get("/avatars/{avatar_id}")
async def avatar_image(request: Request, avatar_id: str) -> Response:
    _authorize(request)
    try:
        data, digest = avatar(avatar_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Avatar not found") from None
    return Response(
        data, media_type="image/svg+xml", headers={"ETag": '"' + digest + '"', "Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff", "Content-Security-Policy": "default-src 'none'; style-src 'none'; sandbox"}
    )


@router.get("/templates/{template_id}/resources")
async def template_resources(template_id: str, request: Request, locale: Literal["zh", "en"] = "zh") -> dict:
    _authorize(request)
    try:
        return resource_preflight(template_id, locale)
    except KeyError:
        raise HTTPException(status_code=404, detail="Agent template not found") from None
    except ValueError:
        raise HTTPException(status_code=503, detail="Resource source integrity unavailable") from None
