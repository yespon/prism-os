"""Real configured-model task using a retained non-Skill resource from product APIs."""

import argparse
import hashlib
import json
import secrets
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / "backend/tmp/n04-wsl"
BASE = "http://127.0.0.1:18026"


def execute(output: Path, base_url: str = BASE, fixture_path: Path = STATE / "live-fixture.json", resume: Path | None = None):
    assert base_url in {BASE, "http://127.0.0.1:18031", "http://127.0.0.1:18036"}, "Owned local test profiles only"
    assert not output.exists(), "Preserve previous evidence"
    fixture = json.loads(fixture_path.read_text())
    suffix = secrets.token_hex(5)
    private = STATE / ("auxiliary-task-" + suffix)
    private.mkdir(mode=0o700)
    result = {"complete": False, "configured_model": fixture["model_name"], "simulated_model": False, "private_diagnostics": str(private)}
    clients = []

    def call(client, path, body=None, method=None, status=200):
        response = client.request(method or ("POST" if body is not None else "GET"), path, json=body)
        assert response.status_code == status, (path, response.status_code)
        return response.json()

    def login(role):
        account = fixture["users"][role]
        client = httpx.Client(base_url=base_url, headers={"X-Tenant-Id": fixture["other_tenant_id"] if role == "outsider" else fixture["tenant_id"]}, trust_env=False, timeout=240)
        clients.append(client)
        session = call(client, "/api/auth/login", {"email": account["email"], "password": account["password"]})
        client.headers["Authorization"] = "Bearer " + session["session"]["token"]
        return client

    def checkpoint():
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")

    try:
        requester, nonowner, outsider = [login(role) for role in ["requester", "approver", "outsider"]]
        if resume is None:
            template = "expert:parenting-companion"
            declaration = call(requester, "/api/agent-catalog/templates/" + template + "/resources?check_installation=true")
            resource = next(r for r in declaration["resources"] if r["root"] == "scripts/check_memory_freshness.sh")
            if resource["installation"]["status"] == "not_installed":
                installed = call(requester, "/api/agent-catalog/templates/" + template + "/resources/" + resource["id"] + "/install", {"scope": "personal", "bundle_sha256": resource["bundle_sha256"]}, status=201)
                name = installed["name"]
            else:
                assert resource["installation"]["status"] == "source_match"
                name = resource["host_adaptation"]["name"]
            detail = call(requester, "/api/skills/" + name + "/detail?scope=personal")
            selected = {"name": name, "scope": "personal", "resource_id": detail["resource_id"]}
            agent = call(
                requester, "/api/agents", {"name": "parenting-task-" + suffix, "model": fixture["model_name"], "template_id": template, "tool_groups": [], "skill_binding_mode": "selected", "skill_resources": [selected]}, status=201
            )
            assert agent["presentation"]["template_id"] == template
            thread = call(requester, "/api/langgraph/threads", {})["thread_id"]
            marker = "AUXILIARY_TASK_" + suffix
            target = "/mnt/user-data/outputs/memory-check-" + suffix + ".md"
            task = (
                "这是隔离验收工作区，全部内容为虚构测试数据，不使用真实儿童资料。请使用已选中的原始记忆一致性检查脚本，完成一次实际本地演练："
                "在 /mnt/user-data/workspace/parenting-companion 下建立 MEMORY.md 索引和 memory/child/demo.md 主题文件；先同步索引并运行检查，确认一致；"
                "然后修改主题文件并再次检查，确认能发现比索引更新的文件；最后同步索引再检查，确认恢复一致。"
                "脚本按秒比较文件时间，请确保变更有时间间隔。请读取所选资源说明并按其工作区配置执行，保留脚本原件。"
                "最终报告必须列出三次真实检查输出，不能只推测结果；写成中文 Markdown 报告，包含验收标识 " + marker + "，保存为 " + target + " 并提供下载。"
                "不要创建定时任务、心跳、子任务、真实通知，也不要调用外部服务。"
            )
            result.update(
                template_id=template,
                agent_id=agent["id"],
                agent_name=agent["name"],
                thread_id=thread,
                selected_resource=selected,
                source_revision=declaration["revision"],
                bundle_sha256=resource["bundle_sha256"],
                stored_prompt_sha256=hashlib.sha256(agent["system_prompt"].encode()).hexdigest(),
                output_path=target,
            )
            checkpoint()
            graph = "/api/langgraph/threads/" + thread
            payload = {
                "assistant_id": "lead_agent",
                "input": {"messages": [{"type": "human", "content": task}]},
                "context": {"agent_name": agent["name"], "subagent_enabled": False, "thinking_enabled": False, "is_plan_mode": False},
                "config": {"recursion_limit": 1000},
                "stream_mode": ["updates", "values"],
            }
            with requester.stream("POST", graph + "/runs/stream", json=payload) as response:
                assert response.status_code == 200
                transcript = "\n".join(response.iter_lines())
            stream = private / "stream.txt"
            stream.write_text(transcript)
            stream.chmod(0o600)
        else:
            result.update(json.loads(resume.read_text()))
            result["complete"] = False
            result["new_model_task_submissions"] = 0
            template = result["template_id"]
            agent = {"id": result["agent_id"], "name": result["agent_name"]}
            thread = result["thread_id"]
            target = result["output_path"]
            marker = "AUXILIARY_TASK_" + agent["name"].rsplit("-", 1)[-1]
            resource = {"root": "scripts/check_memory_freshness.sh"}
            graph = "/api/langgraph/threads/" + thread
        state = call(requester, graph + "/state")
        stored = private / "state.json"
        stored.write_text(json.dumps(state, ensure_ascii=False))
        stored.chmod(0o600)
        runs = call(requester, graph + "/runs")
        result.update(run_id=runs[0]["run_id"], run_status=runs[0]["status"])
        assert runs[0]["status"] == "success" and not state.get("next")
        messages = state["values"]["messages"]
        calls = [c for m in messages for c in m.get("tool_calls", [])]
        script_calls = [c for c in calls if c["name"] == "bash" and "check_memory_freshness.sh" in c["args"].get("command", "")]
        outputs = [str(m.get("content", "")) for m in messages if m.get("type") == "tool" and m.get("tool_call_id") in {c["id"] for c in script_calls}]
        combined = "\n".join(outputs)
        result.update(tool_names=[c["name"] for c in calls], actual_script_tool_calls=len(script_calls), observed_fresh_checks=combined.count("All memory files in sync"), observed_stale_checks=combined.count("newer than MEMORY.md"))
        assert result["observed_fresh_checks"] >= 2 and result["observed_stale_checks"] >= 1, "Actual script outputs did not demonstrate fresh/stale/recovered states"
        assert any(c["name"] == "present_files" for c in calls)
        url = "/api/threads/" + thread + "/artifacts" + target + "?download=true"
        response = requester.get(url)
        assert response.status_code == 200 and marker in response.text
        assert "All memory files in sync" in response.text and "newer than MEMORY.md" in response.text
        assert all(client.get(url).status_code == 404 for client in [nonowner, outsider])
        requester.close()
        requester = login("requester")
        assert target in json.dumps(call(requester, graph + "/history", {"limit": 10}))
        assert requester.get(url).content == response.content
        current = call(requester, "/api/agent-catalog/templates/" + template + "/resources?check_installation=true")
        checked = next(r for r in current["resources"] if r["root"] == resource["root"])
        assert checked["installation"]["status"] == "source_match"
        again = call(requester, "/api/agents/" + agent["name"])
        assert hashlib.sha256(again["system_prompt"].encode()).hexdigest() == result["stored_prompt_sha256"]
        result.update(
            complete=True,
            artifact_url=url,
            artifact_sha256=hashlib.sha256(response.content).hexdigest(),
            artifact_bytes=len(response.content),
            fresh_login_history=True,
            current_owner_acl=True,
            installed_source_unchanged=True,
            original_expert_prompt_unchanged=True,
            real_external_delivery_accepted=False,
            schedule_or_heartbeat_accepted=False,
        )
        output.with_suffix(".md").write_bytes(response.content)
    finally:
        for client in clients:
            client.close()
        checkpoint()
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--base-url", default=BASE)
    parser.add_argument("--fixture", type=Path, default=STATE / "live-fixture.json")
    parser.add_argument("--resume", type=Path)
    options = parser.parse_args()
    execute(options.output, options.base_url, options.fixture, options.resume)
    print("Original expert / selected script / actual state transition / result and history accepted")
