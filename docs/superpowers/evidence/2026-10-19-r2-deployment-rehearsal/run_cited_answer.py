"""R2 rehearsal part 2: real-model cited answer through knowledge.search (2026-10-19)."""

import asyncio
import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from live_common import BASE, FIXTURE, login  # noqa: E402


async def main() -> None:
    receipt = {"steps": [], "complete": False}
    owner = login("approver")

    # 1. Private KB + runbook upload (fresh).
    created = owner.post("/api/knowledge/bases", json={"name": f"cited-answer-{int(time.time())}"})
    assert created.status_code == 201, created.text
    kb_id = created.json()["id"]
    runbook = (
        "# Secret rotation runbook\n\n"
        "The master encryption key must be rotated quarterly via the rotate_storage_key "
        "procedure, always in dry-run mode first. Rotation requires two operators.\n"
    )
    upload = owner.post(
        f"/api/knowledge/bases/{kb_id}/documents",
        files={"file": ("rotation.md", runbook.encode(), "text/markdown")},
    )
    assert upload.status_code == 201 and upload.json()["index_state"] == "ready", upload.text
    receipt["steps"].append({"step": "kb-and-runbook-ready"})

    # 2. Agent bound to the KB via meta_info, prompt asks to use knowledge.search.
    agent = owner.post("/api/agents", json={
        "name": f"kb-answerer-{int(time.time())}",
        "model": FIXTURE["model_name"],
        "is_shared": True, "tool_groups": [], "skill_binding_mode": "selected",
        "skill_resources": [], "meta_info": {"knowledge_base_ids": [kb_id]},
        "system_prompt": "You have a knowledge.search tool bound to private runbooks. "
        "For any operational question, call knowledge.search first and answer from the "
        "cited context; mention the cited filename.",
    })
    assert agent.status_code == 201, agent.text
    agent_id = agent.json()["id"]
    receipt["steps"].append({"step": "kb-bound-agent-created", "agent_id": agent_id})

    # 3. Real-model chat through the authenticated LangGraph proxy.
    import httpx

    thread = owner.post("/api/langgraph/threads", json={})
    assert thread.status_code in (200, 201), thread.text
    thread_id = thread.json()["thread_id"]
    question = "How often must the master encryption key be rotated, and what mode first?"
    agent_name = agent.json()["name"]
    stream = owner.post(
        f"/api/langgraph/threads/{thread_id}/runs/stream",
        json={
            "assistant_id": "lead_agent",
            "input": {"messages": [{"role": "user", "content": question}]},
            "context": {"agent_name": agent_name},
            "stream_mode": ["messages-tuple"],
        },
        timeout=240,
    )
    assert stream.status_code == 200, stream.text[:300]
    body = stream.text
    # The tool result with the citation marker must appear in the stream.
    cited = "prismos-kb-citations" in body
    answered = ("quarterly" in body.lower()) or ("每季" in body)
    receipt["steps"].append({"step": "real-model-answer", "citations_in_stream": cited, "mentions_rotation": answered})

    # The agent must actually answer from the runbook.
    assert answered, "answer did not reflect the runbook content"
    receipt["complete"] = True
    (HERE / "r2-cited-answer-result.json").write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(receipt, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
