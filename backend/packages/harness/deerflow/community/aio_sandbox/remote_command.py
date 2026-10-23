"""Finite remote command leases; unknown submissions are inspected, never replayed."""

import hashlib
import json
import os
import re
import time
import uuid
from pathlib import Path
from urllib.parse import urlsplit

import requests


def execute_remote_command(url, token_env, shared_root, command, skills_view, thread_data, *, env=None, validate=None, timeout=600):
    parsed = urlsplit(url)
    if parsed.scheme not in {"https", "http"} or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise PermissionError("Scoped provisioner URL is invalid")
    if parsed.scheme != "https" and parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
        raise PermissionError("Remote scoped commands require HTTPS")
    if not isinstance(token_env, str) or not re.fullmatch(r"[A-Z_][A-Z0-9_]*", token_env):
        raise PermissionError("Scoped provisioner credential reference is unavailable")
    token = os.environ.get(token_env, "")
    if not 32 <= len(token) <= 4096 or "\n" in token or "\r" in token:
        raise PermissionError("Scoped provisioner credential is unavailable")
    root = Path(shared_root)
    if not root.is_absolute() or root == Path("/") or root.resolve() != root or not root.is_dir():
        raise PermissionError("Scoped shared filesystem is unavailable")
    mounts = {}
    for kind in ("skills", "workspace", "uploads", "outputs"):
        path = Path(skills_view if kind == "skills" else thread_data[kind + "_path"])
        if not path.is_absolute() or path.resolve() != path or not path.is_dir():
            raise PermissionError("Scoped remote directory is unavailable")
        try:
            relative = path.relative_to(root)
        except ValueError:
            raise PermissionError("Scoped remote directory is outside the configured shared root") from None
        if relative == Path("."):
            raise PermissionError("Scoped remote directory cannot be the shared root")
        mounts[kind] = relative.as_posix()
    lease_id = uuid.uuid4().hex
    body = {"lease_id": lease_id, "command": command, "mounts": mounts, "environment": env or {}, "timeout": timeout, "uid": os.getuid(), "gid": os.getgid()}
    digest = hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()).hexdigest()
    endpoint = url.rstrip("/") + "/api/scoped-commands"
    headers = {"Authorization": "Bearer " + token, "X-Prismos-Contract": digest}
    session = requests.Session()
    session.trust_env = False
    attempted = False

    def request(method, suffix, **kwargs):
        try:
            response = session.request(method, endpoint + suffix, headers=headers, timeout=(3, 3), allow_redirects=False, **kwargs)
            if response.status_code not in {200, 201}:
                raise PermissionError("Remote command state is unconfirmed; inspect owned outputs and external effects")
            data = response.json()
        except (requests.RequestException, ValueError):
            raise PermissionError("Remote command state is unconfirmed; inspect the existing lease") from None
        if not isinstance(data, dict) or data.get("lease_id") != lease_id or data.get("contract") != digest:
            raise PermissionError("Remote command ownership is unconfirmed")
        return data

    try:
        if validate:
            validate()
        attempted = True
        request("POST", "", json=body)
        started = time.monotonic()
        while True:
            if validate:
                validate()
            result = request("GET", "/" + lease_id)
            if validate:
                validate()
            if result.get("status") == "completed":
                output, code = result.get("output"), result.get("returncode")
                if not isinstance(output, str) or type(code) is not int or len(output.encode()) > 1024 * 1024:
                    raise PermissionError("Remote command result is unavailable")
                return (output + (f"\nExit Code: {code}" if code else "")) or "(no output)"
            if result.get("status") != "running":
                raise PermissionError("Remote command termination is unconfirmed")
            if time.monotonic() - started >= timeout:
                raise TimeoutError("Remote command timed out; inspect owned outputs and external effects")
            time.sleep(0.25)
    finally:
        try:
            if attempted:
                deadline = time.monotonic() + 15
                while True:
                    result = request("DELETE", "/" + lease_id)
                    if result.get("terminated") is True:
                        break
                    if time.monotonic() >= deadline:
                        raise PermissionError("Remote command termination is unconfirmed; inspect runtime and external effects")
                    time.sleep(0.25)
        finally:
            session.close()
