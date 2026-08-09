import asyncio
import json
import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy import select as sa_select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.gateway.authorization import require_tenant_context
from app.models.assets import Keychain, LocalAsset
from app.models.terminal import ChatSession, TerminalSecuritySettings, CommandAuditLog
from app.services.terminal.session import build_ssh_command, session_manager
from deerflow.database.session import get_session

logger = logging.getLogger(__name__)

router = APIRouter()

class ExecuteCommandRequest(BaseModel):
    session_id: str
    asset_id: str
    command: str
    timeout_seconds: int = 30

class ChatSessionRequest(BaseModel):
    task_id: str
    title: str = ""
    model_name: str = "gpt-4o"
    mode: str = "cmd"
    asset_id: str | None = None
    asset_ip: str | None = None
    messages: list[dict] = []

class WebFetchRequest(BaseModel):
    url: str
    prompt: str = ""
    asset_id: str
    command: str
    timeout_seconds: int = 30


def _build_web_fetch_argv(url: str) -> list[str]:
    return [
        "curl", "-sL", "--max-time", "15",
        "-H", "User-Agent: Mozilla/5.0 (compatible; PrismOS/0.2)",
        url,
    ]


@router.websocket("/ws")
async def terminal_websocket(websocket: WebSocket, asset_id: str | None = None, session_id: str | None = None, db: AsyncSession = Depends(get_session)):
    """
    WebSocket endpoint for the AI Terminal.
    Connects the frontend xterm.js to a real backend PTY shell via TerminalSessionService.
    """
    await websocket.accept()
    
    if not asset_id or not session_id:
        await websocket.send_text("asset_id and session_id are required.\r\n")
        await websocket.close(code=1008)
        return
        
    token = websocket.cookies.get("better-auth.session_token") or websocket.cookies.get("__Secure-better-auth.session_token")
    if not token:
        token = websocket.query_params.get("token")
        
    if not token:
        await websocket.send_text("Unauthorized: missing session token.\r\n")
        await websocket.close(code=1008)
        return

    from app.gateway.auth import _get_tenant_id_from_header, _resolve_tenant_id, _resolve_user_from_auth_db
    db_user = _resolve_user_from_auth_db(token)
    if not db_user:
        await websocket.send_text("Unauthorized: invalid session token.\r\n")
        await websocket.close(code=1008)
        return
        
    user_id, _, _ = db_user
    try:
        class FakeRequest:
            headers = websocket.headers
        tenant_id = await _resolve_tenant_id(user_id, _get_tenant_id_from_header(FakeRequest()))
    except Exception:
        await websocket.send_text("Unauthorized: missing or invalid tenant context.\r\n")
        await websocket.close(code=1008)
        return

    # Fetch the asset from DB and check auth
    query = sa_select(LocalAsset).where(
        LocalAsset.id == asset_id,
        LocalAsset.tenant_id == tenant_id
    )
    result = await db.execute(query)
    asset = result.scalars().first()

    if not asset:
        await websocket.send_text("Asset not found or unauthorized.\r\n")
        await websocket.close(code=1008)
        return

    session = session_manager.get_or_create_session(session_id, asset_id)
    session.attach_websocket(websocket)

    if session.pty.fd is None:
        keychain = None
        if asset.keychain_id:
            query_kc = sa_select(Keychain).where(Keychain.id == asset.keychain_id)
            res_kc = await db.execute(query_kc)
            keychain = res_kc.scalars().first()

        cmd, env_updates, temp_files = build_ssh_command(asset, keychain)
        session.start(cmd=cmd, env_updates=env_updates, temp_files=temp_files)
        
    try:
        while True:
            # Wait for user input from the frontend terminal
            data = await websocket.receive_text()
            
            # Handle JSON payloads (e.g. window resize)
            if data.startswith("{") and data.endswith("}") and "type" in data:
                try:
                    payload = json.loads(data)
                    if payload.get("type") == "resize":
                        session.pty.resize(payload.get("rows", 24), payload.get("cols", 80))
                        continue
                except json.JSONDecodeError:
                    pass
            
            # Otherwise it's raw terminal input (keystrokes)
            session.pty.write(data)
    except WebSocketDisconnect:
        logger.info("Terminal WebSocket disconnected")
    except Exception as e:
        logger.error(f"Terminal WebSocket error: {e}")
    finally:
        session.detach_websocket(websocket)


