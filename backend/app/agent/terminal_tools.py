"""
Terminal Agent Tools — Tools for remote host operations via PTY sessions.

These tools are injected into the lead_agent when agent_name == "terminal-agent".
They share the same TerminalSessionManager singleton for SSH PTY connections.
"""

import asyncio
import logging
import time
from typing import Optional

from langchain_core.tools import tool
from langgraph.types import interrupt

from app.services.terminal.session import session_manager
from app.models.assets import Keychain, LocalAsset
from deerflow.database.session import get_session_factory
from sqlalchemy import select as sa_select

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Tool Context — set by make_lead_agent before agent starts
# ---------------------------------------------------------------------------
_terminal_context: dict = {}


def _build_write_file_command(path: str, content: str) -> str:
    escaped = content.replace("'", "'\\''")
    return f"cat > '{path}' << 'PRISMOS_EOF'\n{escaped}\nPRISMOS_EOF"


def _build_web_fetch_command(url: str) -> str:
    return f"curl -sL --max-time 15 -H 'User-Agent: PrismOS/0.2' '{url}' 2>/dev/null | head -c 10000"


def set_terminal_context(context: dict):
    """Called by make_lead_agent to set the terminal session context."""
    global _terminal_context
    _terminal_context = context


def get_terminal_context() -> dict:
    return _terminal_context


# ---------------------------------------------------------------------------
# Session helpers
# ---------------------------------------------------------------------------

def _get_session_id() -> str:
    return _terminal_context.get("terminal_session_id", "default")


def _get_assets() -> list:
    return _terminal_context.get("selected_assets", [])


def _get_mode() -> str:
    return _terminal_context.get("mode", "cmd")


def _is_agent_mode() -> bool:
    return _get_mode() == "agent"


async def _ensure_session(asset_id: str = "") -> tuple:
    """Ensure a PTY session exists. Returns session."""
    session_id = _get_session_id()
    if not asset_id:
        assets = _get_assets()
        if assets:
            asset_id = assets[0].get("id", "") if isinstance(assets[0], dict) else getattr(assets[0], "id", "")
    if not asset_id:
        return None

    session = session_manager.get_or_create_session(session_id, asset_id)

    if session.pty.fd is None:
        logger.info(f"[terminal_tool] Starting PTY session {session_id} for asset {asset_id}")
        try:
            from app.gateway.routers.terminal import build_ssh_command
            session_factory = get_session_factory()
            async with session_factory() as db:
                asset = (
                    await db.execute(
                        sa_select(LocalAsset).where(LocalAsset.id == asset_id)
                    )
                ).scalars().first()
                if asset:
                    keychain = None
                    if asset.keychain_id:
                        keychain = (
                            await db.execute(
                                sa_select(Keychain).where(Keychain.id == asset.keychain_id)
                            )
                        ).scalars().first()
                    cmd_arr, env_updates, temp_files = build_ssh_command(asset, keychain)
                    session.start(cmd=cmd_arr, env_updates=env_updates, temp_files=temp_files)
                    await asyncio.sleep(1.0)
        except Exception as e:
            logger.error(f"[terminal_tool] Failed to start PTY session: {e}")
            return None

    return session


async def _execute_cmd_raw(command: str, session) -> dict:
    """Execute command via the raw session."""
    broadcast = not _is_agent_mode()
    try:
        result = await session.execute_command(command, broadcast=broadcast)
        return result
    except Exception as e:
        err_msg = str(e)
        if "already executing" in err_msg and session.command_future:
            logger.info(f"[terminal_tool] Waiting for previous command to finish...")
            try:
                await asyncio.wait_for(session.command_future, timeout=25.0)
                return await session.execute_command(command, broadcast=broadcast)
            except Exception as retry_err:
                return {"stdout": "", "stderr": f"Error (retry): {retry_err}", "return_code": -1}
        return {"stdout": "", "stderr": f"Error: {err_msg}", "return_code": -1}


