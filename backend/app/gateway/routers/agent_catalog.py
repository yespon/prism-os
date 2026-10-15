"""Authenticated catalog and explicit fixed-source import through native Skill registration."""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException, Query, Request, Response
from prismos_octop.catalog import get_template, list_personas, list_templates, provenance
from prismos_octop.presentation import avatar, list_avatars, questionnaire, score_answers
from pydantic import BaseModel, ConfigDict, Field

from app.gateway.authorization import require_tenant_admin, require_tenant_context
from app.gateway.resource_authorization import CurrentResourceRoute, resource_operation_guard
from app.integrations import skill_imports
from app.integrations.octop.resource_installations import scoped_resource_preflight
from app.integrations.octop.resources import resource_preflight
from app.integrations.octop.skill_packages import SkillPackageUnavailable, prepare_skill_package, skill_archive
from deerflow.skills.installer import SkillAlreadyExistsError

router = APIRouter(prefix="/api/agent-catalog", tags=["agents"], route_class=CurrentResourceRoute)


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
async def template_resources(template_id: str, request: Request, locale: Literal["zh", "en"] = "zh", check_installation: bool = False) -> dict:
    _authorize(request)
    try:
        if check_installation:
            return await scoped_resource_preflight(template_id, locale, require_tenant_context(request), request.state.user_id)
        return resource_preflight(template_id, locale)
    except KeyError:
        raise HTTPException(status_code=404, detail="Agent template not found") from None
    except ValueError:
        raise HTTPException(status_code=503, detail="Resource source integrity unavailable") from None


@router.get("/templates/{template_id}/resources/{resource_id}/archive")
async def resource_archive(template_id: str, resource_id: str, request: Request, locale: Literal["zh", "en"] = "zh") -> Response:
    _authorize(request)
    try:
        # Only the pinned global upstream library is an archive source.
        # Installation rows/private tenant directories are never read here.
        declaration = resource_preflight(template_id, locale)
        if not declaration["template_source"]["source"].startswith("src/octop/infra/agents/experts/library/"):
            raise HTTPException(409, "Only retained upstream Skill sources can be exported")
        resource = next((r for r in declaration["resources"] if r["id"] == resource_id), None)
        if resource is None:
            raise HTTPException(404, "Resource not found")
        package = prepare_skill_package(declaration, resource)
        data = skill_archive(package)
    except KeyError:
        raise HTTPException(404, "Agent template not found") from None
    except SkillPackageUnavailable as error:
        raise HTTPException(409, str(error)) from None
    except ValueError:
        raise HTTPException(503, "Resource source integrity unavailable") from None
    return Response(data, media_type="application/zip", headers={"Content-Disposition": f'attachment; filename="{package["name"]}.zip"', "Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"})


class ResourceInstallRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scope: Literal["personal", "tenant"] = "personal"
    bundle_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


@router.post("/templates/{template_id}/resources/{resource_id}/install", status_code=201)
async def install_source_resource(template_id: str, resource_id: str, body: ResourceInstallRequest, request: Request, locale: Literal["zh", "en"] = "zh") -> dict:
    _authorize(request)
    shared = body.scope == "tenant"
    if shared:
        require_tenant_admin(request)
    try:
        declaration = resource_preflight(template_id, locale)
        if not declaration["template_source"]["source"].startswith("src/octop/infra/agents/experts/library/"):
            raise HTTPException(409, "Only retained upstream Skill sources can be installed")
        resource = next((r for r in declaration["resources"] if r["id"] == resource_id), None)
        if resource is None:
            raise HTTPException(404, "Resource not found")
        if resource["bundle_sha256"] != body.bundle_sha256:
            raise HTTPException(409, "Resource source changed; check and confirm again")
        package = prepare_skill_package(declaration, resource)
    except KeyError:
        raise HTTPException(404, "Agent template not found") from None
    except SkillPackageUnavailable as error:
        raise HTTPException(409, str(error)) from None
    except ValueError:
        raise HTTPException(503, "Resource source integrity unavailable") from None
    with tempfile.TemporaryDirectory(prefix="prismos-source-import-") as directory:
        archive = Path(directory) / "source.zip"
        archive.write_bytes(skill_archive(package))
        try:
            result, row = await skill_imports.import_archive(archive, require_tenant_context(request), request.state.user_id, shared, authorize=resource_operation_guard(request, shared))
        except SkillAlreadyExistsError:
            raise HTTPException(409, "Skill already exists; installed contents were preserved") from None
        except Exception as error:
            operation = getattr(error, "skill_operation_id", None)
            raise HTTPException(503, {"message": "Source import outcome requires reconciliation", "operation_id": operation}) from None
    return {"operation_id": result["operation_id"], "name": row.name, "scope": body.scope, "registered": True, "execution_ready": False, "permission_grants": False}
