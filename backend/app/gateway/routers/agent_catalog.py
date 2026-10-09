"""Authenticated read-only catalog; creation goes through the existing Agent API."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException, Query, Request
from prismos_octop.catalog import get_template, list_personas, list_templates, provenance

from app.gateway.authorization import require_tenant_context

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
