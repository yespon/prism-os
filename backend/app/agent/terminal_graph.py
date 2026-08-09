"""
Terminal Agent Graph — LangGraph-based intelligent terminal orchestration.

Architecture:
  User Input → intent_node (LLM) → security_node → [ask_approval] → execute_node → observation_node → intent_node (loop) → END

Two modes:
  - cmd: Commands execute in the terminal (user-visible). All commands require user confirmation.
  - agent: Commands execute in background. Safe commands auto-execute, dangerous commands ask.
"""

import asyncio
import logging
import shlex
import uuid
from typing import Annotated, Any, Literal, TypedDict

from langchain_core.messages import AIMessage, AnyMessage, HumanMessage, SystemMessage, ToolMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.types import interrupt
from sqlalchemy import select as sa_select

from app.agent.terminal_tools import (
    _build_web_fetch_command,
    _build_write_file_command,
    terminal_tools_list,
)
from app.models.assets import Keychain, LocalAsset
from app.services.terminal.security import security_service
from app.services.terminal.session import build_ssh_command, session_manager
from deerflow.database.session import get_session_factory
from deerflow.models.factory import create_chat_model

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MAX_ITERATIONS = 10  # Prevent infinite loops — ~5 min of agent activity

# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------


class TerminalState(TypedDict):
    """State shared across graph nodes."""

    session_id: str
    terminal_session_id: str  # Shared PTY session ID (same for UI and agent mode)
    asset_id: str
    selected_assets: list[dict[str, Any]]
    tenant_id: str
    user_id: str
    model_name: str
    mode: Literal["cmd", "agent"]
    messages: Annotated[list[AnyMessage], add_messages]
    pending_tool_calls: list[dict[str, Any]]
    pending_approval: bool
    todos: list[dict[str, Any]]
    iteration_count: int
    cmd_post_execution_pending: bool
    skill_instructions: str


# ---------------------------------------------------------------------------
# Custom reducer for todos (replace instead of append)
# ---------------------------------------------------------------------------

def _todos_reducer(_existing: list, new: list) -> list:
    return new


def _target_assets(asset_id: str, selected_assets: list[dict[str, Any]] | None = None) -> list[dict[str, str]]:
    """Return target hosts in a UI-friendly shape for approvals and audit surfaces."""
    assets = selected_assets or []
    if assets:
        return [
            {
                "id": str(asset.get("id", "")),
                "name": str(asset.get("name") or asset.get("ip") or asset.get("hostname") or asset.get("id") or "unknown"),
                "ip": str(asset.get("ip") or asset.get("hostname") or ""),
            }
            for asset in assets
        ]
    if asset_id:
        return [{"id": asset_id, "name": asset_id, "ip": ""}]
    return []


def _format_host_context(asset_id: str, selected_assets: list[dict[str, Any]] | None = None) -> str:
    targets = _target_assets(asset_id, selected_assets)
    if not targets:
        return ""
    labels = [asset.get("ip") or asset.get("name") or asset.get("id") or "unknown" for asset in targets]
    return ", ".join(labels)


def _resolve_tool_targets(
    tool_args: dict[str, Any],
    asset_id: str,
    selected_assets: list[dict[str, Any]] | None = None
) -> list[dict[str, str]]:
    """Resolve target assets for a specific tool call based on host_index, asset_id, or defaults."""
    assets = selected_assets or []
    
    # 1. Check host_index
    host_index = tool_args.get("host_index")
    if host_index is not None:
        try:
            idx = int(host_index)
            if idx == -1:
                if assets:
                    return _target_assets("", assets)
            elif 0 <= idx < len(assets):
                return _target_assets("", [assets[idx]])
        except (ValueError, TypeError):
            pass
            
    # 2. Check asset_id
    arg_asset_id = tool_args.get("asset_id")
    if arg_asset_id:
        for a in assets:
            if str(a.get("id")) == str(arg_asset_id):
                return _target_assets("", [a])
        return [{"id": str(arg_asset_id), "name": str(arg_asset_id), "ip": ""}]

    # 3. Default fallback
    return _target_assets(asset_id, assets)


# ---------------------------------------------------------------------------
# History Trimming
# ---------------------------------------------------------------------------


