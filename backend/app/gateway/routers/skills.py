import hashlib
import logging
import re
import tempfile
import zipfile
from pathlib import Path
from typing import Literal

import yaml
from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from pydantic import BaseModel, Field

from app.gateway.authorization import require_tenant_admin, require_tenant_context
from app.gateway.path_utils import resolve_thread_virtual_path
from app.gateway.resource_authorization import CurrentResourceRoute, resource_operation_guard
from app.integrations import skill_deletions, skill_imports, skill_mutations
from deerflow.database.user_config_service import (
    get_available_skills,
    get_tenant_shared_skill_settings,
    initialize_owned_skill_configuration,
    list_tenant_shared_skills,
)
from deerflow.sandbox.file_access import read_owned_file
from deerflow.skills import (
    Skill,
    get_skills_root_path,
    load_skills,  # noqa: F401 - compatibility export; HTTP paths use current native facts
)
from deerflow.skills.installer import SkillAlreadyExistsError
from deerflow.skills.resource_identity import registered_resource_id, resource_directory

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["skills"], route_class=CurrentResourceRoute)
_SKILL_NAME_PATTERN = re.compile(r"^[a-z0-9-]+$")


class SkillResponse(BaseModel):
    """Response model for skill information."""

    name: str = Field(..., description="Name of the skill")
    description: str = Field(..., description="Description of what the skill does")
    license: str | None = Field(None, description="License information")
    category: str = Field(..., description="Category of the skill (public or custom)")
    enabled: bool = Field(default=True, description="Whether this skill is enabled")
    bound_tools: list[str] = Field(default_factory=list, description="Bound tool names")
    prompt_template: str | None = Field(None, description="Prompt template for this skill")
    strategy: str | None = Field(None, description="Execution strategy for this skill")
    instructions: str | None = Field(None, description="Skill instructions from SKILL.md body")
    created_by: str | None = Field(None, description="User ID who created the skill")
    version: int = Field(default=1, description="Skill version number")
    changelog: str | None = Field(None, description="Latest change description")
    usage_count: int = Field(default=0, description="Number of times this skill has been used")
    references: dict[str, str] | None = Field(None, description="Reference documents loaded on demand (Tier 3)")


class SkillsListResponse(BaseModel):
    """Response model for listing all skills."""

    skills: list[SkillResponse]


class AvailableSkillResponse(SkillResponse):
    file_sha256: str | None = None
    resource_id: str | None = None
    owner_kind: str | None = None
    files_status: str | None = None
    scope: str = Field(..., description="Resource scope: global or tenant")
    source: str = Field(..., description="Skill source classification")
    managed_by_current_user: bool = Field(..., description="Whether current user can manage this skill")
    effective_permissions: list[str] = Field(default_factory=list, description="Effective permissions for current user")


class AvailableSkillsListResponse(BaseModel):
    skills: list[AvailableSkillResponse]


class SkillUpdateRequest(BaseModel):
    """Request model for updating a skill."""

    expected_resource_id: str | None = Field(default=None, max_length=128)
    enabled: bool = Field(..., description="Whether to enable or disable the skill")


class TenantSkillCreateRequest(BaseModel):
    name: str = Field(..., description="Skill name")
    description: str = Field(..., description="Skill description")
    instructions: str | None = Field(default=None, description="Skill instructions")
    enabled: bool = Field(default=True, description="Whether skill is enabled")
    category: str | None = Field(default=None, description="Skill category")
    bound_tools: list[str] | None = Field(default=None, description="Bound tools")
    prompt_template: str | None = Field(default=None, description="Prompt template")
    strategy: str | None = Field(default=None, description="Execution strategy")
    changelog: str | None = Field(default=None, description="Change description")


class TenantSkillPatchRequest(BaseModel):
    expected_file_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    expected_resource_id: str | None = Field(default=None, max_length=128)
    description: str | None = Field(default=None, description="Skill description")
    instructions: str | None = Field(default=None, description="Skill instructions")
    enabled: bool | None = Field(default=None, description="Whether skill is enabled")
    category: str | None = Field(default=None, description="Skill category")
    bound_tools: list[str] | None = Field(default=None, description="Bound tools")
    prompt_template: str | None = Field(default=None, description="Prompt template")
    strategy: str | None = Field(default=None, description="Execution strategy")
    changelog: str | None = Field(default=None, description="Change description")


class GenerateInstructionsRequest(BaseModel):
    """Request model for AI-generated instructions."""
    prompt: str = Field(..., description="Natural language description of desired skill behavior")
    model_name: str | None = Field(None, description="Optional model name to use for generation")


class GenerateInstructionsResponse(BaseModel):
    """Response with AI-generated instructions."""
    instructions: str = Field(..., description="Generated instructions text")


class SkillDetailResponse(SkillResponse):
    file_sha256: str | None = None
    resource_id: str | None = None
    owner_kind: str | None = None
    files_status: str | None = None
    """Extended response for skill detail view."""
    references: dict[str, str] | None = Field(None, description="Reference documents (Tier 3)")
    scope: str = Field(..., description="Scope of the skill (global, tenant, personal)")
    managed_by_current_user: bool = Field(..., description="Whether current user can manage this skill")


class SkillCreationResponse(SkillDetailResponse):
    operation_id: str
    recovery_available: bool = True
    configuration_phase: str = "confirmed"


class ToolCallSummary(BaseModel):
    tool: str = Field(..., description="Tool name")
    description: str = Field(default="", description="Brief description of what the tool did")