async def _run_on_targets(op, host_index: int) -> str:
    """Run an async operation callback on resolved target host sessions and aggregate outputs."""
    assets = _get_assets()
    
    if _is_agent_mode() and not assets:
        return "Error: No target host selected. Please select a host using @ in the chat input."

    # Resolve target assets
    if host_index == -1:
        targets = assets if assets else []
    elif 0 <= host_index < len(assets):
        targets = [assets[host_index]]
    else:
        return f"Error: host_index {host_index} out of range (connected to {len(assets)} host(s))"

    if not targets:
        context_asset_id = _terminal_context.get("asset_id", "")
        if context_asset_id:
            targets = [{"id": context_asset_id, "name": context_asset_id}]
        else:
            return "Error: No execution targets available."

    results = []
    use_headers = len(targets) > 1

    for target in targets:
        target_id = target.get("id", "") if isinstance(target, dict) else getattr(target, "id", "")
        target_name = target.get("name", "") or target.get("ip") or target_id
        
        session = await _ensure_session(target_id)
        if session is None:
            results.append((target_name, "Error: No active session could be established."))
            continue
            
        try:
            out = await op(session)
        except Exception as e:
            out = f"Error during operation: {e}"
            
        results.append((target_name, out))

    if use_headers:
        combined = ""
        for t_name, t_out in results:
            combined += f"=== Host: {t_name} ===\n{t_out.strip()}\n\n"
        return combined.strip()
    else:
        return results[0][1] if results else "(no execution targets)"


# ---------------------------------------------------------------------------
# Dangerous command detection
# ---------------------------------------------------------------------------

DANGEROUS_PATTERNS = [
    "rm -rf", "rm -r", "mkfs.", "dd if=",
    ":(){ :|:& };:",   # fork bomb
    "> /dev/sda",
    "chmod 777",
    "shutdown", "reboot", "halt", "poweroff",
    "iptables -F", "iptables --flush",
    "kill -9", "killall",
    "docker rm", "docker rmi", "docker system prune",
    "git push --force",
    "DROP TABLE", "DROP DATABASE",
    "TRUNCATE",
    "ALTER TABLE",
    "DELETE FROM",
    "mv /", "cp /",
    "wget -O /", "curl -o /",
    "> /etc/", "> /boot/",
    "chown -R", "chgrp -R",
    "passwd", "usermod",
    "openssl", "certutil",
    "export ", "source ", ". /",
]


def _is_dangerous(command: str) -> bool:
    """Check if a command matches dangerous patterns."""
    cmd_lower = command.lower()
    for pattern in DANGEROUS_PATTERNS:
        if pattern.lower() in cmd_lower:
            return True
    return False


# ---------------------------------------------------------------------------
# Tool Definitions
# ---------------------------------------------------------------------------


@tool
async def execute_command(command: str, host_index: int = -1) -> str:
    """Execute a shell command on the remote host(s) via SSH.

    Use this for system administration, diagnostics, log analysis, and
    any operation that needs to run directly on the target server.

    Rules:
    - For interactive/TUI commands, use non-interactive alternatives:
      * top -> top -n 1 -b
      * htop -> htop -n 1 or use top
      * systemctl status -> systemctl status --no-pager
      * less/more -> use cat or tail
      * git log -> git log --no-pager or git log --oneline -n 20
      * journalctl -> journalctl --no-pager -n 50
      * mysql -> mysql -e "query"
      * psql -> psql -c "query"
    - Don't use commands requiring user input (passwd, adduser interactive)
    - Use head/tail to limit output for potentially large results
    - Use absolute paths; don't rely on cd

    Args:
        command: The shell command to execute.
        host_index: Index of the host (0-based) from the connected assets list. Default -1 (targets ALL connected hosts).
    """
    assets = _get_assets()
    tenant_id = _terminal_context.get("tenant_id", "default")
    user_id = _terminal_context.get("user_id", "unknown")
    mode = _get_mode()

    from app.models.terminal import TerminalSecuritySettings
    from app.services.terminal.security import DEFAULT_SECURITY_CONFIG, DEFAULT_AUTO_APPROVAL, security_service

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

    # Evaluate command safety
    sec_result = security_service.evaluate_command(command, mode, security_config, auto_approval)
    if sec_result.action == "block":
        return f"[SYSTEM ALERT] Command blocked: {command}\nReason: {sec_result.reason}\n\n" \
               f"Please DO NOT try to modify the command to bypass this security check. " \
               f"Explain the situation to the user and suggest alternatives."

    if sec_result.action == "ask":
        # Structure the target assets info for the interrupt payload
        target_assets = [{"id": a.get("id"), "ip": a.get("ip") or a.get("hostname"), "name": a.get("name")} for a in assets]
        approval = interrupt({
            "type": "tool_approval",
            "tool": "execute_command",
            "command": command,
            "reason": sec_result.reason,
            "risk_level": sec_result.risk_level,
            "is_state_changing": sec_result.is_state_changing,
            "target_assets": target_assets,
        })
        if isinstance(approval, dict) and not approval.get("approved", True):
            return "Command rejected by user — execution cancelled."
        if isinstance(approval, dict) and not approval:
            return "Command rejected by user — execution cancelled."

    async def op(session):
        res = await _execute_cmd_raw(command, session)
        stdout = res.get("stdout", "")
        stderr = res.get("stderr", "")
        output = stdout
        if stderr:
            output = f"{stdout}\n{stderr}" if stdout else stderr
        return output or "(no output)"

    return await _run_on_targets(op, host_index)


