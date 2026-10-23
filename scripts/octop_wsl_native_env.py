"""Owned WSL native test profile; preserve Docker isolation and the running main stack."""

import argparse
import hashlib
import json
import os
import secrets
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
import yaml
from dotenv import dotenv_values
from sqlalchemy.engine import make_url

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / "backend/tmp/n04-wsl"
NATIVE = STATE / "native-profile"
POSTGRES = "prismos-n04-wsl-postgres-1"


def private(path, data):
    path.write_bytes(data)
    path.chmod(0o600)


def process_identity(pid):
    value = Path("/proc") / str(pid)
    return {"starttime": (value / "stat").read_text().split(") ", 1)[1].split()[19], "cmdline_sha256": hashlib.sha256((value / "cmdline").read_bytes()).hexdigest()}


def settled_process_identity(process, command):
    """Popen can return before exec; persist identity only after exact argv appears."""
    expected = b"\x00".join(os.fsencode(x) for x in command) + b"\x00"
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError("Native process exited before its identity settled")
        try:
            actual = (Path("/proc") / str(process.pid) / "cmdline").read_bytes()
            if actual == expected:
                return process_identity(process.pid)
        except FileNotFoundError:
            pass
        time.sleep(0.01)
    raise RuntimeError("Native process argv did not match the owned launch command")


def runtime_environment():
    environment = {
        **os.environ,
        **{k: v for k, v in dotenv_values(STATE / "runtime.env").items() if v is not None},
        "PRISMOS_CONFIG_PATH": str(NATIVE / "config.yaml"),
        "PRISMOS_HOME": str(NATIVE / "home"),
        "PRISMOS_RUNTIME_ADAPTER_MODULE": "app.runtime_adapters",
        "PRISMOS_GOVERNED_TICKET_ACTION": "off",
        "PRISMOS_TRUSTED_GRAPH_CONTEXT": "off",
        "LANGGRAPH_API_URL": "http://127.0.0.1:18034",
        "LANGCHAIN_TRACING_V2": "false",
        "CORS_ORIGINS": "http://localhost:18036,http://127.0.0.1:18036",
        "SSL_CERT_FILE": str(STATE / "ca-bundle.crt"),
        "PYTHONPATH": str(ROOT / "backend"),
    }
    # Map secret-reference key files from the owned existing mounts, never print env.
    appinfo = json.loads(subprocess.check_output(["docker", "inspect", "prismos-n04-wsl-gateway-1"], text=True))[0]
    mapping = {m["Destination"]: m["Source"] for m in appinfo["Mounts"]}
    for item in appinfo["Config"]["Env"]:
        key, value = item.split("=", 1)
        if key.startswith("PRISMOS_") and ("SECRET" in key or "MASTER_KEY" in key):
            environment[key] = mapping.get(value, value)
    return environment