def _trim_message_history(messages: list[AnyMessage], max_tokens: int = 25000) -> list[AnyMessage]:
    """Trim conversation history to fit within a token limit without orphaning ToolMessages."""
    if not messages:
        return []

    # Helper function to count tokens in a single message
    def count_msg_tokens(msg: AnyMessage) -> int:
        text = ""
        if hasattr(msg, "content") and msg.content:
            if isinstance(msg.content, str):
                text += msg.content
            elif isinstance(msg.content, list):
                for part in msg.content:
                    if isinstance(part, str):
                        text += part
                    elif isinstance(part, dict) and part.get("type") == "text":
                        text += part.get("text", "")
        if hasattr(msg, "tool_calls") and msg.tool_calls:
            import json
            try:
                text += json.dumps(msg.tool_calls)
            except Exception:
                text += str(msg.tool_calls)
        
        try:
            import tiktoken
            encoding = tiktoken.get_encoding("cl100k_base")
            return len(encoding.encode(text))
        except Exception:
            return len(text) // 4

    # Group messages into conversational blocks (excluding SystemMessage)
    blocks = []
    current_block = []
    tool_call_to_block = {}

    for msg in messages:
        if isinstance(msg, SystemMessage):
            continue
        
        is_new_block = False
        if isinstance(msg, HumanMessage):
            is_new_block = True
        elif isinstance(msg, AIMessage):
            is_new_block = True
        elif isinstance(msg, ToolMessage):
            tc_id = getattr(msg, "tool_call_id", None)
            if tc_id and tc_id in tool_call_to_block:
                block_idx = tool_call_to_block[tc_id]
                blocks[block_idx].append(msg)
                continue
            else:
                is_new_block = True

        if is_new_block:
            current_block = [msg]
            blocks.append(current_block)
            block_idx = len(blocks) - 1
            if isinstance(msg, AIMessage) and getattr(msg, "tool_calls", None):
                for tc in msg.tool_calls:
                    tc_id = tc.get("id")
                    if tc_id:
                        tool_call_to_block[tc_id] = block_idx
        else:
            if current_block:
                current_block.append(msg)
            else:
                current_block = [msg]
                blocks.append(current_block)

    # Select blocks from the end (newest first) until token budget is exceeded
    selected_blocks = []
    total_tokens = 0
    for block in reversed(blocks):
        block_tokens = sum(count_msg_tokens(msg) for msg in block)
        if total_tokens + block_tokens > max_tokens:
            if selected_blocks:
                break
        selected_blocks.append(block)
        total_tokens += block_tokens

    selected_blocks.reverse()

    # Flatten to list of messages
    trimmed = []
    for block in selected_blocks:
        trimmed.extend(block)

    # Preserve any initial SystemMessages if we filtered them out
    system_msgs = [m for m in messages if isinstance(m, SystemMessage)]
    return system_msgs + trimmed


# ---------------------------------------------------------------------------
# Graph Nodes
# ---------------------------------------------------------------------------


