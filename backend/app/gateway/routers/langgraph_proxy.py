"""Authenticated browser boundary for LangGraph thread and run APIs."""

import json
import logging
import os
import re
from urllib.parse import parse_qsl, urlencode
from uuid import uuid4

import httpx
from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import select
from starlette.background import BackgroundTask
from starlette.responses import Response, StreamingResponse

from app.models.agents import CustomAgent
from app.platform.execution.trust import (
    DEFAULT_AGENT,
    ExecutionTrustError,
    ThreadBinding,
    ThreadBindingRepository,
    attach_execution_capability,
)
from deerflow.database.session import get_session_factory

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/langgraph", tags=["langgraph"])
_THREAD_ID = re.compile(r"^[A-Za-z0-9_-]{1,128}$")
_IDENTITY_KEYS = {
    "agent_id",
    "diagnosis_source_id",
    "diagnosis_source_revision",
    "diagnosis_incident_id",
    "tenant_id",
    "user_id",
    "agent_name",
    "thread_id",
    "owner_user_id",
    "owner_tenant_id",
    "prismos_execution_capability",
    "is_bootstrap",
    "prismos_action_incident_id",
    "action_incident_id",
}
_UPSTREAM = os.getenv("LANGGRAPH_API_URL", "http://langgraph:2024").rstrip("/")


async def _upstream(method: str, path: str, body: bytes | None, query: str, *, accept: str | None = None, last_event_id: str | None = None):
    """Keep the HTTP stream open until the caller finishes forwarding it."""
    client = httpx.AsyncClient(timeout=httpx.Timeout(connect=10, read=None, write=60, pool=10), trust_env=False)
    headers = {"content-type": "application/json"}
    if accept:
        headers["accept"] = accept
    if last_event_id:
        headers["last-event-id"] = last_event_id
    safe_query = urlencode([(key, value) for key, value in parse_qsl(query) if key != "token"])
    url = f"{_UPSTREAM}/{path}"
    if safe_query:
        url += f"?{safe_query}"
    try:
        response = await client.send(client.build_request(method, url, content=body, headers=headers), stream=True)
        return response, client
    except Exception:
        await client.aclose()
        raise


async def _close_upstream(response: httpx.Response, client: httpx.AsyncClient) -> None:
    await response.aclose()
    await client.aclose()


async def _forward(method: str, path: str, body: dict | None, request: Request) -> Response:
    encoded = None if body is None else json.dumps(body, separators=(",", ":")).encode()
    try:
        upstream, client = await _upstream(
            method,
            path,
            encoded,
            request.url.query,
            accept=request.headers.get("accept"),
            last_event_id=request.headers.get("last-event-id"),
        )
    except httpx.HTTPError as exc:
        logger.warning("LangGraph upstream unavailable: %s", type(exc).__name__)
        raise HTTPException(502, "LangGraph service unavailable") from exc
    headers = {"Cache-Control": "no-store"}
    for key in ("content-location", "x-request-id"):
        if value := upstream.headers.get(key):
            headers[key] = value
    content_type = upstream.headers.get("content-type", "application/json")
    if "text/event-stream" in content_type and upstream.is_success:
        stream_closed = False

        async def close_stream():
            nonlocal stream_closed
            if not stream_closed:
                stream_closed = True
                await _close_upstream(upstream, client)

        async def authorized_chunks():
            from app.gateway.file_authorization import require_current_member
            try:
                async for chunk in upstream.aiter_raw():
                    try:
                        await require_current_member(request, factory=get_session_factory())
                        parts = path.strip("/").split("/")
                        if len(parts) >= 2 and parts[0] == "threads":
                            await ThreadBindingRepository(get_session_factory()).get(parts[1], request.state.tenant_id, request.state.user_id)
                    except (HTTPException, ExecutionTrustError):
                        return
                    yield chunk
            finally:
                await close_stream()
        return StreamingResponse(
            authorized_chunks(),
            status_code=upstream.status_code,
            media_type="text/event-stream",
            headers=headers,
            background=BackgroundTask(close_stream),
        )
    try:
        content = await upstream.aread()
        from app.gateway.file_authorization import require_current_member
        await require_current_member(request, factory=get_session_factory())
        return Response(content, status_code=upstream.status_code, media_type=content_type, headers=headers)
    finally:
        await _close_upstream(upstream, client)


def _json_body(raw: bytes) -> dict:
    if len(raw) > 4 * 1024 * 1024:
        raise HTTPException(413, "LangGraph request body too large")
    try:
        body = json.loads(raw) if raw else {}
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HTTPException(400, "Invalid LangGraph JSON body") from exc
    if not isinstance(body, dict):
        raise HTTPException(400, "LangGraph body must be an object")
    return body