class SummarizeDiagnosisRequest(BaseModel):
    """Request model for summarizing diagnosis into structured skill instructions."""

    incident_title: str | None = Field(None, description="Alert title")
    incident_service: str | None = Field(None, description="Affected service")
    incident_severity: str = Field(default="warning", description="Severity level")
    incident_environment: str | None = Field(None, description="Environment (production/staging)")
    diagnosis_result: str = Field(..., min_length=1, description="Full diagnosis conclusion text")
    diagnosis_steps: list[str] = Field(default_factory=list, description="SOP step labels executed during diagnosis")
    tool_calls_summary: list[ToolCallSummary] = Field(default_factory=list, description="Tools used during diagnosis")
    user_notes: str | None = Field(None, description="Optional user notes to guide refinement")


class SummarizeDiagnosisResponse(BaseModel):
    """Response with AI-refined skill instructions from diagnosis."""

    suggested_name: str = Field(..., description="Suggested skill name")
    suggested_description: str = Field(..., description="Suggested skill description")
    instructions: str = Field(..., description="Refined structured SOP instructions in Markdown")
    suggested_tools: list[str] = Field(default_factory=list, description="Suggested bound tools")
    suggested_category: str = Field(default="custom", description="Suggested skill category")


def _is_platform_admin(request: Request) -> bool:
    role = getattr(request.state, "user_role", None)
    return isinstance(role, str) and role.lower() in {"platform_admin", "admin"}


def _is_tenant_admin(request: Request) -> bool:
    role = getattr(request.state, "tenant_role", None)
    return isinstance(role, str) and role.lower() == "tenant_admin"


class SkillInstallRequest(BaseModel):
    """Request model for installing a skill from a .skill or .zip file."""

    thread_id: str = Field(..., description="The thread ID where the archive file is located")
    path: str = Field(..., description="Virtual path to the .skill or .zip file (e.g., mnt/user-data/outputs/my-skill.skill)")


class SkillInstallResponse(BaseModel):
    """Response model for skill installation."""

    success: bool = Field(..., description="Whether the installation was successful")
    skill_name: str = Field(..., description="Name of the installed skill")
    message: str = Field(..., description="Installation result message")
    operation_id: str | None = Field(default=None, description="Owned Skill import operation for reconciliation")


def _skill_to_response(skill: Skill) -> SkillResponse:
    """Convert a Skill object to a SkillResponse."""
    frontmatter, instructions = _read_skill_file_payload(skill.skill_dir)
    return SkillResponse(
        name=skill.name,
        description=skill.description,
        license=skill.license,
        category=skill.category,
        enabled=skill.enabled,
        bound_tools=[],
        prompt_template=None,
        strategy=None,
        instructions=instructions,
        created_by=frontmatter.get("created_by"),
        version=int(frontmatter.get("version", 1)),
        changelog=frontmatter.get("changelog"),
        usage_count=int(frontmatter.get("usage_count", 0)),
        references=frontmatter.get("references"),
    )


def _validate_manual_skill_name(skill_name: str) -> str:
    name = skill_name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Skill name is required")
    if "/" in name or "\\" in name or ".." in name:
        raise HTTPException(status_code=400, detail="Skill name contains unsafe path characters")
    if not _SKILL_NAME_PATTERN.fullmatch(name):
        raise HTTPException(
            status_code=400,
            detail="Skill name must be hyphen-case using lowercase letters, digits, and hyphens only",
        )
    if name.startswith("-") or name.endswith("-") or "--" in name or len(name) > 64:
        raise HTTPException(status_code=400, detail="Skill name is not a valid skill identifier")
    return name


def _normalize_skill_description(description: str) -> str:
    text = description.strip()
    if not text:
        raise HTTPException(status_code=400, detail="Skill description is required")
    if "<" in text or ">" in text:
        raise HTTPException(status_code=400, detail="Skill description cannot contain angle brackets")
    return " ".join(text.splitlines())


def _tenant_skill_relative_path(tenant_id: str, skill_name: str) -> str:
    return (Path(tenant_id) / skill_name).as_posix()


def _tenant_skill_dir(tenant_id: str, skill_name: str) -> Path:
    return get_skills_root_path() / "custom" / tenant_id / skill_name


def _split_skill_markdown(content: str) -> tuple[dict[str, object], str]:
    match = re.match(r"^---\n(.*?)\n---\s*\n?(.*)$", content, re.DOTALL)
    if not match:
        return {}, ""
    try:
        frontmatter = yaml.safe_load(match.group(1)) or {}
    except yaml.YAMLError:
        frontmatter = {}
    if not isinstance(frontmatter, dict):
        frontmatter = {}
    metadata = frontmatter.get("metadata")
    if isinstance(metadata, dict):
        for key in ("created_by", "changelog", "usage_count"):
            if key not in frontmatter and key in metadata:
                frontmatter[key] = metadata[key]
    return frontmatter, match.group(2).strip()


def _read_skill_bytes(path):
    try:
        return read_owned_file(path)
    except OSError:
        raise HTTPException(409, "Skill member file cannot be verified; contents were preserved") from None


def _read_skill_file_payload(skill_dir: Path) -> tuple[str | None, str | None]:
    skill_file = skill_dir / "SKILL.md"
    if not skill_file.exists():
        return None, None
    frontmatter, instructions = _split_skill_markdown(_read_skill_bytes(skill_file).decode("utf-8"))
    description = frontmatter.get("description")
    if description is not None:
        description_text = str(description).strip()
        if not description_text:
            description_text = None
    else:
        description_text = None
    return description_text, instructions or None


def _read_skill_instructions(skill_dir: Path) -> str | None:
    _, instructions = _read_skill_file_payload(skill_dir)
    return instructions


