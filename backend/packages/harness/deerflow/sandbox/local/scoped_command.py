"""Kernel filesystem/PID isolation for a host-authorized local command view."""

import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path


def execute_scoped_command(command, skills_view, thread_data, *, env=None, validate=None, timeout=600):
    executable = shutil.which("bwrap")
    if executable is None:
        raise PermissionError("Scoped local commands require bubblewrap and working user namespaces")
    view = Path(skills_view).resolve(strict=True)
    if view.is_symlink() or not view.is_dir():
        raise PermissionError("Verified Skill view unavailable")
    args = [executable, "--unshare-user", "--unshare-all", "--share-net", "--disable-userns", "--die-with-parent", "--new-session", "--cap-drop", "ALL", "--ro-bind", "/usr", "/usr"]
    for name in ("bin", "sbin", "lib", "lib64"):
        source = Path("/") / name
        if source.exists():
            if source.is_symlink():
                args += ["--symlink", os.readlink(source), "/" + name]
            else:
                args += ["--ro-bind", str(source), "/" + name]
    args += ["--proc", "/proc", "--dev", "/dev", "--tmpfs", "/tmp", "--dir", "/home/agent", "--ro-bind", str(view), "/mnt/skills"]
    for name in ("workspace", "uploads", "outputs"):
        path = Path(thread_data[name + "_path"])
        if path.resolve() != path or not path.is_dir():
            raise PermissionError("Owned thread directory unavailable")
        args += ["--bind", str(path), "/mnt/user-data/" + name]
    # System resolver and CA files are public runtime data, never host home,
    # application configuration, service credentials, or the original Skill root.
    for path in ("/etc/resolv.conf", "/etc/hosts", "/etc/nsswitch.conf", "/etc/ssl/certs"):
        if Path(path).exists():
            args += ["--ro-bind", path, path]
    base = Path(sys.base_prefix).resolve()
    packages = Path(sys.prefix) / "lib" / f"python{sys.version_info.major}.{sys.version_info.minor}" / "site-packages"
    args += ["--ro-bind", str(base), "/opt/prismos-python"]
    if packages.is_dir():
        args += ["--ro-bind", str(packages), "/opt/prismos-packages", "--setenv", "PYTHONPATH", "/opt/prismos-packages"]
    node = shutil.which("node")
    if node:
        args += ["--ro-bind", str(Path(node).resolve()), "/opt/prismos-bin/node"]
        npm = shutil.which("npm")
        if npm:
            package = Path(npm).resolve().parent.parent
            if (package / "bin/npm-cli.js").is_file():
                args += ["--ro-bind", str(package), "/opt/prismos-npm", "--symlink", "/opt/prismos-npm/bin/npm-cli.js", "/opt/prismos-bin/npm"]
                if (package / "bin/npx-cli.js").is_file():
                    args += ["--symlink", "/opt/prismos-npm/bin/npx-cli.js", "/opt/prismos-bin/npx"]
    command_env = {}
    for key, value in {"PATH": "/opt/prismos-python/bin:/opt/prismos-bin:/usr/local/bin:/usr/bin:/bin", "HOME": "/home/agent", "LANG": "C.UTF-8", **(env or {})}.items():
        if key in {"LD_PRELOAD", "LD_LIBRARY_PATH", "PYTHONPATH", "PYTHONHOME", "PATH", "BASH_ENV", "ENV"} and key in (env or {}):
            raise PermissionError("Command environment cannot alter the isolation runtime")
        command_env[key] = value
    args += ["--chdir", "/mnt/user-data/workspace", "--", "/bin/bash", "--noprofile", "--norc", "-c", command]
    if validate:
        validate()
    process = subprocess.Popen(args, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, start_new_session=True, env=command_env)
    started = time.monotonic()
    try:
        while True:
            try:
                stdout, stderr = process.communicate(timeout=0.25)
                break
            except subprocess.TimeoutExpired:
                if time.monotonic() - started >= timeout:
                    raise TimeoutError("Scoped command timed out; external effects require inspection")
                if validate:
                    validate()
        if validate:
            validate()
        output = stdout
        if stderr:
            output += ("\nStd Error:\n" if output else "") + stderr
        if process.returncode:
            output += f"\nExit Code: {process.returncode}"
        return output or "(no output)"
    finally:
        if process.poll() is None:
            # The bwrap PID namespace supervisor owns descendants, including
            # children which detach from their process group inside that namespace.
            os.killpg(process.pid, signal.SIGKILL)
            process.communicate()
