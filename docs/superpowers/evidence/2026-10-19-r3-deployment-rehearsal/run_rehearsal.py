"""R3 rehearsal: schedule lifecycle, idempotent triggers, tenant isolation (2026-10-19).

Runs against the N04 stack with the R3 image:
1. create an interval schedule through the API (real auth)
2. run-now twice in the same slot; assert exactly one will_execute
3. occurrence history shows one occurrence
4. cross-tenant run-now is a 404
5. disable and delete through the owner-only paths
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


async def main() -> None:
    owner = login("approver")
    receipt = {"steps": [], "complete": False}

    created = owner.post("/api/schedules", json={
        "name": "r3-rehearsal-check",
        "trigger_kind": "interval",
        "interval_seconds": 60,
        "agent_name": "default",
        "prompt": "Summarize the current queue depth.",
    })
    assert created.status_code == 201, created.text
    schedule_id = created.json()["id"]
    step(receipt, "schedule-created", schedule_id=schedule_id)

    first = owner.post(f"/api/schedules/{schedule_id}/run-now")
    assert first.status_code == 202, first.text
    second = owner.post(f"/api/schedules/{schedule_id}/run-now")
    assert second.status_code == 202
    assert first.json()["will_execute"] is True
    assert second.json()["will_execute"] is False, "same-slot run-now must not re-execute"
    step(receipt, "run-now-collision-single-execution")

    occurrences = owner.get(f"/api/schedules/{schedule_id}/occurrences").json()["occurrences"]
    assert len(occurrences) == 1
    step(receipt, "single-occurrence", occurrence_state=occurrences[0]["state"])

    outsider = login("outsider")
    outsider.headers.update({"X-Tenant-Id": FIXTURE["other_tenant_id"]})
    gone = outsider.post(f"/api/schedules/{schedule_id}/run-now")
    assert gone.status_code == 404
    step(receipt, "cross-tenant-404")

    disabled = owner.post(f"/api/schedules/{schedule_id}/enabled", json={"enabled": False})
    assert disabled.status_code == 200
    deleted = owner.delete(f"/api/schedules/{schedule_id}")
    assert deleted.status_code == 204
    listing = owner.get("/api/schedules").json()["schedules"]
    assert all(s["id"] != schedule_id for s in listing)
    step(receipt, "disable-and-delete")

    receipt["complete"] = True
    (HERE / "r3-rehearsal-result.json").write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(receipt, ensure_ascii=False))


if __name__ == "__main__":
    from live_common import FIXTURE
    asyncio.run(main())