@router.post("/execute")
async def execute_command_api(req: ExecuteCommandRequest, request: Request, db: AsyncSession = Depends(get_session)):
    """
    Executes a command via the shared SSH PTY Session in the background and returns the output.
    Used by the AI Agent to run commands without spawning a new SSH connection.
    """
    tenant_id = require_tenant_context(request)
    
    query = sa_select(LocalAsset).where(
        LocalAsset.id == req.asset_id,
        LocalAsset.tenant_id == tenant_id
    )
    result = await db.execute(query)
    asset = result.scalars().first()
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found or unauthorized")
        
    session = session_manager.get_session(req.session_id, req.asset_id)
    if not session or session.pty.fd is None:
        # Start a new session if not exists
        session = session_manager.get_or_create_session(req.session_id, req.asset_id)
            
        keychain = None
        if asset.keychain_id:
            query_kc = sa_select(Keychain).where(Keychain.id == asset.keychain_id)
            res_kc = await db.execute(query_kc)
            keychain = res_kc.scalars().first()

        cmd, env_updates, temp_files = build_ssh_command(asset, keychain)
        session.start(cmd=cmd, env_updates=env_updates, temp_files=temp_files)
        
        # Wait a bit for ssh connection
        await asyncio.sleep(1.0)
        
    try:
        result = await session.execute_command(req.command, timeout_seconds=req.timeout_seconds)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/chats")
async def save_chat_session(req: ChatSessionRequest, request: Request, db: AsyncSession = Depends(get_session)):
    """Save a chat session for history persistence."""
    tenant_id = require_tenant_context(request)
    user_id = getattr(request.state, "user_id", "unknown_user")

    query = sa_select(ChatSession).where(
        ChatSession.id == req.task_id, 
        ChatSession.tenant_id == tenant_id, 
        ChatSession.user_id == user_id
    )
    result = await db.execute(query)
    session = result.scalars().first()

    if session:
        session.title = req.title or session.title
        session.model_name = req.model_name
        session.messages = req.messages
        db.add(session)
    else:
        session = ChatSession(
            id=req.task_id,
            tenant_id=tenant_id,
            user_id=user_id,
            terminal_session_id=req.task_id,
            title=req.title or "未命名会话",
            model_name=req.model_name,
            messages=req.messages,
            todos=[],
        )
        db.add(session)
        
    await db.commit()
    return {"ok": True, "session_id": req.task_id}


@router.get("/chats")
async def list_chat_sessions(request: Request, page: int = 1, limit: int = 40, db: AsyncSession = Depends(get_session)):
    """List paginated chat sessions."""
    tenant_id = require_tenant_context(request)
    user_id = getattr(request.state, "user_id", "unknown_user")
    
    query = sa_select(ChatSession).where(
        ChatSession.tenant_id == tenant_id,
        ChatSession.user_id == user_id
    ).order_by(ChatSession.updated_at.desc()).offset((page - 1) * limit).limit(limit)
    
    result = await db.execute(query)
    sessions = result.scalars().all()
    
    count_query = sa_select(func.count(ChatSession.id)).where(
        ChatSession.tenant_id == tenant_id,
        ChatSession.user_id == user_id
    )
    count_result = await db.execute(count_query)
    total = count_result.scalar_one()

    return {
        "sessions": [s.model_dump() for s in sessions],
        "total": total,
        "page": page,
    }


