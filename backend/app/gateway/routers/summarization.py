"""Summarization settings API router for tenant-admin settings."""

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app.gateway.authorization import require_tenant_context
from deerflow.config.summarization_config import (
    DEFAULT_KEEP_MESSAGES,
    DEFAULT_TRIGGER_MESSAGES,
    DEFAULT_TRIGGER_TOKENS,
    ContextSize,
    SummarizationConfig,
    get_summarization_config,
    set_summarization_config,
)

router = APIRouter(prefix="/api", tags=["summarization"])


# ── Response model ───────────────────────────────────────────────────────────

class ContextSizeResponse(BaseModel):
    type: str = Field(..., description="Type: tokens, messages, or fraction")
    value: int | float = Field(..., description="Value for the context size")


class SummarizationSettingsResponse(BaseModel):
    enabled: bool = Field(..., description="Whether summarization is enabled")
    trigger_tokens: int = Field(..., description="Token threshold to trigger summarization")
    trigger_messages: int = Field(..., description="Message count threshold to trigger summarization")
    keep_messages: int = Field(..., description="Number of recent messages to preserve after summarization")
    trim_tokens_to_summarize: int | None = Field(..., description="Max tokens when preparing messages for summarization")


class SummarizationSettingsUpdate(BaseModel):
    enabled: bool | None = Field(default=None, description="Enable/disable summarization")
    trigger_tokens: int | None = Field(default=None, description="Token threshold to trigger summarization")
    trigger_messages: int | None = Field(default=None, description="Message count threshold to trigger summarization")
    keep_messages: int | None = Field(default=None, description="Number of recent messages to preserve")
    trim_tokens_to_summarize: int | None = Field(default=None, description="Max tokens for summary preparation")


# ── Helpers ──────────────────────────────────────────────────────────────────

def _build_response(config: SummarizationConfig) -> SummarizationSettingsResponse:
    """Build a flat response from the current config."""
    trigger_tokens = DEFAULT_TRIGGER_TOKENS
    trigger_messages = DEFAULT_TRIGGER_MESSAGES

    triggers = config.trigger
    if isinstance(triggers, ContextSize):
        triggers = [triggers]
    if triggers:
        for t in triggers:
            tup = t.to_tuple() if isinstance(t, ContextSize) else t
            if tup[0] == "tokens":
                trigger_tokens = int(tup[1])
            elif tup[0] == "messages":
                trigger_messages = int(tup[1])

    keep = config.keep.to_tuple()
    keep_messages = int(keep[1]) if keep[0] == "messages" else DEFAULT_KEEP_MESSAGES

    return SummarizationSettingsResponse(
        enabled=config.enabled,
        trigger_tokens=trigger_tokens,
        trigger_messages=trigger_messages,
        keep_messages=keep_messages,
        trim_tokens_to_summarize=config.trim_tokens_to_summarize,
    )


# ── Endpoints ────────────────────────────────────────────────────────────────

@router.get(
    "/tenant-admin/settings/summarization",
    response_model=SummarizationSettingsResponse,
    summary="Get Summarization Settings",
    description="Retrieve current summarization (context compression) settings for the tenant.",
)
async def get_summarization_settings(request: Request) -> SummarizationSettingsResponse:
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(status_code=401, detail="Missing user context")
    require_tenant_context(request)

    config = get_summarization_config()
    return _build_response(config)


@router.put(
    "/tenant-admin/settings/summarization",
    response_model=SummarizationSettingsResponse,
    summary="Update Summarization Settings",
    description="Update summarization (context compression) settings for the tenant.",
)
async def update_summarization_settings(
    request: Request,
    body: SummarizationSettingsUpdate,
) -> SummarizationSettingsResponse:
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(status_code=401, detail="Missing user context")
    require_tenant_context(request)

    config = get_summarization_config()

    # Apply partial updates
    if body.enabled is not None:
        config.enabled = body.enabled

    # Rebuild trigger list
    trigger_tokens = body.trigger_tokens if body.trigger_tokens is not None else None
    trigger_messages = body.trigger_messages if body.trigger_messages is not None else None

    # Resolve current values for fields not being updated
    current = _build_response(config)
    if trigger_tokens is None:
        trigger_tokens = current.trigger_tokens
    if trigger_messages is None:
        trigger_messages = current.trigger_messages

    config.trigger = [
        ContextSize(type="tokens", value=trigger_tokens),
        ContextSize(type="messages", value=trigger_messages),
    ]

    if body.keep_messages is not None:
        config.keep = ContextSize(type="messages", value=body.keep_messages)

    if body.trim_tokens_to_summarize is not None:
        config.trim_tokens_to_summarize = body.trim_tokens_to_summarize

    set_summarization_config(config)

    return _build_response(config)
