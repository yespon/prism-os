import asyncio
import fcntl
import logging
import os
import pty
import struct
import tempfile
import termios
import uuid
from collections.abc import Awaitable, Callable

from fastapi import WebSocket

from app.models.assets import Keychain, LocalAsset

logger = logging.getLogger(__name__)


def _new_command_marker() -> str:
    return f"__PRISMOS_MARKER_{uuid.uuid4().hex}__"


def _strip_command_markers(data: str) -> str:
    """Remove complete output lines containing PrismOS command markers."""
    return "".join(
        line for line in data.splitlines(keepends=True) if "__PRISMOS_MARKER_" not in line
    )

def build_ssh_command(asset: LocalAsset, keychain: Keychain | None = None) -> tuple[list[str], dict, list[str]]:
    ssh_cmd = ["ssh", "-o", "StrictHostKeyChecking=no", "-o", "UserKnownHostsFile=/dev/null", "-o", "ConnectTimeout=15", "-p", str(asset.port)]
    env_updates = {}
    temp_files = []

    if keychain:
        if keychain.type == "ssh_key":
            fd, path = tempfile.mkstemp(text=True)
            os.write(fd, keychain.value.encode('utf-8'))
            os.close(fd)
            os.chmod(path, 0o600)
            temp_files.append(path)
            ssh_cmd.extend(["-i", path])
        elif keychain.type == "password":
            fd, path = tempfile.mkstemp(text=True)
            script_content = f"#!/usr/bin/env python3\nimport sys\nsys.stdout.write({repr(keychain.value)} + '\\n')\n"
            os.write(fd, script_content.encode('utf-8'))
            os.close(fd)
            os.chmod(path, 0o700)
            temp_files.append(path)
            env_updates["SSH_ASKPASS"] = path
            env_updates["SSH_ASKPASS_REQUIRE"] = "force"
            env_updates["DISPLAY"] = "dummy:0"
            ssh_cmd.extend(["-o", "BatchMode=no"])
            
    ssh_cmd.append(f"{asset.username}@{asset.ip}")
    return ssh_cmd, env_updates, temp_files

class LocalPTY:
    def __init__(self):
        self.pid: int | None = None
        self.fd: int | None = None

    def start(self, cmd: list[str] = ["bash", "--login"], env_updates: dict = {}):
        # Fork a child process with a new PTY
        pid, fd = pty.fork()
        if pid == 0:
            # Child process: replace with command
            env = os.environ.copy()
            env["TERM"] = "xterm-256color"
            env.update(env_updates)
            try:
                os.execvpe(cmd[0], cmd, env)
            except Exception as e:
                print(f"Failed to execute {cmd}: {e}")
                os._exit(1)
        else:
            # Parent process
            self.pid = pid
            self.fd = fd
            # Set fd to non-blocking
            flags = fcntl.fcntl(fd, fcntl.F_GETFL)
            fcntl.fcntl(fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)

    def resize(self, rows: int, cols: int):
        if self.fd is not None:
            winsize = struct.pack("HHHH", rows, cols, 0, 0)
            fcntl.ioctl(self.fd, termios.TIOCSWINSZ, winsize)

    def write(self, data: str):
        if self.fd is not None:
            os.write(self.fd, data.encode("utf-8"))

    async def read_loop(self, callback: Callable[[str], Awaitable[None]]):
        loop = asyncio.get_event_loop()
        while self.fd is not None:
            try:
                # Use asyncio to read non-blocking from the fd
                data = await loop.run_in_executor(None, lambda: os.read(self.fd, 1024))
                if not data:
                    break
                await callback(data.decode("utf-8", errors="replace"))
            except BlockingIOError:
                await asyncio.sleep(0.01)
            except OSError as e:
                # EIO means EOF on some systems when PTY is closed
                if getattr(e, "errno", None) == 5:
                    break
                logger.error(f"PTY read error: {e}")
                break
            except Exception as e:
                logger.error(f"PTY loop error: {e}")
                break

    def close(self):
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None
        if self.pid is not None:
            try:
                os.kill(self.pid, 9)
                os.waitpid(self.pid, 0)
            except Exception:
                pass
            self.pid = None


