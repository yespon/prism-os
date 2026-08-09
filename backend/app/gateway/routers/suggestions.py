import json
import logging
import os
import time
from collections import defaultdict, deque
from collections.abc import Mapping
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from langgraph_sdk import get_client
from pydantic import BaseModel, Field

from app.gateway.authorization import require_tenant_context
from deerflow.database.user_config_store import load_enabled_tenant_model_names
from deerflow.models import create_chat_model

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["suggestions"])

_RATE_LIMIT_BUCKETS: dict[str, deque[float]] = defaultdict(deque)
_RATE_LIMIT_MAX_REQUESTS = int(os.getenv("SUGGESTIONS_RATE_LIMIT_MAX_REQUESTS", "12"))
_RATE_LIMIT_WINDOW_SECONDS = int(os.getenv("SUGGESTIONS_RATE_LIMIT_WINDOW_SECONDS", "60"))
_LANGGRAPH_URL = os.getenv("LANGGRAPH_API_URL", "http://localhost:2024")
_ALLOW_LEGACY_THREADS_WITHOUT_OWNER_METADATA = (
    os.getenv("SUGGESTIONS_ALLOW_LEGACY_MISSING_OWNER_METADATA", "true").strip().lower()
    in {"1", "true", "yes", "on"}
)


class SuggestionMessage(BaseModel):
    role: str = Field(..., description="Message role: user|assistant")
    content: str = Field(..., description="Message content as plain text")


class SuggestionsRequest(BaseModel):
    messages: list[SuggestionMessage] = Field(..., description="Recent conversation messages")
    n: int = Field(default=3, ge=1, le=5, description="Number of suggestions to generate")
    model_name: str | None = Field(default=None, description="Optional model override")


class SuggestionsResponse(BaseModel):
    suggestions: list[str] = Field(default_factory=list, description="Suggested follow-up questions")


def _to_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, Mapping):
        return dict(value)
    if hasattr(value, "model_dump"):
        dumped = value.model_dump()  # type: ignore[call-arg]
        return dumped if isinstance(dumped, dict) else {}
    return {}


def _extract_thread_metadata(thread_data: Any) -> dict[str, Any]:
    payload = _to_dict(thread_data)
    if "metadata" in payload and isinstance(payload["metadata"], dict):
        return payload["metadata"]
    metadata_attr = getattr(thread_data, "metadata", None)
    if isinstance(metadata_attr, dict):
        return metadata_attr
    return {}


async def _fetch_thread_metadata(thread_id: str) -> dict[str, Any]:
    thread = await _fetch_thread(thread_id)
    return _extract_thread_metadata(thread)


async def _fetch_thread(thread_id: str) -> Any:
    client = get_client(url=_LANGGRAPH_URL)
    try:
        thread = await client.threads.get(thread_id)
    except Exception as exc:
        logger.warning(
            "suggestions_check_failed category=thread_lookup_failed thread_id=%s err=%s",
            thread_id,
            exc,
        )
        raise HTTPException(status_code=404, detail="Thread not found") from exc
    return thread


def _is_legacy_thread_without_owner_metadata(metadata: dict[str, Any]) -> bool:
    if metadata.get("owner_user_id"):
        return False
    if not _ALLOW_LEGACY_THREADS_WITHOUT_OWNER_METADATA:
        return False
    return True


def _enforce_rate_limit(*, user_id: str, thread_id: str) -> None:
    key = f"{user_id}:{thread_id}"
    now = time.monotonic()
    bucket = _RATE_LIMIT_BUCKETS[key]
    while bucket and now - bucket[0] > _RATE_LIMIT_WINDOW_SECONDS:
        bucket.popleft()
    if len(bucket) >= _RATE_LIMIT_MAX_REQUESTS:
        logger.warning(
            "suggestions_request_blocked category=rate_limited user_id=%s thread_id=%s count=%s window_seconds=%s",
            user_id,
            thread_id,
            len(bucket),
            _RATE_LIMIT_WINDOW_SECONDS,
        )
        raise HTTPException(status_code=429, detail="Suggestions rate limit exceeded")
    bucket.append(now)


async def _enforce_suggestions_access(request: Request, thread_id: str) -> None:
    require_tenant_context(request)
    user_id = getattr(request.state, "user_id", None)
    tenant_id = getattr(request.state, "tenant_id", None)
    if not isinstance(user_id, str) or not user_id.strip():
        logger.warning("suggestions_request_blocked category=auth_failed reason=missing_user_id thread_id=%s", thread_id)
        raise HTTPException(status_code=401, detail="Authentication required")

    _enforce_rate_limit(user_id=user_id, thread_id=thread_id)

    thread = await _fetch_thread(thread_id)
    metadata = _extract_thread_metadata(thread)
    owner_user_id = metadata.get("owner_user_id")
    owner_tenant_id = metadata.get("owner_tenant_id")

    if not owner_user_id:
        if _is_legacy_thread_without_owner_metadata(metadata):
            logger.info(
                "suggestions_request_allowed category=auth_compat reason=missing_owner_metadata_legacy user_id=%s tenant_id=%s thread_id=%s",
                user_id,
                tenant_id,
                thread_id,
            )
            return
        logger.warning(
            "suggestions_request_blocked category=auth_failed reason=missing_owner_metadata user_id=%s thread_id=%s",
            user_id,
            thread_id,
        )
        raise HTTPException(status_code=403, detail="Thread ownership metadata is missing")

    if owner_user_id != user_id:
        logger.warning(
            "suggestions_request_blocked category=auth_failed reason=owner_mismatch user_id=%s owner_user_id=%s thread_id=%s",
            user_id,
            owner_user_id,
            thread_id,
        )
        raise HTTPException(status_code=403, detail="Thread access denied")

    if owner_tenant_id and owner_tenant_id != tenant_id:
        logger.warning(
            "suggestions_request_blocked category=auth_failed reason=tenant_mismatch user_id=%s tenant_id=%s owner_tenant_id=%s thread_id=%s",
            user_id,
            tenant_id,
            owner_tenant_id,
            thread_id,
        )
        raise HTTPException(status_code=403, detail="Thread tenant access denied")