@router.get("/chats/{task_id}")
async def get_chat_session(task_id: str, request: Request, db: AsyncSession = Depends(get_session)):
    """Get a specific chat session by ID."""
    tenant_id = require_tenant_context(request)
    user_id = getattr(request.state, "user_id", "unknown_user")
    
    query = sa_select(ChatSession).where(
        ChatSession.id == task_id,
        ChatSession.tenant_id == tenant_id,
        ChatSession.user_id == user_id
    )
    result = await db.execute(query)
    session = result.scalars().first()
    
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session.model_dump()


@router.delete("/chats/{task_id}")
async def delete_chat_session(task_id: str, request: Request, db: AsyncSession = Depends(get_session)):
    """Delete a chat session by ID."""
    tenant_id = require_tenant_context(request)
    user_id = getattr(request.state, "user_id", "unknown_user")
    
    query = sa_select(ChatSession).where(
        ChatSession.id == task_id,
        ChatSession.tenant_id == tenant_id,
        ChatSession.user_id == user_id
    )
    result = await db.execute(query)
    session = result.scalars().first()
    
    if session:
        await db.delete(session)
        await db.commit()
        return {"ok": True}
    raise HTTPException(status_code=404, detail="Session not found")


@router.post("/web-fetch")
async def web_fetch_proxy(req: WebFetchRequest):
    """Fetch a URL from the server side and return cleaned text content.
    Uses curl internally to avoid CORS issues.
    """
    import asyncio

    url = req.url.strip()
    if not url.startswith(("http://", "https://")):
        raise HTTPException(status_code=400, detail="Invalid URL scheme")

    # Use curl with timeout to fetch the URL
    cmd = _build_web_fetch_argv(url)

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=20)
        if proc.returncode != 0:
            return {
                "ok": False,
                "error": f"curl failed: {stderr.decode('utf-8', errors='replace')[:200]}",
                "content": "",
            }
        content = stdout.decode("utf-8", errors="replace")
        # Basic HTML-to-text: strip tags
        import re
        text = re.sub(r'<script[^>]*>.*?</script>', '', content, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r'<[^>]+>', ' ', text)
        text = re.sub(r'\s+', ' ', text).strip()
        # Truncate to reasonable length
        return {
            "ok": True,
            "content": text[:10000],
            "original_length": len(content),
        }
    except TimeoutError:
        return {"ok": False, "error": "Request timed out", "content": ""}
    except Exception as e:
        return {"ok": False, "error": str(e), "content": ""}


class SecuritySettingsUpdateRequest(BaseModel):
    security_config: dict
    auto_approval: dict


@router.get("/security-settings")
async def get_security_settings(request: Request, db: AsyncSession = Depends(get_session)):
    """Get security and auto-approval settings for the current user and tenant."""
    tenant_id = require_tenant_context(request)
    user_id = getattr(request.state, "user_id", "unknown_user")

    query = sa_select(TerminalSecuritySettings).where(
        TerminalSecuritySettings.tenant_id == tenant_id,
        TerminalSecuritySettings.user_id == user_id
    )
    result = await db.execute(query)
    settings = result.scalars().first()

    from app.services.terminal.security import DEFAULT_SECURITY_CONFIG, DEFAULT_AUTO_APPROVAL

    if not settings:
        return {
            "security_config": DEFAULT_SECURITY_CONFIG,
            "auto_approval": DEFAULT_AUTO_APPROVAL,
        }

    config = settings.config or {}
    security_config = {**DEFAULT_SECURITY_CONFIG, **config.get("security_config", {})}
    default_policy = DEFAULT_SECURITY_CONFIG.get("securityPolicy", {})
    saved_policy = config.get("security_config", {}).get("securityPolicy", {})
    security_config["securityPolicy"] = {**default_policy, **saved_policy}

    auto_approval = {**DEFAULT_AUTO_APPROVAL, **config.get("auto_approval", {})}
    default_actions = DEFAULT_AUTO_APPROVAL.get("actions", {})
    saved_actions = config.get("auto_approval", {}).get("actions", {})
    auto_approval["actions"] = {**default_actions, **saved_actions}

    return {
        "security_config": security_config,
        "auto_approval": auto_approval,
    }


