"""Per-command container lease using the configured AIO image, never global mounts."""

import os
import re
import subprocess
import time
import uuid
from pathlib import Path


def execute_container_command(runtime, image, command, skills_view, thread_data, *, env=None, validate=None, timeout=600, host_paths=None):
    if runtime != "docker":
        raise PermissionError("This container runtime has no verified scoped command lease")
    name = "prismos-scoped-command-" + uuid.uuid4().hex
    scope = name.removeprefix("prismos-scoped-command-")
    args = [
        runtime,
        "create",
        "--pull=never",
        "--name",
        name,
        "--label",
        "prismos.scoped-command=" + scope,
        "--user",
        f"{os.getuid()}:{os.getgid()}",
        "--read-only",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges",
        "--pids-limit",
        "128",
        "--memory",
        "1g",
        "--cpus",
        "2",
        "--tmpfs",
        "/tmp:rw,nosuid,nodev",
        "--tmpfs",
        "/home/agent:rw,nosuid,nodev",
        "--entrypoint",
        "/bin/bash",
        "--workdir",
        "/mnt/user-data/workspace",
        "--env",
        "HOME=/home/agent",
        "--env",
        "LANG=C.UTF-8",
    ]
    view = Path(skills_view)
    if view.resolve() != view or not view.is_dir():
        raise PermissionError("Verified container resource view unavailable")
    mounts = [(view, "/mnt/skills", True)]
    for key in ("workspace", "uploads", "outputs"):
        path = Path(thread_data[key + "_path"])
        if path.resolve() != path or not path.is_dir():
            raise PermissionError("Owned container thread directory unavailable")
        mounts.append((path, "/mnt/user-data/" + key, False))
    for path, target, readonly in mounts:
        source = (host_paths or {}).get(str(path), str(path))
        spec = f"type=bind,source={source},target={target}" + (",readonly" if readonly else "")
        if "," in str(source):
            raise PermissionError("Container mount path contains an unsupported delimiter")
        args += ["--mount", spec]
    environment = dict(os.environ)
    for key, value in (env or {}).items():
        if not re.fullmatch(r"[A-Z_][A-Z0-9_]*", key) or key in {"LD_PRELOAD", "LD_LIBRARY_PATH", "BASH_ENV", "ENV", "PATH", "PYTHONPATH", "PYTHONHOME"}:
            raise PermissionError("Container command environment unavailable")
        environment[key] = value
        args += ["--env", key]  # Values never enter process arguments or command logs.
    args += [image, "--noprofile", "--norc", "-c", command]
    process = None
    owned = False
    attempted = False
    try:
        if validate:
            validate()
        attempted = True
        created = subprocess.run(args, env=environment, capture_output=True, text=True, timeout=30)
        if created.returncode or not re.fullmatch(r"[0-9a-f]{64}\n?", created.stdout):
            raise PermissionError("Configured scoped container could not be created; inspect runtime configuration")
        owned = True
        if validate:
            validate()
        process = subprocess.Popen([runtime, "start", "--attach", name], stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        started = time.monotonic()
        while True:
            try:
                stdout, stderr = process.communicate(timeout=0.25)
                break
            except subprocess.TimeoutExpired:
                if time.monotonic() - started >= timeout:
                    raise TimeoutError("Scoped container timed out; inspect outputs and external effects")
                if validate:
                    validate()
        if validate:
            validate()
        output = stdout + (("\nStd Error:\n" if stdout else "") + stderr if stderr else "")
        if process.returncode:
            output += f"\nExit Code: {process.returncode}"
        return output or "(no output)"
    finally:
        if attempted and not owned:
            # A create reply can be lost after the daemon committed. Only this
            # unique lease label can authorize cleanup of the discovered name.
            inspected = subprocess.run([runtime, "inspect", "--format", '{{index .Config.Labels "prismos.scoped-command"}}', name], capture_output=True, text=True, timeout=30)
            if inspected.returncode == 0:
                if inspected.stdout.strip() != scope:
                    raise PermissionError("Unknown container ownership; cleanup refused")
                owned = True
            elif "No such" not in inspected.stderr:
                raise PermissionError("Container creation result is unknown; inspect runtime")
        if owned:
            cleanup = subprocess.run([runtime, "rm", "--force", name], capture_output=True, timeout=30)
            if cleanup.returncode:
                raise PermissionError("Scoped container termination is unconfirmed; inspect runtime and external effects")
        if process is not None:
            process.communicate(timeout=30)