class TerminalAgentNodes:
    """Node implementations for the terminal agent graph."""

    # ------------------------------------------------------------------
    # Intent Node — calls LLM with tools
    # ------------------------------------------------------------------

    @staticmethod
    def _sanitize_orphaned_tool_calls(messages: list[AnyMessage]) -> list[AnyMessage]:
        """Strip tool_calls from AIMessages that lack corresponding ToolMessages in the message list.

        This prevents "insufficient tool messages following tool_calls message" errors
        from LLM providers (OpenAI, DeepSeek, etc.) when resuming a graph that was
        force-stopped (e.g., due to MAX_ITERATIONS) with orphaned tool calls.
        """
        # Collect all tool_call_ids that have a responding ToolMessage
        responded_ids: set[str] = set()
        for msg in messages:
            if isinstance(msg, ToolMessage):
                tc_id = getattr(msg, "tool_call_id", None)
                if tc_id:
                    responded_ids.add(tc_id)

        # Strip orphaned tool_calls from AIMessages
        sanitized = []
        for msg in messages:
            if isinstance(msg, AIMessage) and hasattr(msg, "tool_calls") and msg.tool_calls:
                orphaned = [tc for tc in msg.tool_calls if tc.get("id") not in responded_ids]
                if orphaned:
                    logger.warning(
                        f"[intent_node] Stripping {len(orphaned)} orphaned tool_calls "
                        f"from AIMessage (ids: {[tc.get('id') for tc in orphaned]})"
                    )
                    # Keep only tool_calls that have responses
                    valid_calls = [tc for tc in msg.tool_calls if tc.get("id") in responded_ids]
                    if valid_calls:
                        msg.tool_calls = valid_calls
                    else:
                        # No valid tool_calls remain — remove the tool_calls attribute
                        msg.tool_calls = []
            sanitized.append(msg)
        return sanitized

    @staticmethod
    async def intent_node(state: TerminalState) -> dict:
        """Call LLM with tools bound. Returns the AI's next message (text + tool calls)."""
        model_name = state.get("model_name", "gpt-4o")
        mode = state.get("mode", "cmd")
        asset_id = state.get("asset_id", "")
        selected_assets = state.get("selected_assets", [])
        todos = state.get("todos", [])
        messages = list(state.get("messages", []))
        messages = _trim_message_history(messages)

        # Sanitize orphaned tool_calls before sending to LLM
        messages = TerminalAgentNodes._sanitize_orphaned_tool_calls(messages)

        # Build model
        llm = create_chat_model(name=model_name)
        is_cmd_summary_turn = mode == "cmd" and state.get("cmd_post_execution_pending", False)
        if is_cmd_summary_turn:
            logger.info("[intent_node] CMD post-execution summary turn — binding NO tools")
            llm_with_tools = llm
        else:
            llm_with_tools = llm.bind_tools(terminal_tools_list)

        # Build system prompt (first node invocation — check if we already injected it)
        from app.agent.prompts import build_dynamic_prompt

        host_label = _format_host_context(asset_id, selected_assets)
        skill_instructions = state.get("skill_instructions", "")
        system_prompt = build_dynamic_prompt(mode=mode, asset_ip=host_label, todos=todos, skill_instructions=skill_instructions)

        # Don't prepend system message if one already exists at position 0
        if messages and isinstance(messages[0], SystemMessage):
            messages[0] = SystemMessage(content=system_prompt)
        else:
            messages.insert(0, SystemMessage(content=system_prompt))

        logger.info(f"[intent_node] Invoking LLM mode={mode} with {len(messages)} messages")

        response = await llm_with_tools.ainvoke(messages)

        pending_tool_calls = []
        if hasattr(response, "tool_calls") and response.tool_calls:
            pending_tool_calls = [
                {
                    "id": tc.get("id", ""),
                    "name": tc.get("name", ""),
                    "args": tc.get("args", {}),
                }
                for tc in response.tool_calls
            ]

        # Track iterations to prevent infinite loops
        iteration_count = state.get("iteration_count", 0) + 1
        if iteration_count > MAX_ITERATIONS:
            logger.warning(f"[intent_node] Max iterations reached ({MAX_ITERATIONS}), forcing end")
            # Strip tool_calls from the response to prevent orphaned tool calls
            # that would cause "insufficient tool messages" errors on next invocation
            if hasattr(response, "tool_calls") and response.tool_calls:
                stripped_ids = [tc.get("id") for tc in response.tool_calls]
                logger.warning(f"[intent_node] Stripping {len(stripped_ids)} tool_calls from final response: {stripped_ids}")
                response.tool_calls = []
            return {
                "messages": [response],
                "pending_tool_calls": [],
                "iteration_count": iteration_count,
                "cmd_post_execution_pending": False,
            }

        return {
            "messages": [response],
            "pending_tool_calls": pending_tool_calls,
            "iteration_count": iteration_count,
            "cmd_post_execution_pending": False,
        }

    # ------------------------------------------------------------------
    # Security Node — evaluate all pending tool calls
    # ------------------------------------------------------------------

    @staticmethod
    async def security_node(state: TerminalState) -> dict:
        """Evaluate security for all pending tool calls.

        In cmd mode: ALL tool calls → ask (require confirmation).
        In agent mode: safe → allow, dangerous → ask, blocked → block.
        """
        pending_tool_calls = state.get("pending_tool_calls", [])
        if not pending_tool_calls:
            return {}

        mode = state.get("mode", "cmd")
        tenant_id = state.get("tenant_id", "default")
        user_id = state.get("user_id", "unknown")

        # Load user security settings from database
        from app.models.terminal import TerminalSecuritySettings
        from app.services.terminal.security import DEFAULT_AUTO_APPROVAL, DEFAULT_SECURITY_CONFIG

        security_config = DEFAULT_SECURITY_CONFIG
        auto_approval = DEFAULT_AUTO_APPROVAL

        session_factory = get_session_factory()
        async with session_factory() as db:
            query = sa_select(TerminalSecuritySettings).where(
                TerminalSecuritySettings.tenant_id == tenant_id,
                TerminalSecuritySettings.user_id == user_id
            )
            result = await db.execute(query)
            settings_obj = result.scalars().first()
            if settings_obj and settings_obj.config:
                config_data = settings_obj.config
                security_config = {**DEFAULT_SECURITY_CONFIG, **config_data.get("security_config", {})}
                default_policy = DEFAULT_SECURITY_CONFIG.get("securityPolicy", {})
                saved_policy = config_data.get("security_config", {}).get("securityPolicy", {})
                security_config["securityPolicy"] = {**default_policy, **saved_policy}

                auto_approval = {**DEFAULT_AUTO_APPROVAL, **config_data.get("auto_approval", {})}
                default_actions = DEFAULT_AUTO_APPROVAL.get("actions", {})
                saved_actions = config_data.get("auto_approval", {}).get("actions", {})
                auto_approval["actions"] = {**default_actions, **saved_actions}

        selected_assets = state.get("selected_assets", [])

        # In Agent mode, if no target host is selected, return error ToolMessages immediately
        if mode == "agent" and not selected_assets:
            error_messages = []
            for tc in pending_tool_calls:
                tool_name = tc.get("name", "")
                if tool_name in {"execute_command", "read_file", "write_file", "grep_search", "web_fetch"}:
                    error_messages.append(
                        ToolMessage(
                            content="Error: No target host selected. Please select a host using @ in the chat input.",
                            tool_call_id=tc.get("id"),
                        )
                    )
            if error_messages:
                return {
                    "pending_approval": False,
                    "pending_tool_calls": [],
                    "messages": error_messages,
                }

        requires_approval = False
        blocked_results: list[dict] = []  # Track blocked tool calls to send error messages

        for tc in pending_tool_calls:
            tool_name = tc.get("name", "")
            tc_targets = _resolve_tool_targets(tc.get("args", {}), state.get("asset_id", ""), selected_assets)

            # Tools that always require approval in cmd mode
            REMOTE_TOOLS = {"execute_command", "read_file", "write_file", "grep_search", "web_fetch"}

            if tool_name == "execute_command":
                cmd = tc.get("args", {}).get("command", "")
                result = security_service.evaluate_command(cmd, mode, security_config, auto_approval)
                tc["security"] = {
                    "action": result.action,
                    "reason": result.reason,
                    "risk_level": result.risk_level,
                    "is_state_changing": result.is_state_changing,
                    "target_assets": tc_targets,
                }

                if result.action == "block":
                    logger.warning(f"[security_node] BLOCKED command: '{cmd}' — {result.reason}")
                    blocked_results.append({
                        "tool_call_id": tc["id"],
                        "tool_name": tool_name,
                        "command": cmd,
                        "reason": result.reason,
                    })
                elif result.action == "ask":
                    requires_approval = True

            elif tool_name == "write_file":
                is_auto_approved = False
                if mode == "agent" and auto_approval.get("enabled", False):
                    is_auto_approved = auto_approval.get("actions", {}).get("editFiles", False)

                if is_auto_approved:
                    tc["security"] = {
                        "action": "allow",
                        "reason": "文件修改已配置自动批准。",
                        "risk_level": "high",
                        "is_state_changing": True,
                        "target_assets": tc_targets,
                    }
                else:
                    tc["security"] = {
                        "action": "ask",
                        "reason": "写入文件会修改远程主机状态，需要确认目标路径和内容。",
                        "risk_level": "high",
                        "is_state_changing": True,
                        "target_assets": tc_targets,
                    }
                    requires_approval = True

            elif tool_name in {"read_file", "grep_search", "web_fetch"}:
                is_auto_approved = True
                if mode == "cmd":
                    is_auto_approved = False
                elif auto_approval.get("enabled", False):
                    is_auto_approved = auto_approval.get("actions", {}).get("readFiles", True)

                if is_auto_approved:
                    tc["security"] = {
                        "action": "allow",
                        "reason": "远程读取操作自动批准。",
                        "risk_level": "low",
                        "is_state_changing": False,
                        "target_assets": tc_targets,
                    }
                else:
                    tc["security"] = {
                        "action": "ask",
                        "reason": "远程读取操作需要手动确认。",
                        "risk_level": "low",
                        "is_state_changing": False,
                        "target_assets": tc_targets,
                    }
                    requires_approval = True

            elif tool_name in REMOTE_TOOLS and mode == "cmd":
                tc["security"] = {
                    "action": "ask",
                    "reason": "Command 模式下远程操作需要手动确认。",
                    "risk_level": "low",
                    "is_state_changing": False,
                    "target_assets": tc_targets,
                }
                requires_approval = True

            else:
                pass

        # If any tool was blocked, generate error ToolMessages immediately
        error_messages = []
        for blocked in blocked_results:
            error_messages.append(
                ToolMessage(
                    content=f"[SYSTEM ALERT] Command blocked: {blocked['command']}\nReason: {blocked['reason']}\n\n"
                            f"Please DO NOT try to modify the command to bypass this security check. "
                            f"Explain the situation to the user and suggest alternatives.",
                    tool_call_id=blocked["tool_call_id"],
                )
            )

        # Remove blocked calls from pending list
        blocked_ids = {b["tool_call_id"] for b in blocked_results}
        remaining_calls = [tc for tc in pending_tool_calls if tc["id"] not in blocked_ids]

        return {
            "pending_approval": requires_approval,
            "pending_tool_calls": remaining_calls,
            "messages": error_messages if error_messages else [],
        }

    # ------------------------------------------------------------------
    # Ask Approval Node — interrupt for user confirmation
    # ------------------------------------------------------------------

    @staticmethod
    def ask_approval_node(state: TerminalState) -> dict:
        """Pause execution and ask user for approval (Human-in-the-Loop via LangGraph interrupt)."""
        pending_tool_calls = state.get("pending_tool_calls", [])
        approval = interrupt({
            "type": "approval_required",
            "tool_calls": [
                {
                    "tool_call_id": tc["id"],
                    "tool_name": tc["name"],
                    "args": tc.get("args", {}),
                    "security": tc.get("security", {}),
                }
                for tc in pending_tool_calls
            ],
        })

        if not approval.get("approved"):
            # User rejected — send error ToolMessage for the rejected tool
            rejected_id = approval.get("tool_call_id", pending_tool_calls[0]["id"] if pending_tool_calls else "")
            return {
                "pending_approval": False,
                "pending_tool_calls": [],
                "messages": [
                    ToolMessage(
                        content="User rejected this command execution.",
                        tool_call_id=rejected_id,
                    )
                ],
            }

        return {"pending_approval": False}

    # ------------------------------------------------------------------
    # Execute Node — run tools via shared PTY session
    # ------------------------------------------------------------------

    @staticmethod
    async def execute_node(state: TerminalState) -> dict:
        """Execute all allowed tools.

        All modes share the same PTY session (terminal_session_id).
        In agent mode, command output is NOT broadcast to UI websockets (background execution).
        In cmd mode, command output IS broadcast to UI websockets (user can see in terminal).
        """
        pending_tool_calls = state.get("pending_tool_calls", [])
        term_session_id = state.get("terminal_session_id") or state.get("session_id")
        asset_id = state.get("asset_id", "")
        selected_assets = state.get("selected_assets", [])
        mode = state.get("mode", "cmd")

        results: list[ToolMessage] = []
        should_broadcast = (mode == "cmd")

        for tc in pending_tool_calls:
            tool_name = tc.get("name", "")
            tc_id = tc.get("id", "")
            tc_args = tc.get("args", {})

            REMOTE_TOOLS = {"execute_command", "read_file", "write_file", "grep_search", "web_fetch"}

            if tool_name in REMOTE_TOOLS:
                tc_targets = _resolve_tool_targets(tc_args, asset_id, selected_assets)
                host_results = []
                use_headers = len(tc_targets) > 1

                for target in tc_targets:
                    target_id = target.get("id", "")
                    target_name = target.get("name", "") or target.get("ip") or target_id
                    
                    # 1. Get or create session for this target
                    session = session_manager.get_or_create_session(term_session_id, target_id)
                    
                    # 2. Ensure PTY is started
                    if session.pty.fd is None:
                        logger.info(f"[execute_node] Starting PTY session {term_session_id} for asset {target_id}")
                        try:
                            session_factory = get_session_factory()
                            async with session_factory() as db:
                                asset_obj = (
                                    await db.execute(sa_select(LocalAsset).where(LocalAsset.id == target_id))
                                ).scalars().first()
                                if asset_obj:
                                    keychain = None
                                    if asset_obj.keychain_id:
                                        keychain = (
                                            await db.execute(
                                                sa_select(Keychain).where(Keychain.id == asset_obj.keychain_id)
                                            )
                                        ).scalars().first()
                                    cmd_arr, env_updates, temp_files = build_ssh_command(asset_obj, keychain)
                                    session.start(cmd=cmd_arr, env_updates=env_updates, temp_files=temp_files)
                                    await asyncio.sleep(1.0)
                        except Exception as pty_err:
                            logger.error(f"[execute_node] Failed to start PTY session for {target_id}: {pty_err}")
                            host_results.append((target_name, f"Error starting session: {pty_err}"))
                            continue

                    # 3. Execute remote command
                    if tool_name == "execute_command":
                        cmd = tc_args.get("command", "")
                        logger.info(f"[execute_node] Executing command on {target_name} (mode={mode}): {cmd}")
                        try:
                            result = await session.execute_command(cmd, broadcast=should_broadcast)
                        except Exception as e:
                            err_msg = str(e)
                            if "already executing" in err_msg and session.command_future:
                                logger.info(f"[execute_node] Waiting for previous command on {target_name} to finish...")
                                try:
                                    await asyncio.wait_for(session.command_future, timeout=25.0)
                                    result = await session.execute_command(cmd, broadcast=should_broadcast)
                                except Exception as retry_err:
                                    logger.error(f"[execute_node] Retry on {target_name} also failed: {retry_err}")
                                    result = {"stdout": "", "stderr": f"Error executing command (after retry): {str(retry_err)}", "return_code": -1}
                            else:
                                logger.error(f"[execute_node] Command execution error on {target_name}: {e}")
                                result = {"stdout": "", "stderr": f"Error executing command: {err_msg}", "return_code": -1}
                        
                        stdout = result.get("stdout", "")
                        stderr = result.get("stderr", "")
                        host_output = stdout
                        if stderr:
                            host_output = f"{stdout}\n{stderr}" if stdout else stderr
                        
                        # Write audit log for this target host
                        try:
                            session_factory = get_session_factory()
                            async with session_factory() as db:
                                from app.models.terminal import CommandAuditLog
                                audit = CommandAuditLog(
                                    id=uuid.uuid4().hex,
                                    tenant_id=state.get("tenant_id", "unknown"),
                                    user_id=state.get("user_id", "unknown"),
                                    terminal_session_id=term_session_id,
                                    asset_id=target_id,
                                    command=cmd,
                                    mode=mode,
                                    security_action="allow",
                                    stdout=result.get("stdout", ""),
                                    stderr=result.get("stderr", ""),
                                    return_code=result.get("return_code", -1),
                                )
                                db.add(audit)
                                await db.commit()
                        except Exception as audit_err:
                            logger.error(f"[execute_node] Failed to write audit log for {target_id}: {audit_err}")

                    elif tool_name == "read_file":
                        path = tc_args.get("path", "")
                        max_lines = tc_args.get("max_lines", 200)
                        cmd = f"cat {shlex.quote(path)} 2>/dev/null | head -n {int(max_lines)}"
                        logger.info(f"[execute_node] Reading file on {target_name}: {path}")
                        try:
                            result = await session.execute_command(cmd, broadcast=should_broadcast)
                            host_output = result.get("stdout", "") or "(file empty or not found)"
                        except Exception as e:
                            host_output = f"Error reading file: {str(e)}"

                    elif tool_name == "write_file":
                        path = tc_args.get("path", "")
                        content = tc_args.get("content", "")
                        cmd = _build_write_file_command(path, content)
                        logger.info(f"[execute_node] Writing file on {target_name}: {path}")
                        try:
                            result = await session.execute_command(cmd, broadcast=should_broadcast)
                            rc = result.get("return_code", -1)
                            host_output = f"File written successfully: {path}" if rc == 0 else f"Error writing file (exit code {rc}): {result.get('stdout', '')}"
                        except Exception as e:
                            host_output = f"Error writing file: {str(e)}"

                    elif tool_name == "grep_search":
                        pattern = tc_args.get("pattern", "")
                        path = tc_args.get("path", ".")
                        max_results = tc_args.get("max_results", 50)
                        cmd = f"grep -rn --color=never {shlex.quote(pattern)} {shlex.quote(path)} 2>/dev/null | head -n {int(max_results)}"
                        logger.info(f"[execute_node] Grep on {target_name}: {pattern} in {path}")
                        try:
                            result = await session.execute_command(cmd, broadcast=should_broadcast)
                            host_output = result.get("stdout", "") or "No matches found."
                        except Exception as e:
                            host_output = f"Error searching: {str(e)}"

                    elif tool_name == "web_fetch":
                        url = tc_args.get("url", "")
                        cmd = _build_web_fetch_command(url)
                        logger.info(f"[execute_node] Web fetch on {target_name}: {url}")
                        try:
                            result = await session.execute_command(cmd, broadcast=should_broadcast)
                            host_output = result.get("stdout", "") or "(no content)"
                        except Exception as e:
                            host_output = f"Error fetching URL: {str(e)}"

                    host_results.append((target_name, host_output))

                # Combine outputs
                if use_headers:
                    combined_output = ""
                    for t_name, t_out in host_results:
                        combined_output += f"=== Host: {t_name} ===\n{t_out.strip()}\n\n"
                    combined_output = combined_output.strip()
                else:
                    combined_output = host_results[0][1] if host_results else "(no execution targets)"

                results.append(ToolMessage(content=combined_output, tool_call_id=tc_id))

            elif tool_name == "ask_followup_question":
                question = tc_args.get("question", "")
                results.append(
                    ToolMessage(
                        content=f"Question displayed to user: {question}",
                        tool_call_id=tc_id,
                    )
                )

            elif tool_name in ("focus_task", "complete_task", "todo_write", "todo_read"):
                results.append(
                    ToolMessage(
                        content=f"Tool '{tool_name}' processed.",
                        tool_call_id=tc_id,
                    )
                )

            else:
                results.append(
                    ToolMessage(
                        content=f"Unknown tool '{tool_name}' — no execution handler.",
                        tool_call_id=tc_id,
                    )
                )

        # Truncate all ToolMessage contents to prevent context window overflow
        MAX_TOOL_OUTPUT_CHARS = 30000
        for msg in results:
            if hasattr(msg, "content") and isinstance(msg.content, str):
                if len(msg.content) > MAX_TOOL_OUTPUT_CHARS:
                    logger.warning(f"[execute_node] Truncating output for tool message. Original size: {len(msg.content)}")
                    msg.content = msg.content[:MAX_TOOL_OUTPUT_CHARS] + f"\n\n[输出过长已截断。总长度 {len(msg.content)} 字符，仅展示前 {MAX_TOOL_OUTPUT_CHARS} 字符。]"

        return {
            "messages": results,
            "pending_tool_calls": [],
            "cmd_post_execution_pending": mode == "cmd",
        }

    # ------------------------------------------------------------------
    # Observation Node — process results, pass through to intent for next iteration
    # ------------------------------------------------------------------

    @staticmethod
    def observation_node(state: TerminalState) -> dict:
        """Process tool outputs.

        In Agent mode: passes through so LLM can analyze and continue.
        In Command mode: still passes through but routing sends to END afterwards.
        """
        pending_tool_calls = state.get("pending_tool_calls", [])
        if pending_tool_calls:
            logger.debug(f"[observation_node] Still have pending calls: {len(pending_tool_calls)}")
        return {}