def _render_skill_markdown(
    name: str,
    description: str,
    instructions: str | None,
    *,
    created_by: str | None = None,
    version: int = 1,
    changelog: str | None = None,
    usage_count: int = 0,
    references: dict[str, str] | None = None,
) -> str:
    body = (instructions or "").strip() or f"# {name}\n"
    frontmatter_lines = [
        f"name: {name}",
        f"description: {description}",
    ]
    if created_by:
        frontmatter_lines.append(f"created_by: {created_by}")
    frontmatter_lines.append(f"version: {version}")
    if changelog:
        frontmatter_lines.append(f"changelog: {changelog}")
    frontmatter_lines.append(f"usage_count: {usage_count}")
    if references:
        refs_yaml = yaml.dump(references, default_flow_style=False).strip()
        frontmatter_lines.append(f"references:\n{_indent(refs_yaml)}")
    fm = "\n".join(frontmatter_lines)
    return f"---\n{fm}\n---\n\n{body}\n"


def _indent(text: str, prefix: str = "  ") -> str:
    return "\n".join(prefix + line if line.strip() else line for line in text.splitlines())


def _write_skill_markdown(
    skill_dir: Path,
    *,
    name: str,
    description: str,
    instructions: str | None,
    created_by: str | None = None,
    version: int = 1,
    changelog: str | None = None,
    usage_count: int = 0,
    references: dict[str, str] | None = None,
) -> None:
    skill_dir.mkdir(parents=True, exist_ok=True)
    content = _render_skill_markdown(
        name, description, instructions,
        created_by=created_by,
        version=version,
        changelog=changelog,
        usage_count=usage_count,
        references=references,
    )
    (skill_dir / "SKILL.md").write_text(content, encoding="utf-8")


def _resolve_skill_runtime_dir(tenant_id: str, row_name: str, install_dir: str | None, relative_path: str | None) -> Path:
    if isinstance(install_dir, str) and install_dir.strip():
        return Path(install_dir)
    if isinstance(relative_path, str) and relative_path.strip():
        return get_skills_root_path() / "custom" / relative_path.strip()
    return _tenant_skill_dir(tenant_id, row_name)


def _build_skill_response(
    *,
    tenant_id: str,
    row_name: str,
    category: str,
    enabled: bool,
    settings: dict[str, object] | None = None,
    install_dir: str | None = None,
    relative_path: str | None = None,
) -> SkillResponse:
    skill_dir = _resolve_skill_runtime_dir(tenant_id, row_name, install_dir, relative_path)
    skill_file = skill_dir / "SKILL.md"
    file_description: str | None = None
    if skill_file.exists():
        raw = _read_skill_bytes(skill_file).decode("utf-8")
        fm, instructions = _split_skill_markdown(raw)
        description_value = fm.get("description")
        file_description = str(description_value).strip() if description_value is not None else None
    else:
        fm = {}
        instructions = ""

    settings = settings or {}

    return SkillResponse(
        name=row_name,
        description=file_description or "",
        license=fm.get("license"),
        category=category,
        enabled=enabled,
        bound_tools=settings.get("bound_tools") or [],
        prompt_template=settings.get("prompt_template"),
        strategy=settings.get("strategy"),
        instructions=instructions,
        created_by=fm.get("created_by"),
        version=int(fm.get("version", 1)),
        changelog=fm.get("changelog"),
        usage_count=int(fm.get("usage_count", 0)),
        references=fm.get("references"),
    )


@router.get(
    "/skills",
    response_model=SkillsListResponse,
    summary="List All Skills",
    description="Retrieve a list of all available skills from both public and custom directories.",
)
async def list_skills(request: Request) -> SkillsListResponse:
    require_tenant_context(request)
    try:
        available = await list_available_skills(request)
        return SkillsListResponse(skills=[SkillResponse.model_validate(item.model_dump()) for item in available.skills])
    except Exception as e:
        logger.error(f"Failed to load skills: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to load skills: {str(e)}")


@router.get(
    "/skills/available",
    response_model=AvailableSkillsListResponse,
    summary="List Available Skills",
    description="Return platform built-in and tenant-shared skills for current tenant context.",
)
async def list_available_skills(request: Request) -> AvailableSkillsListResponse:
    tenant_id = require_tenant_context(request)
    try:
        rows = await get_available_skills(
            request.state.user_id,
            tenant_id,
            is_tenant_admin=_is_tenant_admin(request),
            is_platform_admin=_is_platform_admin(request),
        )
        enriched_rows = []
        for row in rows:
            if row.get("scope") in {"tenant", "personal"} and row.get("files_status") == "verified":
                directory = resource_directory(get_skills_root_path(), tenant_id, request.state.user_id, row)
                raw_bytes = _read_skill_bytes(directory / "SKILL.md")
                frontmatter, instructions = _split_skill_markdown(raw_bytes.decode("utf-8"))
                description = frontmatter.get("description")
                if description is not None and str(description).strip():
                    row["description"] = str(description).strip()
                row["instructions"] = instructions
                row["file_sha256"] = hashlib.sha256(raw_bytes).hexdigest()
            enriched_rows.append(row)
        return AvailableSkillsListResponse(skills=[AvailableSkillResponse.model_validate(row) for row in enriched_rows])
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to load available skills: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to load available skills: {str(e)}")


@router.get(
    "/tenants/skills",
    response_model=SkillsListResponse,
    summary="List Tenant Shared Skills",
    dependencies=[Depends(require_tenant_admin)],
)
async def list_tenant_skills(request: Request) -> SkillsListResponse:
    tenant_id = require_tenant_context(request)
    rows = await list_tenant_shared_skills(tenant_id)
    settings_by_name = await get_tenant_shared_skill_settings(tenant_id)
    skills = []
    for row in rows:
        settings = settings_by_name.get(row.name) or {}
        skills.append(
            _build_skill_response(
                tenant_id=tenant_id,
                row_name=row.name,
                category=row.category,
                enabled=row.enabled,
                settings=settings,
                install_dir=getattr(row, "install_dir", None),
                relative_path=getattr(row, "relative_path", None),
            )
        )
    return SkillsListResponse(skills=skills)


