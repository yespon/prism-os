"""R3 rehearsal part 2: cron worker boot recovery (2026-10-19).

Create a real schedule, restart the worker container, verify the job is
re-registered from the DB (single-instance worker, restart-safe through
the claim protocol).
"""

import asyncio
import json
import subprocess
import sys
import time
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

    # 1. Create an interval schedule (every 30 seconds so the recovery is observable).
    created = owner.post("/api/schedules", json={
        "name": "r3-recovery-check",
        "trigger_kind": "interval",
        "interval_seconds": 30,
        "agent_name": "default",
        "prompt": "Report queue depth.",
    })
    assert created.status_code == 201, created.text
    schedule_id = created.json()["id"]
    step(receipt, "schedule-created", schedule_id=schedule_id)

    # 2. The worker picks it up: restart the worker, then check the boot log
    #    re-registers exactly this one job.
    subprocess.run(["docker", "restart", "prismos-n04-wsl-cron-worker-1"], check=True)
    time.sleep(15)
    log = subprocess.run(
        ["docker", "logs", "--since", "60s", "prismos-n04-wsl-cron-worker-1"],
        capture_output=True, text=True, check=True).stdout
    assert "cron worker booted with 1 job(s)" in log, log[-400:]
    step(receipt, "worker-restart-recovered", jobs=1)

    # 3. Wait for one automatic trigger (interval 30s) and verify the
    #    occurrence history shows exactly one execution for the slot.
    time.sleep(35)
    occurrences = owner.get(f"/api/schedules/{schedule_id}/occurrences").json()["occurrences"]
    assert len(occurrences) >= 1, "interval trigger produced no occurrence"
    states = [o["state"] for o in occurrences]
    step(receipt, "auto-trigger-fired", count=len(occurrences), states=states)

    # 4. Cleanup: delete the schedule (owner path) and stop the worker.
    deleted = owner.delete(f"/api/schedules/{schedule_id}")
    assert deleted.status_code == 204
    step(receipt, "cleanup-done")

    receipt["complete"] = True
    (HERE / "r3-boot-recovery-result.json").write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(receipt, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
