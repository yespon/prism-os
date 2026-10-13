"""CRUD API for custom agents — DB-backed."""

import hashlib
import json
import logging
import re
import uuid
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import case
from sqlalchemy import select as sa_select
from sqlalchemy.exc import IntegrityError
from sqlmodel.ext.asyncio.session import AsyncSession

from app.gateway.authorization import _is_tenant_admin, require_tenant_context
from app.gateway.config import get_plugin_states
from app.integrations.agent_skill_references import SkillResourceReference, binding, save_binding
from app.integrations.octop.agents import AgentPresentation, AgentQuickPrompt, agent_content, update_agent_content
from app.integrations.skill_reference_transactions import begin_reference_transaction
from app.models.agents import CustomAgent
from deerflow.config.paths import get_paths
from deerflow.database.session import get_session
from deerflow.skills import load_skills

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["agents"])

AGENT_NAME_PATTERN = re.compile(r"^[A-Za-z0-9-]+$")


# ---------------------------------------------------------------------------
# Response / Request models
# ---------------------------------------------------------------------------


class AgentResponse(BaseModel):
    """Response model for a custom agent."""

    revision: str | None = None
    id: str = Field(..., description="UUID")
    name: str = Field(..., description="Agent name (hyphen-case)")
    description: str = Field(default="", description="Agent description")
    model: str | None = Field(default=None, description="Optional model override")
    tool_groups: list[str] | None = Field(default=None, description="Optional tool group whitelist")
    system_prompt: str | None = Field(default=None, description="Agent personality and behavioral guardrails")
    skill_binding_mode: Literal["all", "selected", "unresolved"] | None = None
    skill_resources: list[SkillResourceReference] | None = None
    skills: list[str] = Field(default_factory=list, description="Allowed skill SOPs")
    enabled: bool = Field(default=True, description="Whether the agent is active")
    tags: list[str] = Field(default_factory=list, description="Filter labels")
    created_by: str | None = Field(default=None, description="Creator user ID")
    created_at: str | None = Field(default=None, description="ISO timestamp")
    updated_at: str | None = Field(default=None, description="ISO timestamp")
    is_shared: bool = Field(default=False, description="Whether the agent is shared with the tenant")
    presentation: AgentPresentation = Field(default_factory=AgentPresentation)
    base_system_prompt: str = ""
    # Deprecated alias
    soul: str | None = Field(default=None, description="Deprecated — use system_prompt")


class AgentsListResponse(BaseModel):
    """Response model for listing agents."""

    agents: list[AgentResponse]


class AgentCreateRequest(BaseModel):
    """Request body for creating a custom agent."""

    name: str = Field(..., description="Agent name (must match ^[A-Za-z0-9-]+$, stored as lowercase)")
    description: str = Field(default="", description="Agent description")
    model: str | None = Field(default=None, description="Optional model override")
    tool_groups: list[str] | None = Field(default=None, description="Optional tool group whitelist")
    system_prompt: str = Field(default="", description="Agent personality and behavioral guardrails")
    skill_binding_mode: Literal["all", "selected"] | None = None
    skill_resources: list[SkillResourceReference] | None = Field(default=None, max_length=128)
    skills: list[str] = Field(default_factory=list, description="Allowed skill SOPs (empty = all available)")
    tags: list[str] = Field(default_factory=list, description="Filter labels")
    enabled: bool = Field(default=True, description="Enable or disable the agent")
    is_shared: bool = Field(default=False, description="Whether the agent is shared with the tenant")
    template_id: str | None = Field(default=None, max_length=200)
    template_locale: Literal["zh", "en"] = "zh"
    persona_mbti: str | None = Field(default=None, max_length=4)
    quick_prompts: list[AgentQuickPrompt] = Field(default_factory=list, max_length=32)
    welcome_message: str | None = Field(default=None, max_length=2000)
    avatar_id: str | None = Field(default=None, max_length=100)
    # Deprecated field — accepted but mapped to system_prompt
    soul: str | None = Field(default=None, description="Deprecated — use system_prompt")