# ---------------------------------------------------------------------------
# Routing Logic
# ---------------------------------------------------------------------------


def _route_after_intent(state: TerminalState) -> str:
    """After LLM response: if there are tool calls → go to security check, else → END."""
    if state.get("pending_tool_calls"):
        return "security"
    return END


def _route_after_security(state: TerminalState) -> str:
    """After security check: if approval needed → ask_approval, elif calls remain → execute, else → END."""
    if state.get("pending_approval"):
        return "ask_approval"
    if not state.get("pending_tool_calls"):
        return END
    return "execute"


def _route_after_ask_approval(state: TerminalState) -> str:
    """After approval: if calls remain → execute, else → END (back to intent for LLM to continue)."""
    if not state.get("pending_tool_calls"):
        # Even if rejected, go back to intent so LLM can explain/recover
        return "intent"
    return "execute"


def _route_after_execute(state: TerminalState) -> str:
    """After execution: always go to observation."""
    return "observation"


def _route_after_observation(state: TerminalState) -> str:
    """Mode-aware routing after observation.

    Command mode: execution complete → intent node for post-execution summary (if pending), else → END
    Agent mode:  loop back to intent for LLM to analyze results and decide next steps,
                 UNLESS the last AIMessage had no tool calls (LLM's final summary).
    """
    mode = state.get("mode", "cmd")
    iteration_count = state.get("iteration_count", 0)

    if iteration_count > MAX_ITERATIONS:
        return END

    if mode == "cmd":
        if state.get("cmd_post_execution_pending"):
            logger.info(f"[_route_after_observation] CMD mode → intent for post-execution summary (iteration {iteration_count})")
            return "intent"
        logger.info(f"[_route_after_observation] CMD mode → END (iteration {iteration_count})")
        return END

    # Agent mode: check if the LLM actually issued tool calls
    # If the last AIMessage had no tool calls, it was a final summary → don't loop
    messages = state.get("messages", [])
    last_ai_with_tools = False
    for msg in reversed(messages):
        if isinstance(msg, AIMessage):
            if hasattr(msg, "tool_calls") and msg.tool_calls:
                last_ai_with_tools = True
            break  # Only check the most recent AIMessage

    if not last_ai_with_tools:
        logger.info("[_route_after_observation] AGENT mode → END (final summary, no tool calls)")
        return END

    # Agent mode: loop back to intent for LLM analysis and potential further actions
    logger.info(f"[_route_after_observation] AGENT mode → intent (iteration {iteration_count})")
    return "intent"