@router.put("/security-settings")
async def update_security_settings(req: SecuritySettingsUpdateRequest, request: Request, db: AsyncSession = Depends(get_session)):
    """Create or update security and auto-approval settings for the current user and tenant."""
    tenant_id = require_tenant_context(request)
    user_id = getattr(request.state, "user_id", "unknown_user")

    query = sa_select(TerminalSecuritySettings).where(
        TerminalSecuritySettings.tenant_id == tenant_id,
        TerminalSecuritySettings.user_id == user_id
    )
    result = await db.execute(query)
    settings = result.scalars().first()

    config_data = {
        "security_config": req.security_config,
        "auto_approval": req.auto_approval,
    }

    if settings:
        settings.config = config_data
        db.add(settings)
    else:
        settings = TerminalSecuritySettings(
            id=uuid.uuid4().hex,
            tenant_id=tenant_id,
            user_id=user_id,
            config=config_data,
        )
        db.add(settings)

    await db.commit()
    return {"ok": True}


@router.post("/security-settings/reset")
async def reset_security_settings(request: Request, db: AsyncSession = Depends(get_session)):
    """Reset security and auto-approval settings to default for the current user and tenant."""
    tenant_id = require_tenant_context(request)
    user_id = getattr(request.state, "user_id", "unknown_user")

    query = sa_select(TerminalSecuritySettings).where(
        TerminalSecuritySettings.tenant_id == tenant_id,
        TerminalSecuritySettings.user_id == user_id
    )
    result = await db.execute(query)
    settings = result.scalars().first()

    if settings:
        await db.delete(settings)
        await db.commit()

    from app.services.terminal.security import DEFAULT_SECURITY_CONFIG, DEFAULT_AUTO_APPROVAL
    return {
        "ok": True,
        "security_config": DEFAULT_SECURITY_CONFIG,
        "auto_approval": DEFAULT_AUTO_APPROVAL,
    }


@router.get("/audit-logs")
async def list_audit_logs(
    request: Request,
    page: int = 1,
    limit: int = 50,
    terminal_session_id: str | None = None,
    asset_id: str | None = None,
    db: AsyncSession = Depends(get_session)
):
    """List paginated command audit logs."""
    tenant_id = require_tenant_context(request)

    query = sa_select(CommandAuditLog).where(
        CommandAuditLog.tenant_id == tenant_id
    )
    if terminal_session_id:
        query = query.where(CommandAuditLog.terminal_session_id == terminal_session_id)
    if asset_id:
        query = query.where(CommandAuditLog.asset_id == asset_id)

    query = query.order_by(CommandAuditLog.executed_at.desc()).offset((page - 1) * limit).limit(limit)
    result = await db.execute(query)
    logs = result.scalars().all()

    count_query = sa_select(func.count(CommandAuditLog.id)).where(
        CommandAuditLog.tenant_id == tenant_id
    )
    if terminal_session_id:
        count_query = count_query.where(CommandAuditLog.terminal_session_id == terminal_session_id)
    if asset_id:
        count_query = count_query.where(CommandAuditLog.asset_id == asset_id)
    count_result = await db.execute(count_query)
    total = count_result.scalar_one()

    return {
        "logs": [log.model_dump() for log in logs],
        "total": total,
        "page": page,
        "limit": limit,
    }


# ---------------------------------------------------------------------------
# Agent Invoke Endpoint (SSE streaming for AI assistant chat)
# ---------------------------------------------------------------------------

class AgentInvokeRequest(BaseModel):
    session_id: str
    terminal_session_id: str = ""
    model_name: str = "gpt-4o"
    asset_id: str = ""
    selected_assets: list[dict] = []
    mode: str = "cmd"
    user_input: str
    skill_instructions: str = ""