class AgentUpdateRequest(BaseModel):
    """Request body for updating a custom agent. All fields optional."""

    expected_agent_id: str | None = Field(default=None, max_length=80)
    expected_revision: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    template_locale: Literal["zh", "en"] | None = None
    persona_mbti: str | None = Field(default=None, max_length=4)
    quick_prompts: list[AgentQuickPrompt] | None = Field(default=None, max_length=32)
    welcome_message: str | None = Field(default=None, max_length=2000)
    avatar_id: str | None = Field(default=None, max_length=100)
    description: str | None = Field(default=None, description="Updated description")
    model: str | None = Field(default=None, description="Updated model override")
    tool_groups: list[str] | None = Field(default=None, description="Updated tool group whitelist")
    system_prompt: str | None = Field(default=None, description="Updated agent personality")
    skill_binding_mode: Literal["all", "selected"] | None = None
    skill_resources: list[SkillResourceReference] | None = Field(default=None, max_length=128)
    skills: list[str] | None = Field(default=None, description="Updated skill whitelist")
    enabled: bool | None = Field(default=None, description="Enable or disable the agent")
    tags: list[str] | None = Field(default=None, description="Updated filter labels")
    is_shared: bool | None = Field(default=None, description="Whether the agent is shared with the tenant")
    # Deprecated field
    soul: str | None = Field(default=None, description="Deprecated — use system_prompt")


class UserProfileResponse(BaseModel):
    """Response model for the global user profile (USER.md)."""

    content: str | None = Field(default=None, description="USER.md content")


class UserProfileUpdateRequest(BaseModel):
    """Request body for setting the global user profile."""

    content: str = Field(default="", description="USER.md content")


class SkillResponse(BaseModel):
    """Response model for an installed skill."""

    name: str
    description: str
    category: str
    enabled: bool


class SkillsListResponse(BaseModel):
    """Response model for listing skills."""

    skills: list[SkillResponse]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _validate_agent_name(name: str) -> None:
    if not AGENT_NAME_PATTERN.match(name):
        raise HTTPException(
            status_code=422,
            detail=f"Invalid agent name '{name}'. Must match ^[A-Za-z0-9-]+$ (letters, digits, and hyphens only).",
        )


def _normalize_agent_name(name: str) -> str:
    return name.lower()


def _agent_revision(agent):
    value = [agent.id, agent.user_id, agent.name, agent.description, agent.model, agent.tool_groups, agent.system_prompt, agent.skills, agent.enabled, agent.tags, agent.meta_info]
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


def _agent_to_response(agent: CustomAgent) -> AgentResponse:
    try:
        selected = binding(agent)
    except ValueError:
        selected = None
    return AgentResponse(
        revision=_agent_revision(agent),
        skill_binding_mode=selected.mode if selected else None,
        skill_resources=selected.resources if selected else None,
        id=agent.id,
        name=agent.name,
        description=agent.description or "",
        model=agent.model,
        tool_groups=agent.tool_groups or [],
        system_prompt=agent.system_prompt or None,
        skills=agent.skills or [],
        enabled=agent.enabled,
        tags=agent.tags or [],
        created_by=agent.created_by,
        created_at=agent.created_at.isoformat() if agent.created_at else None,
        updated_at=agent.updated_at.isoformat() if agent.updated_at else None,
        is_shared=agent.user_id == "tenant-shared",
        soul=agent.system_prompt or None,
        base_system_prompt=agent_content(agent)[0],
        presentation=agent_content(agent)[1],
    )


def _get_user_id(request: Request) -> str:
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")
    return user_id


# ---------------------------------------------------------------------------
# Agent CRUD endpoints
# ---------------------------------------------------------------------------


@router.get(
    "/agents",
    response_model=AgentsListResponse,
    summary="List Custom Agents",
)
async def list_agents(
    request: Request,
    show_all: bool = Query(default=False, description="Show all tenant agents for discoverability"),
    tag: str | None = Query(default=None, description="Filter by tag"),
    skill: str | None = Query(default=None, description="Filter by skill"),
    session: AsyncSession = Depends(get_session),
) -> AgentsListResponse:
    tenant_id = require_tenant_context(request)
    user_id = _get_user_id(request)

    query = sa_select(CustomAgent).where(
        CustomAgent.tenant_id == tenant_id,
    )

    is_admin = _is_tenant_admin(request)
    if is_admin:
        if not show_all:
            query = query.where((CustomAgent.user_id == user_id) | (CustomAgent.user_id == "tenant-shared"))
    else:
        if show_all:
            query = query.where(CustomAgent.user_id != "tenant-shared")
        else:
            query = query.where(CustomAgent.user_id == user_id)

    result = await session.exec(query.order_by(CustomAgent.name))
    agents = result.scalars().all()

    # Client-side tag/skill filtering
    if tag:
        tag_lower = tag.lower()
        agents = [a for a in agents if any(tag_lower in t.lower() for t in (a.tags or []))]
    if skill:
        agents = [a for a in agents if skill in (a.skills or [])]

    return AgentsListResponse(agents=[_agent_to_response(a) for a in agents])


