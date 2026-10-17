"""Start only the owned loopback analytics target in the existing private native profile."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import time

import httpx

from octop_wsl_native_env import NATIVE, ROOT, settled_process_identity


def prepare(output):
    assert not output.exists()
    state = NATIVE / "analytics-service"
    assert not state.exists(), "Existing owned target must be inspected, not replaced"
    with socket.socket() as sock:
        assert sock.connect_ex(("127.0.0.1", 18041)) != 0, (
            "Target port already occupied"
        )
    state.mkdir(mode=0o700)
    token = secrets.token_urlsafe(40)
    (state / "token").write_text(token)
    (state / "token").chmod(0o600)
    env = dict(os.environ, PRISMOS_ANALYTICS_STATE=str(state))
    command = [
        str(ROOT / "backend/.venv/bin/python"),
        str(ROOT / "scripts/octop_mcp_analytics_service.py"),
    ]
    with (state / "server.log").open("wb") as log:
        proc = subprocess.Popen(
            command,
            cwd=ROOT,
            env=env,
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    (state / "server.log").chmod(0o600)
    owned = {
        "pid": proc.pid,
        **settled_process_identity(proc, command),
        "nonce": secrets.token_hex(16),
        "command": command,
    }
    (state / "ownership.json").write_text(json.dumps(owned, indent=2) + "\n")
    (state / "ownership.json").chmod(0o600)
    with httpx.Client(trust_env=False, timeout=15) as c:
        for _ in range(100):
            assert proc.poll() is None, "Owned target exited; private log retained"
            try:
                if c.get("http://127.0.0.1:18041/health").status_code == 200:
                    break
            except httpx.TransportError:
                pass
            time.sleep(0.2)
        else:
            raise RuntimeError("Owned target readiness timeout")
        assert c.get("http://127.0.0.1:18041/stats").status_code == 401
        c.headers["Authorization"] = "Bearer " + token
        assert c.get("http://127.0.0.1:18041/stats").json()["completed_tool_calls"] == 0
    fixture = json.loads((NATIVE / "live-fixture.json").read_text())
    account = fixture["users"]["requester"]
    with httpx.Client(
        base_url="http://127.0.0.1:18036",
        headers={"X-Tenant-Id": fixture["tenant_id"]},
        trust_env=False,
        timeout=30,
    ) as c:
        response = c.post(
            "/api/auth/login",
            json={"email": account["email"], "password": account["password"]},
        )
        assert response.status_code == 200
        c.headers["Authorization"] = "Bearer " + response.json()["session"]["token"]
        before = c.get("/api/mcp/config")
        assert before.status_code == 200
        original = before.json()
        (state / "mcp-before.json").write_text(json.dumps(original))
        (state / "mcp-before.json").chmod(0o600)
        server_name = "owned_analytics_" + secrets.token_hex(4)
        updated = {
            "mcp_servers": {
                **original["mcp_servers"],
                server_name: {
                    "enabled": True,
                    "type": "http",
                    "url": "http://127.0.0.1:18041/mcp",
                    "headers": {"Authorization": "Bearer " + token},
                    "description": "Owned read-only CSV/SQLite revenue analysis test target",
                },
            }
        }
        response = c.put("/api/mcp/config", json=updated)
        assert response.status_code == 200, (
            "Configure native target",
            response.status_code,
        )
    (state / "binding.json").write_text(
        json.dumps(
            {
                "server_name": server_name,
                "user_id": account["id"],
                "tenant_id": fixture["tenant_id"],
            }
        )
    )
    (state / "binding.json").chmod(0o600)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(
            {
                "complete": True,
                "scope": "owned loopback native-profile target only",
                "url": "http://127.0.0.1:18041/mcp",
                "server_name": server_name,
                "process": owned,
                "service_source_sha256": hashlib.sha256(
                    Path(command[1]).read_bytes()
                ).hexdigest(),
                "anonymous_stats_denied": True,
                "real_tool_calls_at_start": 0,
                "main_config_unchanged": True,
            },
            indent=2,
        )
        + "\n"
    )
    print("Owned native MCP target ready and configured; no token exported")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    prepare(parser.parse_args().output)