class TerminalSession:
    def __init__(self, session_id: str, asset_id: str):
        self.session_id = session_id
        self.asset_id = asset_id
        self.pty: LocalPTY = LocalPTY()
        self.websockets: set[WebSocket] = set()
        self.read_task: asyncio.Task | None = None
        self.temp_files: list[str] = []
        
        # State for marker-based command execution
        self.is_executing_command = False
        self.command_output_buffer = ""
        self.command_future: asyncio.Future | None = None
        self.end_marker = ""

    async def _on_pty_output(self, data: str):
        # Buffer and detect end marker if executing command
        if self.is_executing_command and self.command_future and not self.command_future.done():
            self.command_output_buffer += data
            if self.end_marker and self.end_marker in self.command_output_buffer:
                self.command_future.set_result(self.command_output_buffer)

        # Broadcast to UI websockets only if current mode allows it
        # Agent mode (broadcast=False): do NOT send to UI, keep terminal clean
        if not getattr(self, '_current_broadcast', True):
            return

        # Filter out marker strings to keep the terminal clean
        clean_data = _strip_command_markers(data)

        if clean_data:
            dead_ws = set()
            for ws in self.websockets:
                try:
                    await ws.send_text(clean_data)
                except Exception:
                    dead_ws.add(ws)
            
            for ws in dead_ws:
                self.websockets.remove(ws)

    def start(self, cmd: list[str], env_updates: dict, temp_files: list[str]):
        self.temp_files = temp_files
        self.pty.start(cmd=cmd, env_updates=env_updates)
        self.read_task = asyncio.create_task(self.pty.read_loop(self._on_pty_output))

    def attach_websocket(self, ws: WebSocket):
        self.websockets.add(ws)

    def detach_websocket(self, ws: WebSocket):
        if ws in self.websockets:
            self.websockets.remove(ws)

    async def execute_command(self, command: str, timeout_seconds: int = 30, broadcast: bool = True) -> dict:
        """Execute a command via the PTY using markers and capture the output.
        
        Args:
            command: The shell command to execute.
            timeout_seconds: Max time to wait for completion.
            broadcast: If True (cmd mode), output is sent to UI websockets.
                       If False (agent mode), output is only captured, not broadcast.
        """
        if self.is_executing_command:
            raise Exception("A command is already executing in this session")
            
        self.is_executing_command = True
        self._current_broadcast = broadcast
        self.command_output_buffer = ""
        self.command_future = asyncio.get_event_loop().create_future()
        
        marker = _new_command_marker()
        self.end_marker = f"{marker}_END"
        
        # Write the command exactly as it is so it looks native to the user.
        # Use a clean marker format that won't leave residuals after stripping
        full_command = f"{command}\necho {self.end_marker}$?\n"
        self.pty.write(full_command)
        
        try:
            output = await asyncio.wait_for(self.command_future, timeout=timeout_seconds)
            
            # Parse output between markers
            start_idx = output.find(f"{marker}_START")
            if start_idx != -1:
                start_line_end = output.find("\n", start_idx)
                if start_line_end != -1:
                    output = output[start_line_end+1:]
            
            end_idx = output.find(self.end_marker)
            exit_code = 0
            if end_idx != -1:
                import re
                end_str = output[end_idx:]
                # Match: MARKER_END<NUMBER> (space between marker and exit code)
                match = re.search(f"{re.escape(self.end_marker)}(\\d+)", end_str)
                if match:
                    exit_code = int(match.group(1))
                output = output[:end_idx].rstrip()

            # Clean the output string to remove any marker echoes
            output = _strip_command_markers(output).strip()

            # Strip ANSI escape sequences (color codes, cursor movements, etc.)
            ansi_escape = re.compile(r'\x1b\[[0-9;]*[a-zA-Z]|\x1b\][0-9;]*[a-zA-Z]|\x1b[()][0-9AB]|\x1b\[[?][0-9;]*[hl]')
            output = ansi_escape.sub('', output)

            return {
                "stdout": output,
                "stderr": "", # PTY merges stdout and stderr
                "return_code": exit_code
            }
        except TimeoutError:
            # Need to send Ctrl+C to cancel command
            self.pty.write("\x03")
            return {
                "stdout": self.command_output_buffer,
                "stderr": f"Command timed out after {timeout_seconds} seconds",
                "return_code": -1
            }
        finally:
            self.is_executing_command = False
            self.command_future = None

    def close(self):
        self.pty.close()
        if self.read_task:
            self.read_task.cancel()
        for f in self.temp_files:
            try:
                os.remove(f)
            except OSError:
                pass


class TerminalSessionManager:
    def __init__(self):
        self.sessions: dict[str, TerminalSession] = {}

    def _get_key(self, session_id: str, asset_id: str | None) -> str:
        if asset_id:
            return f"{session_id}:{asset_id}"
        return session_id

    def get_or_create_session(self, session_id: str, asset_id: str) -> TerminalSession:
        key = self._get_key(session_id, asset_id)
        if key not in self.sessions:
            session = TerminalSession(session_id, asset_id)
            self.sessions[key] = session
        return self.sessions[key]

    def get_session(self, session_id: str, asset_id: str | None = None) -> TerminalSession | None:
        if asset_id:
            key = self._get_key(session_id, asset_id)
            return self.sessions.get(key)
        # Fallback: exact match or find any key prefix matching session_id
        if session_id in self.sessions:
            return self.sessions[session_id]
        for key, session in self.sessions.items():
            if key == session_id or key.startswith(f"{session_id}:"):
                return session
        return None

    def close_session(self, session_id: str, asset_id: str | None = None):
        if asset_id:
            key = self._get_key(session_id, asset_id)
            if key in self.sessions:
                self.sessions[key].close()
                del self.sessions[key]
        else:
            keys_to_close = [k for k in self.sessions.keys() if k == session_id or k.startswith(f"{session_id}:")]
            for key in keys_to_close:
                self.sessions[key].close()
                del self.sessions[key]

session_manager = TerminalSessionManager()
