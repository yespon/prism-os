"""R5 rehearsal: version publish -> evaluation gate -> deploy -> rollback (2026-10-20).

Against the N04 stack with the R5 image: publish an agent version,
prove the gate refuses (no evaluation, then a failing score), deploy
after a passing evaluation, publish v2, roll back, and confirm history
resolves both versions.
"""

import asyncio
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from live_common import login  # noqa: E402


def step(receipt, name, **fields):
    entry = {"step": name, **fields}
    receipt["steps"].append(entry)
    print(json.dumps(entry, ensure_ascii=False), flush=True)


def main() -> None:
    owner = login("approver")
    receipt = {"steps": [], "complete": False}

    agents = owner.get("/api/agents").json()
    items = agents.get("agents") or agents.get("items") or []
    if not items:
        created = owner.post("/api/agents", json={
            "name": "r5-rehearsal-agent",
            "system_prompt": "R5 rehearsal agent: answer briefly.",
        })
        assert created.status_code in (200, 201), created.text
        agent_id = created.json()["id"]
    else:
        agent_id = items[0]["id"]
    step(receipt, "agent-ready", agent_id=agent_id)

    # 1. Create a fresh agent so every rehearsal run exercises the full gate
    #    path from an undeployed state (reruns stay deterministic).
    import time as _time

    fresh = owner.post("/api/agents", json={
        "name": f"r5-gate-{int(_time.time())}",
        "system_prompt": "R5 gate rehearsal agent.",
    })
    assert fresh.status_code in (200, 201), fresh.text
    gate_agent = fresh.json()["id"]

    # 2. Gate refuses without evaluation.
    v0 = owner.post(f"/api/agents/{gate_agent}/versions", json={"notes": "gate probe"})
    assert v0.status_code == 201, v0.text
    blocked = owner.post(f"/api/agents/{gate_agent}/versions/{v0.json()['id']}/deploy")
    assert blocked.status_code == 409, blocked.text
    step(receipt, "gate-refuses-no-evaluation", detail=blocked.json()["detail"])

    # 3. Failing score still refuses.
    owner.post(f"/api/agents/{gate_agent}/versions/{v0.json()['id']}/evaluate",
               json={"score": 0.3, "dataset": "golden-aiops"})
    low = owner.post(f"/api/agents/{gate_agent}/versions/{v0.json()['id']}/deploy")
    assert low.status_code == 409 and "gate failed" in low.json()["detail"], low.text
    step(receipt, "gate-refuses-low-score")

    # 4. Passing score deploys.
    owner.post(f"/api/agents/{gate_agent}/versions/{v0.json()['id']}/evaluate",
               json={"score": 0.95, "dataset": "golden-aiops"})
    deployed = owner.post(f"/api/agents/{gate_agent}/versions/{v0.json()['id']}/deploy")
    assert deployed.status_code == 202, deployed.text
    step(receipt, "gate-probe-deployed-after-pass")

    # 5. The main agent: v1 (idempotent on rerun).
    v1 = owner.post(f"/api/agents/{agent_id}/versions", json={"notes": "v1 baseline"})
    if v1.status_code == 400:
        versions = owner.get(f"/api/agents/{agent_id}/versions").json()["versions"]
        assert versions, "no prior version although publish said identical"
        v1_id = versions[0]["id"]
        step(receipt, "v1-already-published", version_id=v1_id)
    else:
        assert v1.status_code == 201, v1.text
        v1_id = v1.json()["id"]
        owner.post(f"/api/agents/{agent_id}/versions/{v1_id}/evaluate",
                   json={"score": 0.95, "dataset": "golden-aiops"})
        owner.post(f"/api/agents/{agent_id}/versions/{v1_id}/deploy")
        step(receipt, "v1-published-and-deployed", version_id=v1_id)

    # 5. Publish v2 with a changed prompt (agents route by name everywhere).
    listing = owner.get("/api/agents").json()
    items = listing.get("agents") or listing.get("items") or []
    agent_name = next(a["name"] for a in items if a["id"] == agent_id)
    owner.put(f"/api/agents/{agent_name}", json={"system_prompt": "R5 v2: structured detailed answers."})
    v2 = owner.post(f"/api/agents/{agent_id}/versions", json={"notes": "v2 detail mode"})
    if v2.status_code == 400:
        versions = owner.get(f"/api/agents/{agent_id}/versions").json()["versions"]
        assert len(versions) >= 2, "expected a distinct v2"
        v2_id = versions[1]["id"]
        step(receipt, "v2-already-published", version_id=v2_id)
    else:
        assert v2.status_code == 201, v2.text
        v2_id = v2.json()["id"]
        step(receipt, "v2-published", version_id=v2_id)

    # 6. Evaluate and deploy v2.
    owner.post(f"/api/agents/{agent_id}/versions/{v2_id}/evaluate",
               json={"score": 0.9, "dataset": "golden-aiops"})
    deployed_v2 = owner.post(f"/api/agents/{agent_id}/versions/{v2_id}/deploy")
    assert deployed_v2.status_code == 202, deployed_v2.text
    pointer = owner.get(f"/api/agents/{agent_id}/versions/deployment").json()
    assert pointer["version_id"] == v2_id and pointer["previous_version_id"] == v1_id, pointer
    step(receipt, "v2-deployed", previous=v1_id)

    # 7. Rollback to v1.
    rolled = owner.post(f"/api/agents/{agent_id}/versions/rollback")
    assert rolled.status_code == 200, rolled.text
    assert rolled.json()["version_id"] == v1_id
    step(receipt, "rolled-back-to-v1")

    # 8. History intact: both versions still listed.
    versions = owner.get(f"/api/agents/{agent_id}/versions").json()["versions"]
    assert {v["id"] for v in versions} >= {v1_id, v2_id}
    step(receipt, "history-intact", count=len(versions))

    receipt["complete"] = True
    (HERE / "r5-rehearsal-result.json").write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(receipt, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