async def _create_owned_skill(request: Request, body: TenantSkillCreateRequest, shared: bool) -> SkillCreationResponse:
    tenant, actor = _import_identity(request)
    name = _validate_manual_skill_name(body.name)
    description = _normalize_skill_description(body.description)
    category = (body.category or "custom").strip() or "custom" if shared else "personal"
    if category.lower() == "public":
        raise HTTPException(403, "Public source overrides use the original tenant enablement control")
    frontmatter = {"name": name, "description": description, "version": 1, "metadata": {"created_by": actor, "changelog": body.changelog or "Initial creation", "usage_count": 0}}
    markdown = "---\n" + yaml.safe_dump(frontmatter, sort_keys=False, allow_unicode=True) + "---\n\n" + ((body.instructions or "").strip() or f"# {name}") + "\n"
    root = get_skills_root_path()
    result = None
    resource_id = None
    try:
        with tempfile.TemporaryDirectory(prefix="prismos-manual-skill-") as directory:
            archive = Path(directory) / "manual.zip"
            with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_STORED) as package:
                package.writestr(name + "/SKILL.md", markdown)
            result, row = await skill_imports.import_archive(
                archive, tenant, actor, shared, root=root,
                manual_creation={"enabled": body.enabled, "category": category, "configuration_phase": "pending"},
                authorize=resource_operation_guard(request, shared),
            )
        resource_id = registered_resource_id(row)
        await initialize_owned_skill_configuration(tenant, actor, name, shared=shared, expected_resource_id=resource_id, enabled=body.enabled, bound_tools=body.bound_tools, prompt_template=body.prompt_template, strategy=body.strategy)
        await skill_imports.mark_manual_configuration(result, tenant, actor, shared, "confirmed", root=root)
        detail = await get_skill_detail(name, request, scope="tenant" if shared else "personal", resource_id=resource_id)
        return SkillCreationResponse(**detail.model_dump(), operation_id=result["operation_id"])
    except Exception as error:
        operation_id = getattr(error, "skill_operation_id", None) or (result or {}).get("operation_id")
        if operation_id:
            if result is not None:
                try:
                    await skill_imports.mark_manual_configuration(result, tenant, actor, shared, "unknown", root=root)
                except (OSError, ValueError):
                    pass
            raise HTTPException(503, {
                "message": "Creation outcome requires inspection; published content and native facts were preserved",
                "operation_id": operation_id, "resource_id": resource_id,
                "recovery_available": True, "inspection_required": True,
            }) from None
        if isinstance(error, (SkillAlreadyExistsError, FileExistsError, RuntimeError)):
            raise HTTPException(409, str(error)) from None
        if isinstance(error, ValueError):
            raise HTTPException(400, str(error)) from None
        raise HTTPException(503, "Skill creation unavailable; inspect current resources") from None


@router.post(
    "/tenants/skills",
    response_model=SkillCreationResponse,
    status_code=201,
    summary="Create Tenant Shared Skill",
    dependencies=[Depends(require_tenant_admin)],
)
async def create_tenant_skill(request: Request, body: TenantSkillCreateRequest) -> SkillCreationResponse:
    require_tenant_admin(request)
    return await _create_owned_skill(request, body, True)


@router.put(
    "/tenants/skills/{skill_name}",
    response_model=SkillDetailResponse,
    summary="Update Tenant Shared Skill",
    dependencies=[Depends(require_tenant_admin)],
)
async def update_tenant_skill(skill_name: str, request: SkillUpdateRequest, api_request: Request) -> SkillDetailResponse:
    require_tenant_admin(api_request)
    tenant, actor = _import_identity(api_request)
    try:
        scope, resource_id = await skill_mutations.set_shared_enablement(get_skills_root_path(), tenant, actor, skill_name, request.enabled, request.expected_resource_id)
    except skill_mutations.SkillMutationRejected as error:
        raise HTTPException(error.status, str(error)) from None
    except skill_mutations.SkillMutationUnknown as error:
        raise HTTPException(503, {"message": str(error), "resource_id": error.resource_id, "inspection_required": True}) from None
    except Exception:
        logger.exception("Skill enablement did not complete")
        raise HTTPException(503, "Skill enablement unavailable; inspect current resources") from None
    try:
        return await get_skill_detail(skill_name, api_request, scope=scope, resource_id=resource_id)
    except Exception:
        raise HTTPException(503, {"message": "Skill enablement response could not be confirmed; inspect current state", "resource_id": resource_id, "inspection_required": True}) from None


async def _patch_owned_response(name: str, body: TenantSkillPatchRequest, request: Request, shared: bool):
    tenant, actor = _import_identity(request)
    try:
        resource_id = await skill_mutations.patch_owned_skill(get_skills_root_path(), tenant, actor, shared, name, body, split=_split_skill_markdown, render=_render_skill_markdown, normalize=_normalize_skill_description)
    except skill_mutations.SkillMutationRejected as error:
        raise HTTPException(error.status, str(error)) from None
    except skill_mutations.SkillMutationUnknown as error:
        raise HTTPException(503, {"message": str(error), "resource_id": error.resource_id, "inspection_required": True}) from None
    except HTTPException:
        raise
    except Exception:
        logger.exception("Owned Skill edit did not complete")
        raise HTTPException(503, "Skill edit unavailable; inspect the current resource before retrying") from None
    try:
        return await get_skill_detail(name, request, scope="tenant" if shared else "personal", resource_id=resource_id)
    except Exception:
        raise HTTPException(503, {"message": "Skill edit response could not be confirmed; inspect current state", "resource_id": resource_id, "inspection_required": True}) from None