def prepare(output):
    assert sys.platform == "linux" and not NATIVE.exists() and not output.exists()
    for port in [18031, 18034]:
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", port))
    info = json.loads(subprocess.check_output(["docker", "inspect", POSTGRES], text=True))[0]
    assert info["Config"]["Labels"]["com.docker.compose.project"] == "prismos-n04-wsl"
    address = info["NetworkSettings"]["Networks"]["prismos-n04-wsl-network"]["IPAddress"]
    original = (STATE / "compose.yaml").read_bytes()
    config = yaml.safe_load((STATE / "config.yaml").read_text())
    NATIVE.mkdir(mode=0o700)
    nonce = secrets.token_hex(5)
    databases = {}
    sources = {"app": make_url(config["database"]["url"]).database, "auth": make_url(config["database"]["auth"]["url"]).database, "checkpoints": make_url(config["checkpointer"]["connection_string"]).database}
    for kind, source in sources.items():
        assert source in {"prismos", "prismos_auth_db", "prismos_checkpoints"}
        target = "prismos_native_" + kind + "_" + nonce
        subprocess.run(["docker", "exec", POSTGRES, "createdb", "-U", "prismos", target], capture_output=True, check=True)
        dump = subprocess.check_output(["docker", "exec", POSTGRES, "pg_dump", "-U", "prismos", "--no-owner", "--no-privileges", source])
        result = subprocess.run(["docker", "exec", "-i", POSTGRES, "psql", "-X", "-q", "-v", "ON_ERROR_STOP=1", "-U", "prismos", "-d", target], input=dump, capture_output=True)
        assert result.returncode == 0, "Owned database clone restore failed; private state retained"
        databases[kind] = target
    for target, url in [(config["database"], config["database"]["url"]), (config["database"]["auth"], config["database"]["auth"]["url"])]:
        kind = "auth" if target is config["database"]["auth"] else "app"
        target["url"] = make_url(url).set(host=address, port=5432, database=databases[kind]).render_as_string(hide_password=False)
    config["checkpointer"]["connection_string"] = make_url(config["checkpointer"]["connection_string"]).set(host=address, port=5432, database=databases["checkpoints"]).render_as_string(hide_password=False)
    config["title"]["enabled"] = False
    private(NATIVE / "config.yaml", yaml.safe_dump(config, allow_unicode=True).encode())
    fixture = json.loads((STATE / "live-fixture.json").read_text())
    # Use an existing different test actor with a fresh personal resource scope.
    fixture["users"]["requester"], fixture["users"]["approver"] = fixture["users"]["approver"], fixture["users"]["requester"]
    private(NATIVE / "live-fixture.json", json.dumps(fixture).encode())
    environment = runtime_environment()
    graph = json.loads((ROOT / "backend/langgraph.json").read_text())
    graph.pop("env", None)
    graph["dependencies"] = [str(ROOT / "backend")]
    graph["checkpointer"]["path"] = str(ROOT / "backend/packages/harness/deerflow/agents/checkpointer/async_provider.py") + ":make_checkpointer"
    private(NATIVE / "langgraph.json", json.dumps(graph).encode())
    entry = NATIVE / "entry.py"
    private(
        entry,
        b"import runpy,sys\n"
        b"service=sys.argv[1]\n"
        b"if service=='gateway':\n"
        b" sys.argv=['uvicorn','app.gateway.app:app','--host','127.0.0.1','--port','18031']\n"
        b"else:\n"
        b" sys.argv=['langgraph','dev','--config','langgraph.json','--no-browser','--allow-blocking','--no-reload','--host','127.0.0.1','--port','18034']\n"
        b"runpy.run_module('uvicorn' if service=='gateway' else 'langgraph_cli',run_name='__main__')\n",
    )
    processes = {}
    private(NATIVE / "ownership.json", json.dumps({"databases": databases, "nonce": nonce, "main_compose_sha256": hashlib.sha256(original).hexdigest()}).encode())
    for name in ["langgraph", "gateway"]:
        log = NATIVE / (name + ".log")
        with log.open("wb") as stream:
            log.chmod(0o600)
            process = subprocess.Popen([str(ROOT / "backend/.venv/bin/python"), str(entry), name, nonce], cwd=NATIVE, env=environment, stdout=stream, stderr=subprocess.STDOUT, start_new_session=True)
        processes[name] = {"pid": process.pid, **settled_process_identity(process, [str(ROOT / "backend/.venv/bin/python"), str(entry), name, nonce])}
    private(NATIVE / "processes.json", json.dumps(processes).encode())
    deadline = time.monotonic() + 120
    with httpx.Client(trust_env=False, timeout=5) as client:
        while time.monotonic() < deadline:
            try:
                if client.get("http://127.0.0.1:18031/health").status_code == 200 and client.get("http://127.0.0.1:18034/ok").status_code == 200:
                    break
            except httpx.HTTPError:
                pass
            time.sleep(1)
        else:
            raise RuntimeError("Owned native services not healthy; private logs retained")
    assert (STATE / "compose.yaml").read_bytes() == original
    output.write_text(
        json.dumps(
            {
                "complete": True,
                "profile": "owned-wsl-native",
                "base_url": "http://127.0.0.1:18031",
                "main_url": "http://localhost:18026",
                "main_compose_unchanged": True,
                "databases": databases,
                "native_state": str(NATIVE),
                "processes": processes,
                "M1_exited": False,
            },
            indent=2,
        )
        + "\n"
    )
    print("Owned native Gateway/LangGraph healthy; main container profile unchanged")


