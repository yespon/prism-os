"""Probe a local isolated compatibility image; never register an execution worker."""

import argparse
import asyncio
import hashlib
import importlib.metadata
import json
import os
import re
import subprocess
import uuid
from pathlib import Path

from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_mcp_adapters.tools import load_mcp_tools

ROOT = Path(__file__).resolve().parents[1]


def run(*args, check=True):
    return subprocess.run(args, check=check, capture_output=True, text=True, timeout=30)


def content(value):
    if isinstance(value, tuple):
        value = value[0]
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        return json.loads(value)
    return json.loads(next(item["text"] for item in value if item.get("type") == "text"))


async def probe(image):
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", image):
        raise ValueError("An immutable local image ID is required")
    before = hashlib.sha256((ROOT / "backend/uv.lock").read_bytes()).hexdigest()
    name = "prismos-octop-compat-" + uuid.uuid4().hex[:12]
    args = ["run", "--rm", "-i", "--name", name, "--network", "none", "--read-only",
            "--cap-drop", "ALL", "--security-opt", "no-new-privileges", "--memory", "768m",
            "--cpus", "1", "--pids-limit", "64", "--user", "65534:65534",
            "--tmpfs", "/tmp:rw,nosuid,nodev,noexec,size=32m", image]
    client = MultiServerMCPClient({"compat": {"transport": "stdio", "command": "docker", "args": args,
                                           "env": {"PATH": os.environ.get("PATH", os.defpath)}}})
    report = {"schema": "prismos.octop-worker-compat.v1", "image": image,
              "host_adapter_version": importlib.metadata.version("langchain-mcp-adapters"),
              "host_mcp_version": importlib.metadata.version("mcp"), "real_external_acceptance": False}
    try:
        async with asyncio.timeout(120):
            async with client.session("compat") as session:
                tools = {tool.name: tool for tool in await load_mcp_tools(session)}
                assert set(tools) == {"compat_echo", "compat_sdk_facts"}
                report["schemas"] = {key: tool.args_schema for key, tool in tools.items()}
                echoes = [content(await tools["compat_echo"].ainvoke({"text": text}))
                          for text in ["PrismOS → Octop 中文", "second call"]]
                assert [item["completed_calls"] for item in echoes] == [1, 2]
                assert echoes[0]["text"] == "PrismOS → Octop 中文"
                rejected = await session.call_tool("compat_echo", {"text": "x" * 2001})
                assert rejected.isError
                final = content(await tools["compat_echo"].ainvoke({"text": "after rejected input"}))
                assert final["completed_calls"] == 3
                facts = content(await tools["compat_sdk_facts"].ainvoke({}))
                assert facts["sdk"]["worker_adapter_version"] == "0.3.0"
                assert facts["sdk"]["harness_agent_class"] == "HarnessAgent"
                assert facts["sdk"]["octop-harness"]["distribution_version"] is None
                assert not facts["native_execution_enabled"]
                inspection = json.loads(run("docker", "inspect", name).stdout)[0]
                host = inspection["HostConfig"]
                assert host["NetworkMode"] == "none" and host["ReadonlyRootfs"]
                assert host["CapDrop"] == ["ALL"] and not host["Privileged"]
                assert not host.get("Binds") and not inspection["Mounts"]
                assert not host.get("PortBindings") and inspection["Config"]["User"] == "65534:65534"
                report.update({"echoes": echoes + [final], "oversize_rejected": True, "sdk_facts": facts,
                               "isolation": {key: host[key] for key in ["NetworkMode", "ReadonlyRootfs", "CapDrop", "SecurityOpt", "Memory", "NanoCpus", "PidsLimit", "Tmpfs"]}})
    finally:
        # Only the random container created by this invocation may be removed.
        run("docker", "rm", "-f", name, check=False)
    assert run("docker", "inspect", name, check=False).returncode != 0
    after = hashlib.sha256((ROOT / "backend/uv.lock").read_bytes()).hexdigest()
    assert before == after
    report.update({"complete": True, "host_lock_sha256": after, "host_lock_unchanged": True,
                   "container_removed": True, "native_execution_enabled": False})
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError("Evidence output already exists")
    result = asyncio.run(probe(args.image))
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