@router.patch(
    "/tenants/skills/{skill_name}",
    response_model=SkillDetailResponse,
    summary="Patch Tenant Shared Skill",
    dependencies=[Depends(require_tenant_admin)],
)
async def patch_tenant_skill(skill_name: str, request: TenantSkillPatchRequest, api_request: Request) -> SkillResponse:
    require_tenant_admin(api_request)
    return await _patch_owned_response(skill_name, request, api_request, True)


async def _deletion_preflight(name: str, request: Request, shared: bool, expected_resource_id: str | None = None):
    if shared:
        require_tenant_admin(request)
    tenant, actor = _import_identity(request)
    try:
        return await skill_deletions.preflight(get_skills_root_path(), tenant, actor, shared, name, expected_resource_id)
    except skill_mutations.SkillMutationRejected as error:
        raise HTTPException(error.status, str(error)) from None
    except (ValueError, OSError):
        raise HTTPException(409, "Deletion ownership or references cannot be verified; contents were preserved") from None


async def _delete_owned_response(name: str, request: Request, shared: bool, expected_resource_id=None, expected_tree_sha256=None, expected_file_sha256=None):
    if shared:
        require_tenant_admin(request)
    tenant, actor = _import_identity(request)
    try:
        await skill_deletions.delete_owned(get_skills_root_path(), tenant, actor, shared, name, expected_resource_id=expected_resource_id, expected_tree_sha256=expected_tree_sha256, expected_file_sha256=expected_file_sha256)
    except skill_mutations.SkillMutationRejected as error:
        raise HTTPException(error.status, str(error)) from None
    except skill_deletions.SkillDeletionUnknown as error:
        raise HTTPException(503, {"message": str(error), "operation_id": error.operation_id, "resource_id": error.resource_id, "inspection_required": True, "recovery_available": True}) from None
    except (ValueError, OSError):
        raise HTTPException(409, "Deletion ownership or references cannot be verified; contents were preserved") from None
    except Exception:
        logger.exception("Resource deletion did not complete")
        raise HTTPException(503, "Deletion unavailable; inspect current resource and operation records") from None


@router.get("/tenants/skills/{skill_name}/deletion-preflight", dependencies=[Depends(require_tenant_admin)])
async def tenant_deletion_preflight(skill_name: str, request: Request, expected_resource_id: str | None = None):
    return await _deletion_preflight(skill_name, request, True, expected_resource_id)


@router.get("/skills/personal/{skill_name}/deletion-preflight")
async def personal_deletion_preflight(skill_name: str, request: Request, expected_resource_id: str | None = None):
    return await _deletion_preflight(skill_name, request, False, expected_resource_id)


@router.delete("/tenants/skills/{skill_name}", status_code=204, summary="Delete Tenant Shared Skill", dependencies=[Depends(require_tenant_admin)])
async def delete_tenant_skill(skill_name: str, request: Request, expected_resource_id: str | None = None, expected_tree_sha256: str | None = None, expected_file_sha256: str | None = None):
    return await _delete_owned_response(skill_name, request, True, expected_resource_id, expected_tree_sha256, expected_file_sha256)


@router.post(
    "/skills/personal",
    response_model=SkillCreationResponse,
    status_code=201,
    summary="Create Personal Skill",
)
async def create_personal_skill(request: Request, body: TenantSkillCreateRequest) -> SkillCreationResponse:
    return await _create_owned_skill(request, body, False)


@router.patch(
    "/skills/personal/{skill_name}",
    response_model=SkillDetailResponse,
    summary="Patch Personal Skill",
)
async def patch_personal_skill(skill_name: str, request: TenantSkillPatchRequest, api_request: Request) -> SkillResponse:
    return await _patch_owned_response(skill_name, request, api_request, False)


@router.delete("/skills/personal/{skill_name}", status_code=204, summary="Delete Personal Skill")
async def delete_personal_skill(skill_name: str, request: Request, expected_resource_id: str | None = None, expected_tree_sha256: str | None = None, expected_file_sha256: str | None = None):
    return await _delete_owned_response(skill_name, request, False, expected_resource_id, expected_tree_sha256, expected_file_sha256)


def _import_error_detail(error: Exception, result: dict | None = None):
    operation_id = getattr(error, "skill_operation_id", None) or (result or {}).get("operation_id")
    if operation_id:
        return {"message": "Import outcome requires reconciliation; published files were preserved", "operation_id": operation_id, "recovery_available": True}
    return str(error)


def _import_identity(request: Request) -> tuple[str, str]:
    tenant = require_tenant_context(request)
    user = getattr(request.state, "user_id", "")
    if not user:
        raise HTTPException(401, "User ID is required")
    return tenant, user


async def _import_operations(request: Request, shared: bool, cursor: str | None, page_size: int):
    tenant, user = _import_identity(request)
    try:
        return await skill_imports.list_operation_page(tenant, user, shared, root=get_skills_root_path(), cursor=cursor, page_size=page_size)
    except skill_imports.InvalidImportCursor as error:
        raise HTTPException(400, str(error)) from None
    except ValueError:
        raise HTTPException(409, "Skill import scope cannot be verified; contents were preserved") from None
    except Exception:
        logger.exception("Skill import inspection did not complete")
        raise HTTPException(503, "Import records unavailable; inspect again before taking action") from None