async def _visible_agent(tenant_id: str, user_id: str, name: str | None) -> None:
    if name is None:
        return
    if name == "terminal-agent" or not re.fullmatch(r"[A-Za-z0-9-]+", name):
        raise HTTPException(403, "Agent is unavailable")
    async with get_session_factory()() as session:
        row = (
            await session.exec(
                select(CustomAgent).where(
                    CustomAgent.tenant_id == tenant_id,
                    CustomAgent.name == name,
                    CustomAgent.enabled.is_(True),
                    (CustomAgent.user_id == user_id) | (CustomAgent.user_id == "tenant-shared"),
                )
            )
        ).first()
    if row is None:
        raise HTTPException(403, "Agent is unavailable")


async def _binding_or_legacy(
    threads: ThreadBindingRepository,
    thread_id: str,
    tenant_id: str,
    user_id: str,
    request: Request,
) -> ThreadBinding:
    existing = await threads.lookup(thread_id)
    if existing is not None:
        if existing.tenant_id != tenant_id or existing.user_id != user_id:
            raise HTTPException(404, "Thread unavailable")
        return existing
    else:
        # Existing conversations were created before server-owned bindings.
        # Claim only their owner metadata; never claim an unowned thread.
        response = await _forward("GET", f"threads/{thread_id}", None, request)
        if response.status_code != 200:
            raise HTTPException(404, "Thread unavailable")
        try:
            metadata = json.loads(response.body).get("metadata") or {}
        except (ValueError, AttributeError) as exc:
            raise HTTPException(404, "Thread unavailable") from exc
        if metadata.get("owner_user_id") != user_id or metadata.get("owner_tenant_id") != tenant_id:
            raise HTTPException(404, "Thread unavailable")
        try:
            return await threads.create(thread_id, tenant_id, user_id, legacy_claim=True)
        except ExecutionTrustError:
            return await threads.get(thread_id, tenant_id, user_id)


async def _run_body(
    body: dict,
    binding: ThreadBinding,
    tenant_id: str,
    user_id: str,
    threads: ThreadBindingRepository,
) -> dict:
    if body.get("assistant_id") != "lead_agent":
        raise HTTPException(403, "Assistant is unavailable")
    context = body.get("context") or {}
    config = body.get("config") or {}
    if not isinstance(context, dict) or not isinstance(config, dict):
        raise HTTPException(400, "Invalid run context")
    configurable = config.get("configurable") or {}
    if not isinstance(configurable, dict):
        raise HTTPException(400, "Invalid run configuration")
    requested = context.get("agent_name") or configurable.get("agent_name")
    explicitly_selected = "agent_name" in context or "agent_name" in configurable
    if requested is not None and not isinstance(requested, str):
        raise HTTPException(400, "Invalid Agent name")
    if binding.agent_name is not None:
        expected = None if binding.agent_name == DEFAULT_AGENT else binding.agent_name
        if explicitly_selected and requested != expected:
            raise HTTPException(403, "Thread Agent cannot change")
        requested = expected
    await _visible_agent(tenant_id, user_id, requested)
    if binding.agent_name is None:
        await threads.bind_agent(binding.thread_id, tenant_id, user_id, requested)
    cleaned = {key: value for key, value in context.items() if key not in _IDENTITY_KEYS}
    cleaned.update({"tenant_id": tenant_id, "user_id": user_id, "thread_id": binding.thread_id})
    if requested is not None:
        cleaned["agent_name"] = requested
    cleaned = await attach_execution_capability(cleaned)
    body["context"] = cleaned
    config_metadata = config.get("metadata") or {}
    if not isinstance(config_metadata, dict):
        raise HTTPException(400, "Invalid run configuration metadata")
    body["config"] = {
        **config,
        "configurable": {key: value for key, value in configurable.items() if key not in _IDENTITY_KEYS},
        "metadata": {key: value for key, value in config_metadata.items() if key not in _IDENTITY_KEYS},
    }
    metadata = body.get("metadata") or {}
    if not isinstance(metadata, dict):
        raise HTTPException(400, "Invalid run metadata")
    body["metadata"] = {**{key: value for key, value in metadata.items() if key not in _IDENTITY_KEYS}, "owner_user_id": user_id, "owner_tenant_id": tenant_id}
    return body