def _build_approval_payload(tool_calls: list[dict]) -> dict:
    return {
        "type": "TOOL_APPROVAL_REQUIRED",
        "toolCalls": [
            {
                "toolCallId": tc.get("id", ""),
                "toolName": tc.get("name", ""),
                "args": tc.get("args", {}),
                "security": tc.get("security", {}),
            }
            for tc in tool_calls
        ],
    }


@router.post("/invoke")
async def agent_invoke(req: AgentInvokeRequest, request: Request):
    """Invoke the terminal agent graph and stream results via SSE."""
    from app.agent.terminal_graph import terminal_graph
    from app.agent.terminal_graph import TerminalState
    from langchain_core.messages import HumanMessage, AIMessage, ToolMessage
    import json as json_mod

    tenant_id = require_tenant_context(request)
    user_id = getattr(request.state, "user_id", "system")
    primary_asset_id = req.asset_id or (
        str(req.selected_assets[0].get("id", "")) if req.selected_assets else ""
    )

    async def event_stream():
        try:
            # Build the initial state
            config = {"configurable": {"thread_id": req.session_id}, "recursion_limit": 100}
            state_input: TerminalState = {
                "session_id": req.session_id,
                "terminal_session_id": req.terminal_session_id or "",
                "asset_id": primary_asset_id,
                "selected_assets": req.selected_assets or [],
                "tenant_id": tenant_id,
                "user_id": user_id,
                "model_name": req.model_name or "gpt-4o",
                "mode": req.mode,  # type: ignore
                "messages": [HumanMessage(content=req.user_input)],
                "pending_tool_calls": [],
                "pending_approval": False,
                "todos": [],
                "iteration_count": 0,
                "cmd_post_execution_pending": False,
                "skill_instructions": req.skill_instructions,
            }

            yield f"data: {json_mod.dumps({'type': 'RUN_STARTED'})}\n\n"
            seen_run_ids = set()
            intent_count = 0
            msg_id = f"msg-{req.session_id}"
            first_content = True

            if req.mode == "sandbox":
                from app.agent.sandbox_graph import sandbox_graph
                target_graph = sandbox_graph
            else:
                target_graph = terminal_graph

            async for event in target_graph.astream_events(state_input, config, version="v2"):
                kind = event.get("event", "")
                name = event.get("name", "")
                data_event = event.get("data", {})

                step_names = {
                    "intent": "正在分析问题",
                    "security": "正在检查命令风险",
                    "ask_approval": "等待用户确认",
                    "execute": "正在执行命令",
                    "observation": "正在整理结果",
                }
                if kind == "on_chain_start" and name in step_names:
                    # On second+ intent_node invocation, pre-create a new bubble before steps
                    if name == "intent":
                        intent_count += 1
                        if intent_count > 1:
                            msg_id = f"msg-{uuid.uuid4()}"
                            first_content = False
                            logger.info(f"[agent_invoke] intent_count={intent_count}: pre-creating bubble msg_id={msg_id}")
                            # Pre-create the bubble so steps go into it, not the previous one
                            yield f"data: {json_mod.dumps({'type': 'TEXT_MESSAGE_START', 'messageId': msg_id})}\n\n"
                    yield f"data: {json_mod.dumps({'type': 'STEP_STARTED', 'stepName': step_names[name], 'messageId': msg_id})}\n\n"
                elif kind == "on_chain_end" and name in step_names:
                    yield f"data: {json_mod.dumps({'type': 'STEP_FINISHED', 'stepName': step_names[name], 'messageId': msg_id})}\n\n"

                if kind in ("on_chat_model_start", "on_chat_model_stream"):
                    run_id = event.get("run_id")
                    if run_id and run_id not in seen_run_ids:
                        seen_run_ids.add(run_id)
                        # Only set msg_id for the very first model run in the stream.
                        # Subsequent runs already have a msg_id assigned by intent_count in on_chain_start.
                        if len(seen_run_ids) == 1:
                            msg_id = f"msg-{req.session_id}"

                if kind == "on_chat_model_stream":
                    chunk = data_event.get("chunk")
                    if chunk and hasattr(chunk, "content") and chunk.content:
                        raw_content = chunk.content
                        
                        # DeepSeek may return content as list [{type:'text', text:'...'}]
                        if isinstance(raw_content, list):
                            text_parts = [p.get("text", "") for p in raw_content if isinstance(p, dict) and p.get("type") == "text"]
                            raw_content = "".join(text_parts) if text_parts else ""
                        elif not isinstance(raw_content, str):
                            raw_content = str(raw_content)
                        
                        if isinstance(raw_content, str) and raw_content:
                            if first_content:
                                yield f"data: {json_mod.dumps({'type': 'TEXT_MESSAGE_START', 'messageId': msg_id})}\n\n"
                                first_content = False
                            yield f"data: {json_mod.dumps({'type': 'TEXT_MESSAGE_CONTENT', 'messageId': msg_id, 'delta': raw_content})}\n\n"

                elif kind == "on_tool_start":
                    tool_name = name or "unknown"
                    tool_call_id = data_event.get("run_id", str(uuid.uuid4()))
                    tool_input = data_event.get("input", {})
                    # Serialize input for streaming
                    input_json = json_mod.dumps(tool_input)
                    yield f"data: {json_mod.dumps({'type': 'TOOL_CALL_START', 'toolCallName': tool_name, 'toolCallId': tool_call_id, 'messageId': msg_id})}\n\n"
                    # Stream args as a single chunk
                    yield f"data: {json_mod.dumps({'type': 'TOOL_CALL_ARGS', 'toolCallId': tool_call_id, 'delta': input_json})}\n\n"
                    # Mark tool call end
                    yield f"data: {json_mod.dumps({'type': 'TOOL_CALL_END', 'toolCallId': tool_call_id})}\n\n"

                elif kind == "on_tool_end":
                    tool_output = str(data_event.get("output", ""))
                    tool_name_camel = "".join(w.capitalize() for w in (name or "unknown").split("_"))
                    yield f"data: {json_mod.dumps({'type': 'TOOL_CALL_RESULT', 'toolCallId': data_event.get('run_id', ''), 'content': tool_output, 'toolName': tool_name_camel})}\n\n"

                elif kind == "on_chat_model_end":
                    # DeepSeek (and some models) don't emit separate on_tool_start events.
                    # Tool calls are embedded in the final AIMessage's tool_calls attribute.
                    output = data_event.get("output")
                    if output and hasattr(output, "tool_calls") and output.tool_calls:
                            for tc in output.tool_calls:
                                tc_id = tc.get("id", str(uuid.uuid4()))
                                tc_name = tc.get("name", "unknown")
                                tc_args = tc.get("args", {})
                                yield f"data: {json_mod.dumps({'type': 'TOOL_CALL_START', 'toolCallName': tc_name, 'toolCallId': tc_id, 'messageId': msg_id})}\n\n"
                                yield f"data: {json_mod.dumps({'type': 'TOOL_CALL_ARGS', 'toolCallId': tc_id, 'delta': json_mod.dumps(tc_args)})}\n\n"
                                yield f"data: {json_mod.dumps({'type': 'TOOL_CALL_END', 'toolCallId': tc_id})}\n\n"

            graph_state = target_graph.get_state(config)
            if graph_state and graph_state.next and "ask_approval" in graph_state.next:
                pending = graph_state.values.get("pending_tool_calls", [])
                if pending:
                    yield f"data: {json_mod.dumps(_build_approval_payload(pending), ensure_ascii=False)}\n\n"

            # After the graph finishes, emit TOOL_CALL_RESULT for all executed ToolMessages
            state = target_graph.get_state(config)
            if state and state.values:
                msgs = state.values.get("messages", [])
                for msg in msgs:
                    if hasattr(msg, "tool_call_id") and getattr(msg, "content", "") and getattr(msg, "type", "") == "tool":
                        tc_id = getattr(msg, "tool_call_id", "")
                        if tc_id:
                            result_content = msg.content
                            if isinstance(result_content, list):
                                result_content = "".join(
                                    p.get("text", "") for p in result_content
                                    if isinstance(p, dict) and p.get("type") == "text"
                                ) or str(result_content)
                            yield f"data: {json_mod.dumps({'type': 'TOOL_CALL_RESULT', 'toolCallId': tc_id, 'content': str(result_content), 'toolName': getattr(msg, 'name', 'unknown')})}\n\n"

            yield f"data: {json_mod.dumps({'type': 'RUN_FINISHED'})}\n\n"

        except Exception as e:
            logger.error(f"[agent_invoke] Error: {e}", exc_info=True)
            yield f"data: {json_mod.dumps({'type': 'RUN_ERROR', 'message': str(e)})}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