async def _import_operation(request: Request, operation_id: str, shared: bool, recover: bool = False, abort: bool = False):
    if shared:
        require_tenant_admin(request)
    tenant, user = _import_identity(request)
    try:
        callback = skill_imports.abort_operation if abort else skill_imports.recover_operation if recover else skill_imports.observe_operation
        options = {"authorize": resource_operation_guard(request, shared)} if recover else {}
        return await callback(operation_id, tenant, user, shared, root=get_skills_root_path(), **options)
    except FileNotFoundError:
        raise HTTPException(404, "Skill import operation not found") from None
    except (ValueError, RuntimeError):
        raise HTTPException(409, "Skill import state or contents conflict; files were preserved") from None
    except Exception:
        logger.exception("Skill import reconciliation did not complete")
        raise HTTPException(503, "Registration outcome is uncertain; inspect current import state before retrying") from None


@router.get("/skills/personal/imports")
async def personal_import_operations(request: Request, cursor: str | None = Query(default=None, max_length=512), page_size: int = Query(default=100, ge=1, le=100)):
    return await _import_operations(request, False, cursor, page_size)


@router.get("/skills/personal/imports/{operation_id}")
async def personal_import_operation(request: Request, operation_id: str):
    return await _import_operation(request, operation_id, False)


@router.post("/skills/personal/imports/{operation_id}/recover")
async def recover_personal_import(request: Request, operation_id: str):
    return await _import_operation(request, operation_id, False, True)


@router.post("/skills/personal/imports/{operation_id}/abort")
async def abort_personal_import(request: Request, operation_id: str):
    return await _import_operation(request, operation_id, False, abort=True)


@router.get("/tenants/skills/imports", dependencies=[Depends(require_tenant_admin)])
async def tenant_import_operations(request: Request, cursor: str | None = Query(default=None, max_length=512), page_size: int = Query(default=100, ge=1, le=100)):
    return await _import_operations(request, True, cursor, page_size)


@router.get("/tenants/skills/imports/{operation_id}", dependencies=[Depends(require_tenant_admin)])
async def tenant_import_operation(request: Request, operation_id: str):
    return await _import_operation(request, operation_id, True)


@router.post("/tenants/skills/imports/{operation_id}/recover", dependencies=[Depends(require_tenant_admin)])
async def recover_tenant_import(request: Request, operation_id: str):
    return await _import_operation(request, operation_id, True, True)

@router.post("/tenants/skills/imports/{operation_id}/abort", dependencies=[Depends(require_tenant_admin)])
async def abort_tenant_import(request: Request, operation_id: str):
    return await _import_operation(request, operation_id, True, abort=True)


@router.post(
    "/skills/personal/import",
    response_model=SkillResponse,
    status_code=201,
    summary="Import Personal Skill",
)
async def import_personal_skill(request: Request, archive: UploadFile = File(...)) -> SkillResponse:
    tenant_id = require_tenant_context(request)
    user_id: str = getattr(request.state, "user_id", "")
    if not user_id:
        raise HTTPException(status_code=401, detail="User ID is required")

    filename = archive.filename or ""
    suffix = Path(filename).suffix.lower()
    if suffix not in {".skill", ".zip"}:
        raise HTTPException(status_code=400, detail="File must have .skill or .zip extension")

    temp_path: Path | None = None
    result: dict | None = None
    try:
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as temp_file:
            temp_path = Path(temp_file.name)
            while chunk := await archive.read(1024 * 1024):
                temp_file.write(chunk)

        result, row = await skill_imports.import_archive(temp_path, tenant_id, user_id, False, root=get_skills_root_path(), authorize=resource_operation_guard(request))
        return _build_skill_response(
            tenant_id=tenant_id,
            row_name=row.name,
            category=row.category,
            enabled=row.enabled,
            settings={},
            install_dir=getattr(row, "install_dir", None),
            relative_path=getattr(row, "relative_path", None),
        )
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except SkillAlreadyExistsError as e:
        raise HTTPException(status_code=409, detail=_import_error_detail(e, result))
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=_import_error_detail(e, result))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=_import_error_detail(e, result))
    except Exception as e:
        logger.error("Failed to import personal skill: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=_import_error_detail(e, result))
    finally:
        await archive.close()
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)


@router.post(
    "/tenants/skills/import",
    response_model=SkillResponse,
    status_code=201,
    summary="Import Tenant Shared Skill",
    dependencies=[Depends(require_tenant_admin)],
)
async def import_tenant_skill(request: Request, archive: UploadFile = File(...)) -> SkillResponse:
    tenant_id = require_tenant_context(request)
    filename = archive.filename or ""
    suffix = Path(filename).suffix.lower()
    if suffix not in {".skill", ".zip"}:
        raise HTTPException(status_code=400, detail="File must have .skill or .zip extension")

    temp_path: Path | None = None
    result: dict | None = None
    try:
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as temp_file:
            temp_path = Path(temp_file.name)
            while chunk := await archive.read(1024 * 1024):
                temp_file.write(chunk)

        result, row = await skill_imports.import_archive(temp_path, tenant_id, getattr(request.state, "user_id", ""), True, root=get_skills_root_path(), authorize=resource_operation_guard(request, True))
        settings = await get_tenant_shared_skill_settings(tenant_id)
        return _build_skill_response(
            tenant_id=tenant_id,
            row_name=row.name,
            category=row.category,
            enabled=row.enabled,
            settings=settings.get(row.name) or {},
            install_dir=getattr(row, "install_dir", None),
            relative_path=getattr(row, "relative_path", None),
        )
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except SkillAlreadyExistsError as e:
        raise HTTPException(status_code=409, detail=_import_error_detail(e, result))
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=_import_error_detail(e, result))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=_import_error_detail(e, result))
    except Exception as e:
        logger.error("Failed to import tenant skill: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=_import_error_detail(e, result))
    finally:
        await archive.close()
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)