@tool
async def read_file(path: str, max_lines: int = 200, host_index: int = -1) -> str:
    """Read the contents of a file on the remote host(s).

    Args:
        path: Absolute path to the file on the remote host.
        max_lines: Maximum number of lines to read (default 200).
        host_index: Index of the host (0-based) from the connected assets list. Default -1 (targets ALL connected hosts).
    """
    import shlex
    cmd = f"cat '{path}' 2>/dev/null | head -n {max_lines}"
    
    async def op(session):
        result = await _execute_cmd_raw(cmd, session)
        if result.get("return_code", 0) != 0:
            return result.get("stderr") or "Error reading file"
        return result.get("stdout", "") or "(file empty or not found)"

    return await _run_on_targets(op, host_index)


@tool
async def write_file(path: str, content: str, host_index: int = -1) -> str:
    """Write content to a file on the remote host(s) (creates or overwrites).

    Args:
        path: Absolute path to the file on the remote host.
        content: The complete file content to write.
        host_index: Index of the host (0-based) from the connected assets list. Default -1 (targets ALL connected hosts).
    """
    cmd = _build_write_file_command(path, content)
    
    async def op(session):
        result = await _execute_cmd_raw(cmd, session)
        rc = result.get("return_code", -1)
        if rc != 0:
            return result.get("stderr") or f"Error writing file (exit code {rc}): {result.get('stdout', '')}"
        return f"File written successfully: {path}"

    return await _run_on_targets(op, host_index)


@tool
async def grep_search(pattern: str, path: str = ".", max_results: int = 50, max_size_mb: int = 10, host_index: int = -1) -> str:
    """Search for a pattern in files on the remote host(s) (recursive grep).

    Args:
        pattern: The regex or text pattern to search for.
        path: The directory or file path to search in (default: current directory).
        max_results: Maximum number of matching lines to return (default 50).
        max_size_mb: Maximum file size in MB to search (default 10). Skips files larger than this.
        host_index: Index of the host (0-based) from the connected assets list. Default -1 (targets ALL connected hosts).
    """
    import shlex
    max_size_bytes = max_size_mb * 1024 * 1024
    cmd = f"find '{path}' -type f -size -{max_size_bytes}c -exec grep -rn --color=never '{pattern}' {{}} + 2>/dev/null | head -n {max_results}"
    
    async def op(session):
        result = await _execute_cmd_raw(cmd, session)
        if result.get("return_code", 0) != 0:
            return result.get("stderr") or "Error searching pattern"
        return result.get("stdout", "") or "No matches found."

    return await _run_on_targets(op, host_index)


@tool
async def web_fetch(url: str, host_index: int = -1) -> str:
    """Fetch content from a URL via the remote host(s) (uses curl).

    Args:
        url: The URL to fetch (must start with http:// or https://).
        host_index: Index of the host (0-based) from the connected assets list. Default -1 (targets ALL connected hosts).
    """
    if not url.startswith(("http://", "https://")):
        return "Error: URL must start with http:// or https://"
    cmd = _build_web_fetch_command(url)
    
    async def op(session):
        result = await _execute_cmd_raw(cmd, session)
        if result.get("return_code", 0) != 0:
            return result.get("stderr") or "Error fetching URL"
        return result.get("stdout", "") or "(no content)"

    return await _run_on_targets(op, host_index)


# ---------------------------------------------------------------------------
# Tool collection
# ---------------------------------------------------------------------------

TERMINAL_TOOLS = [
    execute_command,
    read_file,
    write_file,
    grep_search,
    web_fetch,
]

# Backward-compat alias (used by terminal_graph.py until it's removed)
terminal_tools_list = TERMINAL_TOOLS


def get_terminal_tools() -> list:
    """Return the list of terminal tools."""
    return TERMINAL_TOOLS
