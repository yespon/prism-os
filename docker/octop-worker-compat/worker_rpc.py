"""Local compatibility tools only; no native execution, provider clients or user mounts."""

import importlib
import importlib.metadata
import json
from pathlib import Path

from mcp.server.fastmcp import FastMCP
from packaging.requirements import Requirement

server = FastMCP("prismos-octop-compat", log_level="ERROR")
_calls = 0


@server.tool()
def compat_echo(text: str) -> dict:
    """Bounded synthetic RPC echo; never dispatches an external tool or model."""
    global _calls
    if len(text) > 2000:
        raise ValueError("Compatibility payload too large")
    _calls += 1
    return {"schema": "prismos.octop-compat.v1", "text": text, "completed_calls": _calls, "external_effects": False}


@server.tool()
def compat_sdk_facts() -> dict:
    """Import verified SDK sources and report exact installed/source identities."""
    receipt = json.loads(Path("/worker/source-receipt.json").read_text())
    facts = {}
    for package in receipt["packages"]:
        name = package["name"]
        module = importlib.import_module(name.replace("-", "_"))
        facts[name] = {
            "source_version": package["version"],
            "source_only": name == "octop-harness",
            "reported_version": getattr(module, "__version__", None),
            "distribution_version": None if name == "octop-harness" else importlib.metadata.version(name),
        }
        for expression in package["core_requirements"]:
            requirement = Requirement(expression)
            if requirement.marker and not requirement.marker.evaluate({"extra": ""}):
                continue
            version = importlib.metadata.version(requirement.name)
            if not requirement.specifier.contains(version):
                raise ValueError("Worker dependency contract mismatch")
    # Loading the actual agent class exercises the new Deep Agents/adapter imports;
    # it does not construct an Agent, initialize workspace, or call a provider.
    harness_agent = getattr(importlib.import_module("octop_harness"), "HarnessAgent")
    facts["harness_agent_class"] = harness_agent.__name__
    facts["worker_adapter_version"] = importlib.metadata.version("langchain-mcp-adapters")
    facts["mcp_version"] = importlib.metadata.version("mcp")
    return {"schema": "prismos.octop-compat.v1", "sdk": facts, "excluded_harness_members": receipt["excluded_harness_members"], "native_execution_enabled": False, "source_only_harness_is_not_an_official_installed_distribution": True}


if __name__ == "__main__":
    server.run(transport="stdio")