@router.get(
    "/skills/{skill_name}",
    response_model=SkillResponse,
    summary="Get Skill Details",
    description="Retrieve detailed information about a specific skill by its name.",
)
async def get_skill(skill_name: str, request: Request) -> SkillResponse:
    require_tenant_context(request)
    try:
        detail = await get_skill_detail(skill_name, request, scope=None, resource_id=None)
        return SkillResponse.model_validate(detail.model_dump())
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get skill {skill_name}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get skill: {str(e)}")


@router.post(
    "/skills/install",
    response_model=SkillInstallResponse,
    summary="Install Skill",
    description="Tenant admins install a .skill or .zip archive and register it as a tenant-shared skill.",
    dependencies=[Depends(require_tenant_admin)],
)
async def install_skill(request: SkillInstallRequest, api_request: Request) -> SkillInstallResponse:
    tenant_id = require_tenant_context(api_request)
    result = None
    try:
        skill_file_path = resolve_thread_virtual_path(
            api_request.state.user_id,
            request.thread_id,
            request.path,
            tenant_id=getattr(api_request.state, "tenant_id", None),
        )
        result, _ = await skill_imports.import_archive(skill_file_path, tenant_id, api_request.state.user_id, True, root=get_skills_root_path(), authorize=resource_operation_guard(api_request, True))
        return SkillInstallResponse(**result)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=_import_error_detail(e, result))
    except SkillAlreadyExistsError as e:
        raise HTTPException(status_code=409, detail=_import_error_detail(e, result))
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=_import_error_detail(e, result))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=_import_error_detail(e, result))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to install skill: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=_import_error_detail(e, result))


@router.get(
    "/skills/{skill_name}/detail",
    response_model=SkillDetailResponse,
    summary="Get Skill Detail",
    description="Return full detail for any available skill (global, tenant, or personal).",
)
async def get_skill_detail(skill_name: str, request: Request, scope: Literal["global", "tenant", "personal"] | None = None, resource_id: str | None = Query(default=None, max_length=128)) -> SkillDetailResponse:
    tenant_id = require_tenant_context(request)
    user_id = request.state.user_id
    
    rows = await get_available_skills(
        user_id,
        tenant_id,
        is_tenant_admin=_is_tenant_admin(request),
        is_platform_admin=_is_platform_admin(request),
    )
    
    row = next((r for r in rows if r.get("name") == skill_name and (scope is None or r.get("scope") == scope) and (resource_id is None or r.get("resource_id") == resource_id)), None)
    if row is None:
        raise HTTPException(status_code=404, detail=f"Skill '{skill_name}' not found or you don't have access")

    try:
        skill_dir = resource_directory(get_skills_root_path(), tenant_id, user_id, row)
    except ValueError:
        raise HTTPException(409, "Skill resource location cannot be verified; contents were preserved") from None
    skill_file = skill_dir / "SKILL.md"
    file_description: str | None = None
    file_sha256 = None
    if skill_file.exists():
        raw_bytes = _read_skill_bytes(skill_file)
        file_sha256 = hashlib.sha256(raw_bytes).hexdigest()
        raw = raw_bytes.decode("utf-8")
        fm, instructions = _split_skill_markdown(raw)
        description_value = fm.get("description")
        file_description = str(description_value).strip() if description_value is not None else None
    else:
        fm = {}
        instructions = ""

    return SkillDetailResponse(
        file_sha256=file_sha256,
        resource_id=row.get("resource_id"),
        owner_kind=row.get("owner_kind"),
        files_status=row.get("files_status"),
        name=row.get("name") or skill_name,
        description=file_description or row.get("description") or "",
        license=row.get("license"),
        category=row.get("category"),
        enabled=row.get("enabled", True),
        bound_tools=row.get("bound_tools") or [],
        prompt_template=row.get("prompt_template"),
        strategy=row.get("strategy"),
        instructions=instructions,
        created_by=fm.get("created_by"),
        version=int(fm.get("version", 1)),
        changelog=fm.get("changelog"),
        usage_count=int(fm.get("usage_count", 0)),
        references=fm.get("references"),
        scope=row.get("scope", "global"),
        managed_by_current_user=row.get("managed_by_current_user", False),
    )


@router.post(
    "/skills/generate-instructions",
    response_model=GenerateInstructionsResponse,
    summary="Generate Skill Instructions via AI",
    description="Use AI to auto-generate structured instructions from a natural language description.",
)
async def generate_skill_instructions(
    request: Request,
    body: GenerateInstructionsRequest,
) -> GenerateInstructionsResponse:
    require_tenant_context(request)
    try:
        from langchain_core.messages import HumanMessage, SystemMessage

        from deerflow.models.factory import create_chat_model

        llm = create_chat_model(body.model_name or "gpt-4o")
        
        sys_msg = SystemMessage(content="You are an expert AI prompt engineer and Skill Instruction Writer for an AI Agent platform.")
        human_msg = HumanMessage(content=f"""A user wants to create a new Agent Skill. They described what they want the agent to be able to do:

"{body.prompt}"

Please write structured, professional Skill instructions in Chinese (Simplified).
Follow these guidelines:
1. Use clear Markdown headings (##, ###)
2. Define the goal clearly and outline a step-by-step workflow for the agent to follow
3. Include any required conditions, constraints, or what NOT to do
4. If applicable, suggest which tools or capabilities the agent should leverage at each step
5. Keep instructions between 300-1500 characters
6. The instructions are for the Agent to read and execute, so use an instructional tone ("You should...")

Output ONLY the instructions text, no preamble or explanation.""")

        result = await llm.ainvoke([sys_msg, human_msg])
        output_text = result.content if hasattr(result, "content") else str(result)

        return GenerateInstructionsResponse(instructions=output_text.strip())
    except Exception as e:
        logger.error(f"Failed to generate instructions: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to generate instructions: {str(e)}")