class AgentApproveRequest(BaseModel):
    session_id: str
    tool_call_id: str
    approved: bool


@router.post("/approve")
async def agent_approve(req: AgentApproveRequest, request: Request):
    """Resume the agent graph after user approves/rejects a tool call via Human-in-the-Loop."""
    from app.agent.terminal_graph import terminal_graph
    from langgraph.types import Command
    import json as json_mod
    import uuid

    async def event_stream():
        try:
            config = {"configurable": {"thread_id": req.session_id}, "recursion_limit": 100}

            # Resume the graph with the approval decision
            approval_cmd = Command(resume={
                "approved": req.approved,
                "tool_call_id": req.tool_call_id,
            })

            seen_run_ids = set()
            # Generate a unified message bubble ID for the approval phases (execution + summary text)
            msg_id = f"msg-{uuid.uuid4()}"
            first_content = False
            approved_tool_completed = False

            # Proactively start the text message bubble
            yield f"data: {json_mod.dumps({'type': 'TEXT_MESSAGE_START', 'messageId': msg_id})}\n\n"

            async for event in terminal_graph.astream_events(approval_cmd, config, version="v2"):
                kind = event.get("event", "")
                name = event.get("name", "")
                data_event = event.get("data", {})

                step_names = {
                    "execute": "正在执行命令",
                    "observation": "正在整理结果",
                    "intent": "正在分析问题",
                }
                if kind == "on_chain_start" and name in step_names:
                    yield f"data: {json_mod.dumps({'type': 'STEP_STARTED', 'stepName': step_names[name], 'messageId': msg_id})}\n\n"
                elif kind == "on_chain_end" and name in step_names:
                    yield f"data: {json_mod.dumps({'type': 'STEP_FINISHED', 'stepName': step_names[name], 'messageId': msg_id})}\n\n"

                if kind in ("on_chat_model_start", "on_chat_model_stream"):
                    run_id = event.get("run_id")
                    if run_id and run_id not in seen_run_ids:
                        seen_run_ids.add(run_id)

                if kind == "on_chat_model_stream":
                    chunk = data_event.get("chunk")
                    if chunk and hasattr(chunk, "content") and chunk.content:
                        raw_content = chunk.content
                        if isinstance(raw_content, list):
                            text_parts = [p.get("text", "") for p in raw_content if isinstance(p, dict) and p.get("type") == "text"]
                            raw_content = "".join(text_parts) if text_parts else ""
                        elif not isinstance(raw_content, str):
                            raw_content = str(raw_content)
                        if isinstance(raw_content, str) and raw_content:
                            yield f"data: {json_mod.dumps({'type': 'TEXT_MESSAGE_CONTENT', 'messageId': msg_id, 'delta': raw_content})}\n\n"

                elif kind == "on_tool_start":
                    tool_name = name or "unknown"
                    tool_call_id = data_event.get("run_id", str(uuid.uuid4()))
                    tool_input = data_event.get("input", {})
                    input_json = json_mod.dumps(tool_input)
                    yield f"data: {json_mod.dumps({'type': 'TOOL_CALL_START', 'toolCallName': tool_name, 'toolCallId': tool_call_id, 'messageId': msg_id})}\n\n"
                    yield f"data: {json_mod.dumps({'type': 'TOOL_CALL_ARGS', 'toolCallId': tool_call_id, 'delta': input_json})}\n\n"
                    yield f"data: {json_mod.dumps({'type': 'TOOL_CALL_END', 'toolCallId': tool_call_id})}\n\n"

                elif kind == "on_tool_end":
                    tool_output = str(data_event.get("output", ""))
                    tool_name_camel = "".join(w.capitalize() for w in (name or "unknown").split("_"))
                    
                    t_call_id = data_event.get('run_id', '')
                    if not approved_tool_completed and req.tool_call_id:
                        t_call_id = req.tool_call_id
                        approved_tool_completed = True
                        logger.info(f"[agent_approve] Mapping first tool completion to approved tool_call_id: {t_call_id}")
                    
                    yield f"data: {json_mod.dumps({'type': 'TOOL_CALL_RESULT', 'toolCallId': t_call_id, 'content': tool_output, 'toolName': tool_name_camel})}\n\n"

                elif kind == "on_chat_model_end":
                    output = data_event.get("output")
                    if output and hasattr(output, "tool_calls") and output.tool_calls:
                        for tc in output.tool_calls:
                            tc_id = tc.get("id", str(uuid.uuid4()))
                            tc_name = tc.get("name", "unknown")
                            tc_args = tc.get("args", {})
                            yield f"data: {json_mod.dumps({'type': 'TOOL_CALL_START', 'toolCallName': tc_name, 'toolCallId': tc_id, 'messageId': msg_id})}\n\n"
                            yield f"data: {json_mod.dumps({'type': 'TOOL_CALL_ARGS', 'toolCallId': tc_id, 'delta': json_mod.dumps(tc_args)})}\n\n"
                            yield f"data: {json_mod.dumps({'type': 'TOOL_CALL_END', 'toolCallId': tc_id})}\n\n"

            # Graph has finished. Read the current state to find tool execution results.
            state = terminal_graph.get_state(config)
            if state and state.values:
                messages = state.values.get("messages", [])
                # Emit TOOL_CALL_RESULT for all ToolMessages
                for msg in messages:
                    if hasattr(msg, "tool_call_id") and getattr(msg, "content", "") and getattr(msg, "type", "") == "tool":
                        tc_id = getattr(msg, "tool_call_id", "")
                        if tc_id:
                            result_content = msg.content
                            if isinstance(result_content, list):
                                result_content = "".join(
                                    p.get("text", "") for p in result_content
                                    if isinstance(p, dict) and p.get("type") == "text"
                                ) or str(result_content)
                            yield f"data: {json_mod.dumps({'type': 'TOOL_CALL_RESULT', 'toolCallId': tc_id, 'content': str(result_content), 'toolName': getattr(msg, 'name', 'unknown')})}\n\n"

            # If the graph has paused at ask_approval again, emit approval payload
            graph_state = terminal_graph.get_state(config)
            if graph_state and graph_state.next and "ask_approval" in graph_state.next:
                pending = graph_state.values.get("pending_tool_calls", [])
                if pending:
                    yield f"data: {json_mod.dumps(_build_approval_payload(pending), ensure_ascii=False)}\n\n"

            yield f"data: {json_mod.dumps({'type': 'RUN_FINISHED'})}\n\n"

        except Exception as e:
            logger.error(f"[agent_approve] Error: {e}", exc_info=True)
            yield f"data: {json_mod.dumps({'type': 'RUN_ERROR', 'message': str(e)})}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