def restart(output):
    assert not output.exists() and NATIVE.is_dir() and not NATIVE.is_symlink()
    original = (STATE / "compose.yaml").read_bytes()
    saved = json.loads((NATIVE / "processes.json").read_text())
    ownership = json.loads((NATIVE / "ownership.json").read_text())
    with httpx.Client(trust_env=False, timeout=10) as client:
        response = client.post("http://127.0.0.1:18034/threads/search", json={"status": "busy", "limit": 100})
        assert response.status_code == 200
        for thread in response.json():
            runs = client.get("http://127.0.0.1:18034/threads/" + thread["thread_id"] + "/runs").json()
            assert runs and all(run["status"] in {"success", "error", "timeout", "interrupted"} for run in runs), "Active native run blocks restart"
    for name in ["gateway", "langgraph"]:
        item = saved[name]
        assert process_identity(item["pid"]) == {k: item[k] for k in ["starttime", "cmdline_sha256"]}
        assert os.getpgid(item["pid"]) == item["pid"], "Native process session ownership changed"
    for name in ["gateway", "langgraph"]:
        os.killpg(saved[name]["pid"], signal.SIGTERM)
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        alive = []
        for name in ["gateway", "langgraph"]:
            status = Path("/proc") / str(saved[name]["pid"]) / "stat"
            if status.exists() and status.read_text().split(") ", 1)[1].split()[0] != "Z":
                alive.append(name)
        if not alive:
            break
        time.sleep(0.2)
    else:
        raise RuntimeError("Native shutdown not confirmed; no replacement process started")
    for name in ["langgraph", "gateway"]:
        logfile = NATIVE / (name + "-restart-" + secrets.token_hex(4) + ".log")
        with logfile.open("wb") as stream:
            logfile.chmod(0o600)
            process = subprocess.Popen([str(ROOT / "backend/.venv/bin/python"), str(NATIVE / "entry.py"), name, ownership["nonce"]], cwd=NATIVE, env=runtime_environment(), stdout=stream, stderr=subprocess.STDOUT, start_new_session=True)
        saved[name] = {"pid": process.pid, **settled_process_identity(process, [str(ROOT / "backend/.venv/bin/python"), str(NATIVE / "entry.py"), name, ownership["nonce"]])}
        private(NATIVE / "processes.json", json.dumps(saved).encode())
    with httpx.Client(trust_env=False, timeout=5) as client:
        deadline = time.monotonic() + 120
        while time.monotonic() < deadline:
            try:
                if client.get("http://127.0.0.1:18036/health").status_code == 200 and client.get("http://127.0.0.1:18034/ok").status_code == 200:
                    break
            except httpx.HTTPError:
                pass
            time.sleep(1)
        else:
            raise RuntimeError("Native restart readiness failed; private logs retained")
    assert (STATE / "compose.yaml").read_bytes() == original
    output.write_text(json.dumps({"complete": True, "main_compose_unchanged": True, "only_owned_native_processes_restarted": True, "busy_runs": 0, "processes": saved}, indent=2) + "\n")
    print("Owned native Gateway/LangGraph restarted; main stack untouched")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--mode", choices=["prepare", "restart"], default="prepare")
    args = parser.parse_args()
    (prepare if args.mode == "prepare" else restart)(args.output)