@router.post(
    "/skills/summarize-diagnosis",
    response_model=SummarizeDiagnosisResponse,
    summary="Summarize Diagnosis into Skill",
    description="Use AI to refine an incident diagnosis conclusion into structured, reusable Skill instructions (SOP). Removes instance-specific details and extracts domain knowledge.",
)
async def summarize_diagnosis(
    request: Request,
    body: SummarizeDiagnosisRequest,
) -> SummarizeDiagnosisResponse:
    require_tenant_context(request)
    try:
        import json as _json

        from deerflow.database.user_config_store import load_enabled_tenant_model_names
        from deerflow.models import create_chat_model

        tenant_id = getattr(request.state, "tenant_id", "")
        enabled_models = load_enabled_tenant_model_names(tenant_id) if tenant_id else []
        model_name = enabled_models[0] if enabled_models else None
        if not model_name:
            raise HTTPException(status_code=403, detail="No enabled tenant-assigned models are available")

        model = create_chat_model(name=model_name, thinking_enabled=False)

        steps_text = ""
        if body.diagnosis_steps:
            steps_text = "诊断执行步骤：\n" + "\n".join(f"- {s}" for s in body.diagnosis_steps)

        tools_text = ""
        if body.tool_calls_summary:
            tools_text = "使用的工具：\n" + "\n".join(
                f"- {t.tool}: {t.description}" for t in body.tool_calls_summary
            )

        user_notes_text = ""
        if body.user_notes:
            user_notes_text = f"\n用户补充说明：{body.user_notes}"

        gen_prompt = f"""你是运维 SRE 领域的 Skill 指令编写专家。用户完成了一次诊断排查，需要将排查经验提炼为可复用的 Skill 指令。

## 告警/排查信息
- 标题：{body.incident_title or '未知'}
- 服务：{body.incident_service or '未知'}
- 环境：{body.incident_environment or '未知'}
- 严重级别：{body.incident_severity or '未知'}

## 排查记录
{body.diagnosis_result[:3000]}

{steps_text}

{tools_text}
{user_notes_text}

## 任务要求

请将上述排查过程提炼为结构化的 Skill 指令。**严格遵循**以下规则：

1. **去实例化**：移除所有具体 IP 地址、Pod 名称、节点名、时间戳、具体数值。用 `<pod-name>` 等占位符代替。
2. **提取通用 SOP**：从单次排查过程抽象出通用的排查流程，让其他运维人员可以复用。
3. **保留领域知识**：保留关键的检查命令、诊断思路、根因分类、阈值建议。
4. **中文输出**：所有内容使用简体中文。

## 输出格式（严格按此结构，分两个代码块）

### 第一个代码块（JSON 元数据）：
```json
{{
  "suggested_name": "英文小写+连字符短名称",
  "suggested_description": "一句话中文描述",
  "suggested_tools": ["工具名1", "工具名2"],
  "suggested_category": "分类"
}}
```

### 第二个代码块（Markdown 指令）：
```markdown
## 适用场景
...

## 排查步骤
1. ...

## 关键检查点
- ...

## 常见根因
- ...

## 修复建议
- ...

## 参考命令
```
```

请确保两个代码块都完整输出，不要省略任何内容。"""

        response = model.invoke(gen_prompt)
        output_text = ""
        if hasattr(response, "content"):
            content = response.content
            if isinstance(content, str):
                output_text = content
            elif isinstance(content, list):
                parts = []
                for block in content:
                    if isinstance(block, str):
                        parts.append(block)
                    elif isinstance(block, dict) and block.get("type") in {"text", "output_text"}:
                        text = block.get("text")
                        if isinstance(text, str):
                            parts.append(text)
                output_text = "\n".join(parts)

        if not output_text:
            raise HTTPException(status_code=500, detail="AI 返回了空内容，请重试")

        # Parse JSON metadata from the first code block
        json_match = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', output_text, re.DOTALL)
        if not json_match:
            raise HTTPException(status_code=500, detail="AI 未返回有效的 JSON 元数据，请重试")
        json_text = json_match.group(1).strip()

        # Parse instructions from the second code block (markdown)
        remaining = output_text[json_match.end():]
        md_match = re.search(r'```(?:markdown)?\s*\n?(.*?)\n?```', remaining, re.DOTALL)
        instructions = md_match.group(1).strip() if md_match else ""
        # Fallback: if no second fence, use everything after the first fence as instructions
        if not instructions:
            instructions = remaining.strip()

        data = _json.loads(json_text)

        return SummarizeDiagnosisResponse(
            suggested_name=str(data.get("suggested_name", "diagnosis-skill")),
            suggested_description=str(data.get("suggested_description", "")),
            instructions=instructions or str(data.get("instructions", "")),
            suggested_tools=[str(t) for t in data.get("suggested_tools", [])],
            suggested_category=str(data.get("suggested_category", "custom")),
        )
    except _json.JSONDecodeError as e:
        logger.error(f"Failed to parse LLM JSON response: {e}\nRaw output: {output_text[:500] if 'output_text' in dir() else 'N/A'}")
        raise HTTPException(status_code=500, detail="AI 返回格式异常，请重试")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to summarize diagnosis: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to summarize diagnosis: {str(e)}")