def _resolve_suggestions_model_name(request: Request, requested_model_name: str | None) -> str:
    """Resolve model name for suggestions under tenant enabled-model policy."""
    tenant_id = require_tenant_context(request)
    enabled_models = load_enabled_tenant_model_names(tenant_id)
    if not enabled_models:
        raise HTTPException(
            status_code=403,
            detail="No enabled tenant-assigned models are available for this tenant.",
        )

    if requested_model_name is None:
        return enabled_models[0]

    if requested_model_name not in enabled_models:
        raise HTTPException(
            status_code=403,
            detail=f"Model '{requested_model_name}' is not available for this tenant.",
        )

    return requested_model_name


def _strip_markdown_code_fence(text: str) -> str:
    stripped = text.strip()
    if not stripped.startswith("```"):
        return stripped
    lines = stripped.splitlines()
    if len(lines) >= 3 and lines[0].startswith("```") and lines[-1].startswith("```"):
        return "\n".join(lines[1:-1]).strip()
    return stripped


def _parse_json_string_list(text: str) -> list[str] | None:
    candidate = _strip_markdown_code_fence(text)
    start = candidate.find("[")
    end = candidate.rfind("]")
    if start == -1 or end == -1 or end <= start:
        return None
    candidate = candidate[start : end + 1]
    try:
        data = json.loads(candidate)
    except Exception:
        return None
    if not isinstance(data, list):
        return None
    out: list[str] = []
    for item in data:
        if not isinstance(item, str):
            continue
        s = item.strip()
        if not s:
            continue
        out.append(s)
    return out


def _extract_response_text(content: object) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and block.get("type") in {"text", "output_text"}:
                text = block.get("text")
                if isinstance(text, str):
                    parts.append(text)
        return "\n".join(parts) if parts else ""
    if content is None:
        return ""
    return str(content)


def _format_conversation(messages: list[SuggestionMessage]) -> str:
    parts: list[str] = []
    for m in messages:
        role = m.role.strip().lower()
        if role in ("user", "human"):
            parts.append(f"User: {m.content.strip()}")
        elif role in ("assistant", "ai"):
            parts.append(f"Assistant: {m.content.strip()}")
        else:
            parts.append(f"{m.role}: {m.content.strip()}")
    return "\n".join(parts).strip()


@router.post(
    "/threads/{thread_id}/suggestions",
    response_model=SuggestionsResponse,
    summary="Generate Follow-up Questions",
    description="Generate short follow-up questions a user might ask next, based on recent conversation context.",
)
async def generate_suggestions(
    thread_id: str,
    request: SuggestionsRequest,
    api_request: Request = None,
) -> SuggestionsResponse:
    model_name = request.model_name
    if api_request is not None:
        await _enforce_suggestions_access(api_request, thread_id)

    if not request.messages:
        logger.info("suggestions_request_skipped category=input_empty reason=no_messages thread_id=%s", thread_id)
        return SuggestionsResponse(suggestions=[])

    n = request.n
    conversation = _format_conversation(request.messages)
    if not conversation:
        logger.info("suggestions_request_skipped category=input_empty reason=blank_messages thread_id=%s", thread_id)
        return SuggestionsResponse(suggestions=[])

    if api_request is not None:
        model_name = _resolve_suggestions_model_name(api_request, request.model_name)

    prompt = (
        "You are generating follow-up questions to help the user continue the conversation.\n"
        f"Based on the conversation below, produce EXACTLY {n} short questions the user might ask next.\n"
        "Requirements:\n"
        "- Questions must be relevant to the conversation.\n"
        "- Questions must be written in the same language as the user.\n"
        "- Keep each question concise (ideally <= 20 words / <= 40 Chinese characters).\n"
        "- Do NOT include numbering, markdown, or any extra text.\n"
        "- Output MUST be a JSON array of strings only.\n\n"
        "Conversation:\n"
        f"{conversation}\n"
    )

    try:
        model = create_chat_model(name=model_name, thinking_enabled=False)
        response = model.invoke(prompt)
        raw = _extract_response_text(response.content)
        parsed = _parse_json_string_list(raw)
        if parsed is None:
            logger.warning(
                "suggestions_request_failed category=parse_failed thread_id=%s raw_preview=%r",
                thread_id,
                raw[:120],
            )
            return SuggestionsResponse(suggestions=[])

        suggestions = parsed
        cleaned = [s.replace("\n", " ").strip() for s in suggestions if s.strip()]
        cleaned = cleaned[:n]
        return SuggestionsResponse(suggestions=cleaned)
    except Exception as exc:
        logger.exception(
            "suggestions_request_failed category=model_failed thread_id=%s err=%s",
            thread_id,
            exc,
        )
        return SuggestionsResponse(suggestions=[])