@router.get(
    "/agents/check",
    summary="Check Agent Name Availability",
)
async def check_agent_name(
    name: str,
    request: Request,
    is_shared: bool = Query(default=False, description="Check availability for shared agent"),
    session: AsyncSession = Depends(get_session),
) -> dict:
    _validate_agent_name(name)
    tenant_id = require_tenant_context(request)
    user_id = _get_user_id(request)
    normalized = _normalize_agent_name(name)

    target_user_id = "tenant-shared" if (is_shared and _is_tenant_admin(request)) else user_id

    result = await session.exec(
        sa_select(CustomAgent).where(
            CustomAgent.tenant_id == tenant_id,
            CustomAgent.user_id == target_user_id,
            CustomAgent.name == normalized,
        )
    )
    existing = result.scalars().first()
    return {"available": existing is None, "name": normalized}


@router.get(
    "/agents/{name}",
    response_model=AgentResponse,
    summary="Get Custom Agent",
)
async def get_agent(
    name: str,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> AgentResponse:
    _validate_agent_name(name)
    name = _normalize_agent_name(name)
    tenant_id = require_tenant_context(request)
    user_id = _get_user_id(request)

    user_ids = [user_id]
    if _is_tenant_admin(request):
        user_ids.append("tenant-shared")

    result = await session.exec(
        sa_select(CustomAgent).where(
            CustomAgent.tenant_id == tenant_id,
            CustomAgent.user_id.in_(user_ids),
            CustomAgent.name == name,
        ).order_by(case((CustomAgent.user_id == user_id, 0), else_=1))
    )
    agent = result.scalars().first()

    if agent is None:
        raise HTTPException(status_code=404, detail=f"Agent '{name}' not found")
    return _agent_to_response(agent)


@router.post(
    "/agents",
    response_model=AgentResponse,
    status_code=201,
    summary="Create Custom Agent",
)
async def create_agent_endpoint(
    body: AgentCreateRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> AgentResponse:
    _validate_agent_name(body.name)
    tenant_id = require_tenant_context(request)
    user_id = _get_user_id(request)
    normalized_name = _normalize_agent_name(body.name)

    is_admin = _is_tenant_admin(request)
    if body.is_shared and not is_admin:
        raise HTTPException(status_code=403, detail="Only tenant admins can create shared agents")

    target_user_id = "tenant-shared" if body.is_shared else user_id

    from app.integrations.octop.agents import resolve_agent_prompt

    system_prompt, source_metadata = resolve_agent_prompt(body)
    if not system_prompt:
        raise HTTPException(status_code=422, detail="system_prompt is required and must not be empty")

    await begin_reference_transaction(session, tenant_id)

    # Check uniqueness
    result = await session.exec(
        sa_select(CustomAgent).where(
            CustomAgent.tenant_id == tenant_id,
            CustomAgent.user_id == target_user_id,
            CustomAgent.name == normalized_name,
        )
    )
    if result.scalars().first() is not None:
        raise HTTPException(status_code=409, detail=f"Agent '{normalized_name}' already exists")

    agent = CustomAgent(
        id=str(uuid.uuid4()),
        tenant_id=tenant_id,
        user_id=target_user_id,
        name=normalized_name,
        description=body.description or "",
        model=body.model,
        tool_groups=body.tool_groups or [],
        system_prompt=system_prompt,
        skills=body.skills or [],
        tags=body.tags or [],
        enabled=body.enabled,
        created_by=user_id,
        meta_info=source_metadata,
    )

    await save_binding(session, agent, tenant_id, user_id, body.skill_binding_mode, body.skill_resources, explicit=bool({"skill_resources", "skill_binding_mode"} & body.model_fields_set))
    session.add(agent)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(status_code=409, detail=f"Agent '{normalized_name}' already exists")
    await session.refresh(agent)

    from deerflow.config.agents_config import load_agent_config

    load_agent_config.cache_clear()

    logger.info(f"Created agent '{normalized_name}' (id={agent.id}) by user {user_id}")
    return _agent_to_response(agent)


@router.put(
    "/agents/{name}",
    response_model=AgentResponse,
    summary="Update Custom Agent",
)
async def update_agent(
    name: str,
    body: AgentUpdateRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> AgentResponse:
    _validate_agent_name(name)
    name = _normalize_agent_name(name)
    tenant_id = require_tenant_context(request)
    user_id = _get_user_id(request)

    await begin_reference_transaction(session, tenant_id)

    user_ids = [user_id]
    is_admin = _is_tenant_admin(request)
    if is_admin:
        user_ids.append("tenant-shared")

    result = await session.exec(
        sa_select(CustomAgent).where(
            CustomAgent.tenant_id == tenant_id,
            CustomAgent.user_id.in_(user_ids),
            CustomAgent.name == name,
            CustomAgent.id == body.expected_agent_id if body.expected_agent_id is not None else True,
        ).order_by(case((CustomAgent.user_id == user_id, 0), else_=1)).with_for_update()
    )
    agent = result.scalars().first()

    if agent is None:
        raise HTTPException(status_code=404, detail=f"Agent '{name}' not found")

    # Check update permissions
    if agent.user_id == "tenant-shared" and not is_admin:
        raise HTTPException(status_code=403, detail="Only tenant admins can update shared agents")
    if agent.user_id != "tenant-shared" and agent.user_id != user_id:
        raise HTTPException(status_code=403, detail="Only the agent owner can update this agent")

    if body.expected_agent_id is not None and body.expected_agent_id != agent.id:
        raise HTTPException(409, "Agent instance changed; inspect current configuration")
    if body.expected_revision is not None and body.expected_revision != _agent_revision(agent):
        raise HTTPException(409, "Agent configuration changed; inspect before saving")

    fields_set = body.model_fields_set

    # If updating shared status
    if "is_shared" in fields_set and body.is_shared is not None:
        if not is_admin:
            raise HTTPException(status_code=403, detail="Only tenant admins can share or unshare agents")
        target_user_id = "tenant-shared" if body.is_shared else user_id
        if agent.user_id != target_user_id:
            # Check for collisions in target scope
            conflict_result = await session.exec(
                sa_select(CustomAgent).where(
                    CustomAgent.tenant_id == tenant_id,
                    CustomAgent.user_id == target_user_id,
                    CustomAgent.name == name,
                )
            )
            if conflict_result.scalars().first() is not None:
                raise HTTPException(status_code=409, detail=f"Agent '{name}' already exists in that scope")
            agent.user_id = target_user_id

    if body.description is not None:
        agent.description = body.description

    # Nullable fields: use model_fields_set to distinguish "not provided" from "explicitly cleared"
    if "model" in fields_set:
        agent.model = body.model  # None → clear model override
    if "tool_groups" in fields_set:
        agent.tool_groups = body.tool_groups or []
    if "skills" in fields_set:
        agent.skills = body.skills or []
    if "tags" in fields_set:
        agent.tags = body.tags or []

    update_agent_content(agent, body)
    if body.enabled is not None:
        agent.enabled = body.enabled

    await save_binding(session, agent, tenant_id, user_id, body.skill_binding_mode, body.skill_resources,
        explicit=bool({"skill_resources", "skill_binding_mode"} & fields_set), names_changed="skills" in fields_set, scope_changed="is_shared" in fields_set)
    session.add(agent)
    await session.commit()
    await session.refresh(agent)

    from deerflow.config.agents_config import load_agent_config

    load_agent_config.cache_clear()

    logger.info(f"Updated agent '{name}' (id={agent.id}) by user {user_id}")
    return _agent_to_response(agent)


@router.delete(
    "/agents/{name}",
    status_code=204,
    summary="Delete Custom Agent",
)
async def delete_agent(
    name: str,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> None:
    _validate_agent_name(name)
    name = _normalize_agent_name(name)
    tenant_id = require_tenant_context(request)
    user_id = _get_user_id(request)

    await begin_reference_transaction(session, tenant_id)

    user_ids = [user_id]
    is_admin = _is_tenant_admin(request)
    if is_admin:
        user_ids.append("tenant-shared")

    result = await session.exec(
        sa_select(CustomAgent).where(
            CustomAgent.tenant_id == tenant_id,
            CustomAgent.user_id.in_(user_ids),
            CustomAgent.name == name,
        )
    )
    agent = result.scalars().first()

    if agent is None:
        raise HTTPException(status_code=404, detail=f"Agent '{name}' not found")

    if agent.user_id == "tenant-shared" and not is_admin:
        raise HTTPException(status_code=403, detail="Only tenant admins can delete shared agents")
    if agent.user_id != "tenant-shared" and agent.user_id != user_id:
        raise HTTPException(status_code=403, detail="Only the agent owner can delete this agent")

    # Check if any alert sources reference this agent (only when alerting plugin is enabled)
    if get_plugin_states().get("ops-alerting", True):
        from app.models.alerting import AlertSource

        ref_result = await session.exec(
            sa_select(AlertSource).where(
                AlertSource.tenant_id == tenant_id,
                AlertSource.config_json["analysis_trigger"]["diagnosis_agent_id"].as_string() == agent.id,
            )
        )
        ref_sources = ref_result.scalars().all()
        if ref_sources:
            source_names = ", ".join(s.name for s in ref_sources)
            raise HTTPException(status_code=409, detail=f"无法删除：告警源 ({source_names}) 正在使用此 Agent。请先在告警源中解除绑定后再删除。")

    await session.delete(agent)
    await session.commit()

    from deerflow.config.agents_config import load_agent_config

    load_agent_config.cache_clear()

    logger.info(f"Deleted agent '{name}' (id={agent.id}) by user {user_id}")


# ---------------------------------------------------------------------------
# Skills endpoint
# ---------------------------------------------------------------------------


@router.get(
    "/skills",
    response_model=SkillsListResponse,
    summary="List Installed Skills",
)
async def list_skills(
    request: Request,
) -> SkillsListResponse:
    require_tenant_context(request)
    _get_user_id(request)

    skills = load_skills(enabled_only=True)
    return SkillsListResponse(
        skills=[
            SkillResponse(
                name=s.name,
                description=s.description,
                category=s.category,
                enabled=s.enabled,
            )
            for s in skills
        ]
    )


# ---------------------------------------------------------------------------
# User profile endpoints (unchanged — filesystem-based)
# ---------------------------------------------------------------------------


@router.get(
    "/user-profile",
    response_model=UserProfileResponse,
    summary="Get User Profile",
)
async def get_user_profile(request: Request) -> UserProfileResponse:
    try:
        user_id = _get_user_id(request)
        tenant_id = getattr(request.state, "tenant_id", None)
        user_md_path = get_paths().user_md_file(user_id=user_id, tenant_id=tenant_id)
        if not user_md_path.exists():
            legacy_path = get_paths().user_md_file(user_id=user_id, tenant_id=None)
            if legacy_path.exists():
                user_md_path = legacy_path
        if not user_md_path.exists():
            return UserProfileResponse(content=None)
        raw = user_md_path.read_text(encoding="utf-8").strip()
        return UserProfileResponse(content=raw or None)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to read user profile: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to read user profile: {str(e)}")


@router.put(
    "/user-profile",
    response_model=UserProfileResponse,
    summary="Update User Profile",
)
async def update_user_profile(
    body: UserProfileUpdateRequest,
    request: Request,
) -> UserProfileResponse:
    try:
        user_id = _get_user_id(request)
        tenant_id = getattr(request.state, "tenant_id", None)
        paths = get_paths()
        user_md_path = paths.user_md_file(user_id=user_id, tenant_id=tenant_id)
        user_md_path.parent.mkdir(parents=True, exist_ok=True)
        user_md_path.write_text(body.content, encoding="utf-8")
        logger.info(f"Updated USER.md at {user_md_path}")
        return UserProfileResponse(content=body.content or None)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update user profile: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to update user profile: {str(e)}")
