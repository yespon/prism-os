"""R1 deployment rehearsal: durable run facts survive restart (2026-10-19).

Runs against the owned N04 WSL stack with the R1 backend image:
1. pre-check stack healthy and switches off
2. enable the single-tenant ticket.create canary in allow mode
3. authenticated diagnosis with the configured real model -> tool executes
4. read governed-ticket status: assert the run projection (state/snapshot)
5. restart gateway+langgraph, re-read status: facts identical (frozen snapshot)
6. switch canary off, verify rollback, record receipts

Secrets stay in the private runtime state directory; only non-sensitive
ids, states and hashes go to the evidence receipt.
"""

import json
import ssl
import subprocess
import sys
import time
from pathlib import Path

import httpx
import yaml

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from live_common import BASE, FIXTURE, STATE, compose, expect, login  # noqa: E402


def wait_healthy(deadline_s: int = 180) -> None:
    deadline = time.monotonic() + deadline_s
    while time.monotonic() < deadline:
        states = [
            subprocess.check_output(
                ["docker", "inspect", "--format", "{{.State.Health.Status}}",
                 f"prismos-n04-wsl-{name}-1"], text=True).strip()
            for name in ("gateway", "langgraph")
        ]
        if all(s == "healthy" for s in states):
            return
        time.sleep(2)
    raise RuntimeError("gateway/langgraph not healthy")


def set_policy(verdict: str) -> str:
    assert verdict in {"off", "allow"}
    path = STATE / "compose.yaml"
    backup = STATE / "compose-before-r1-rehearsal.yaml"
    if not backup.exists():
        backup.write_bytes(path.read_bytes())
    config = yaml.safe_load(path.read_text())
    version = f"r1-{verdict}-{int(time.time())}"
    for name in ("gateway", "langgraph"):
        env = config["services"][name]["environment"]
        env.update({
            "PRISMOS_TRUSTED_GRAPH_CONTEXT": "required" if verdict != "off" else "off",
            "PRISMOS_GOVERNED_TICKET_TENANT": FIXTURE["tenant_id"] if verdict != "off" else "",
            "PRISMOS_GOVERNED_TICKET_ACTION": "ticket.create" if verdict != "off" else "off",
            "PRISMOS_GOVERNED_TICKET_VERDICT": verdict if verdict != "off" else "deny",
            "PRISMOS_GOVERNED_TICKET_POLICY_VERSION": version,
            "PRISMOS_TICKET_SECRET_ADMIN_TENANT": FIXTURE["tenant_id"] if verdict != "off" else "",
        })
    path.write_text(yaml.safe_dump(config, sort_keys=False))
    compose(["up", "-d", "--no-build", "--no-deps", "gateway", "langgraph"])
    wait_healthy()
    return version


def diagnose_and_get_status(owner, requester) -> dict:
    """Trigger one real-model diagnosis and return the status payload.

    Follows the proven N04 pattern: create an owned agent whose prompt
    instructs exactly one governed ticket tool call, bind it to a fresh
    alert source, ingest, then diagnose with that agent.
    """
    suffix = f"r1-{int(time.time())}"
    agent = expect(owner, "/api/agents", {
        "name": "r1-rehearsal-" + suffix, "model": FIXTURE["model_name"],
        "is_shared": True, "tool_groups": [], "skill_binding_mode": "selected",
        "skill_resources": [],
        "system_prompt": "Authorized isolated test: call create_governed_incident_ticket exactly once immediately for this incident, then report its actual result briefly. Do not call other tools, delegate, access files or execute commands. If approval is pending, stop and wait; never bypass approval."}, status=201)
    source = expect(owner, "/api/alert-sources", {
        "name": f"R1 rehearsal {suffix}", "type": "webhook",
        "config_json": {"ticket": {"provider": "webhook", "template": {
            "title": "{{ incident.title }}", "incident_key": "{{ incident.incident_key }}"}}},
        "ai_analysis_enabled": False, "diagnosis_agent_id": agent["id"]}, status=201)
    # Bind the receiver credential through the governed SecretRef endpoint
    # (inline webhook credentials are rejected by the M1 boundary).
    token = (STATE / "receiver/receiver-token").read_text().strip()
    expect(owner, "/api/alert-sources/" + source["id"] + "/ticket-secret", {
        "webhook_url": "https://ticket-receiver:8443/tickets",
        "headers": {"Authorization": "Bearer " + token}}, status=201)
    event = expect(owner, "/api/alerts/ingest/" + source["id"], {
        "alert": {"name": f"R1 rehearsal {suffix}", "severity": "warning"},
        "labels": {"service": f"r1-{suffix}", "env": "test"}}, status=202)
    incident_id = event["ingest_id"]
    with requester.stream("POST", f"/api/incidents/{incident_id}/diagnose",
                          params={"agent_id": agent["id"]}, timeout=240) as response:
        for _ in response.iter_lines():
            pass
    status = requester.get(f"/api/incidents/{incident_id}/governed-ticket").json()
    return {"incident_id": incident_id, "status": status}


def main() -> None:
    receipt = {"steps": [], "complete": False}
    try:
        wait_healthy()
        receipt["steps"].append({"step": "pre-health", "ok": True})

        version = set_policy("allow")
        receipt["steps"].append({"step": "policy-allow", "version": version})

        owner = login("approver")
        requester = login("requester")
        result = diagnose_and_get_status(owner, requester)
        status = result["status"]
        assert status["enabled"] and status.get("run"), "run projection missing"
        run = status["run"]
        assert run["state"] in ("created", "completed"), run
        assert run["snapshot"]["source"] == "diagnosis", run
        receipt["steps"].append({
            "step": "run-fact-recorded",
            "incident_id": result["incident_id"],
            "run_state": run["state"],
            "snapshot_keys": sorted(run["snapshot"].keys()),
            "agent_id": run["snapshot"]["agent_id"],
        })

        compose(["restart", "gateway", "langgraph"])
        wait_healthy()
        after = requester.get(f"/api/incidents/{result['incident_id']}/governed-ticket").json()
        run_after = after["run"]
        assert run_after == run, (run, run_after)
        receipt["steps"].append({
            "step": "restart-preserved",
            "run_state": run_after["state"],
            "snapshot_identical": True,
        })

        set_policy("off")
        rolled = requester.get(f"/api/incidents/{result['incident_id']}/governed-ticket").json()
        assert rolled["enabled"] is False
        receipt["steps"].append({"step": "rollback-off", "ok": True})

        receipt["complete"] = True
    finally:
        try:
            set_policy("off")
        except Exception:
            pass
        out = HERE / "r1-rehearsal-result.json"
        out.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n")
        print(json.dumps(receipt, ensure_ascii=False))


if __name__ == "__main__":
    main()