# ---------------------------------------------------------------------------
# Graph Builder
# ---------------------------------------------------------------------------


def build_terminal_graph() -> StateGraph:
    """Build the terminal agent LangGraph."""
    builder = StateGraph(TerminalState)

    # Register nodes
    builder.add_node("intent", TerminalAgentNodes.intent_node)
    builder.add_node("security", TerminalAgentNodes.security_node)
    builder.add_node("ask_approval", TerminalAgentNodes.ask_approval_node)
    builder.add_node("execute", TerminalAgentNodes.execute_node)
    builder.add_node("observation", TerminalAgentNodes.observation_node)

    # Edges
    builder.add_edge(START, "intent")

    builder.add_conditional_edges("intent", _route_after_intent, {
        "security": "security",
        END: END,
    })

    builder.add_conditional_edges("security", _route_after_security, {
        "ask_approval": "ask_approval",
        "execute": "execute",
        END: END,
    })

    builder.add_conditional_edges("ask_approval", _route_after_ask_approval, {
        "intent": "intent",
        "execute": "execute",
    })

    builder.add_conditional_edges("execute", _route_after_execute, {
        "observation": "observation",
    })

    builder.add_conditional_edges("observation", _route_after_observation, {
        "intent": "intent",
        END: END,
    })

    return builder


# ---------------------------------------------------------------------------
# Compiled Graph (singleton)
# ---------------------------------------------------------------------------

# Use in-memory checkpoint saver for development
memory = MemorySaver()
terminal_graph = build_terminal_graph().compile(checkpointer=memory, interrupt_before=["ask_approval"])  # Pause before approval node