@router.api_route("/{path:path}", methods=["GET", "POST", "PATCH", "DELETE"])
async def proxy_langgraph(path: str, request: Request) -> Response:
    from app.gateway.file_authorization import require_current_member

    tenant_id, user_id = await require_current_member(request, factory=get_session_factory())
    user_id = getattr(request.state, "user_id", None)
    if not isinstance(user_id, str) or not user_id:
        raise HTTPException(401, "Authentication required")
    method = request.method
    parts = path.strip("/").split("/")
    body = _json_body(await request.body()) if method in ("POST", "PATCH") else None
    threads = ThreadBindingRepository()

    if parts[0] == "assistants":
        if method == "GET" and len(parts) >= 2 and parts[1] == "lead_agent":
            return await _forward(method, path, body, request)
        if method == "POST" and parts == ["assistants", "search"]:
            return await _forward(method, path, body, request)
        raise HTTPException(403, "Assistant operation unavailable")

    if parts == ["threads"] and method == "POST":
        assert body is not None
        if body.get("thread_id") or body.get("if_exists") or body.get("supersteps"):
            raise HTTPException(400, "Client-selected thread identity is unavailable")
        thread_id = str(uuid4())
        body["thread_id"] = thread_id
        metadata = body.get("metadata") or {}
        if not isinstance(metadata, dict):
            raise HTTPException(400, "Invalid thread metadata")
        body["metadata"] = {**{key: value for key, value in metadata.items() if key not in ("owner_user_id", "owner_tenant_id", "agent_name")}, "owner_user_id": user_id, "owner_tenant_id": tenant_id}
        response = await _forward(method, path, body, request)
        if response.status_code < 300:
            if json.loads(response.body).get("thread_id") != thread_id:
                raise HTTPException(502, "LangGraph thread identity mismatch")
            await threads.create(thread_id, tenant_id, user_id)
        return response

    if parts == ["threads", "search"] and method == "POST":
        assert body is not None
        metadata = body.get("metadata") or {}
        if not isinstance(metadata, dict):
            raise HTTPException(400, "Invalid thread search")
        body["metadata"] = {**{key: value for key, value in metadata.items() if key not in ("owner_user_id", "owner_tenant_id")}, "owner_user_id": user_id, "owner_tenant_id": tenant_id}
        response = await _forward(method, path, body, request)
        if response.status_code != 200:
            return response
        try:
            rows = json.loads(response.body)
        except ValueError:
            raise HTTPException(502, "Invalid thread search response")
        if not isinstance(rows, list):
            raise HTTPException(502, "Invalid thread search response")
        visible = []
        for row in rows:
            thread_id = row.get("thread_id") if isinstance(row, dict) else None
            if not isinstance(thread_id, str) or not _THREAD_ID.fullmatch(thread_id):
                continue
            try:
                await _binding_or_legacy(threads, thread_id, tenant_id, user_id, request)
            except HTTPException:
                continue
            visible.append(row)
        return Response(json.dumps(visible).encode(), status_code=200, media_type="application/json")

    if len(parts) >= 2 and parts[0] == "threads" and _THREAD_ID.fullmatch(parts[1]):
        thread_id = parts[1]
        binding = await _binding_or_legacy(threads, thread_id, tenant_id, user_id, request)
        if len(parts) == 2 and method == "PATCH":
            assert body is not None
            metadata = body.get("metadata") or {}
            if not isinstance(metadata, dict):
                raise HTTPException(400, "Invalid thread metadata")
            body["metadata"] = {**{key: value for key, value in metadata.items() if key not in ("owner_user_id", "owner_tenant_id", "agent_name")}, "owner_user_id": user_id, "owner_tenant_id": tenant_id}
        if len(parts) >= 3 and parts[2] == "runs" and method == "POST" and len(parts) in (3, 4) and (len(parts) == 3 or parts[3] in ("stream", "wait")):
            assert body is not None
            body = await _run_body(body, binding, tenant_id, user_id, threads)
        elif len(parts) == 3 and parts[2] == "copy" and method == "POST":
            response = await _forward(method, path, body, request)
            if response.status_code < 300:
                new_id = json.loads(response.body)["thread_id"]
                await threads.create(new_id, tenant_id, user_id)
                if binding.agent_name is not None:
                    await threads.bind_agent(new_id, tenant_id, user_id, None if binding.agent_name == DEFAULT_AGENT else binding.agent_name)
            return response
        elif len(parts) == 2 and method == "DELETE":
            response = await _forward(method, path, body, request)
            if response.status_code < 300:
                await threads.delete(thread_id, tenant_id, user_id)
            return response
        elif not (
            (method == "GET" and (len(parts) == 2 or parts[2] in ("state", "history", "stream", "runs")))
            or (method == "PATCH" and len(parts) == 2)
            or (method == "POST" and len(parts) >= 3 and parts[2] in ("state", "history"))
            or (method == "POST" and len(parts) >= 5 and parts[2] == "runs" and parts[4] in ("cancel", "join", "stream"))
        ):
            raise HTTPException(403, "Thread operation unavailable")
        return await _forward(method, path, body, request)

    raise HTTPException(403, "LangGraph operation unavailable")
