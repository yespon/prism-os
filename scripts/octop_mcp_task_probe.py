"""Actual selected MCP analytics tool → owned report → history/current ACL."""

import argparse
import hashlib
import json
from pathlib import Path
import secrets

import httpx

from octop_office_chart_task_probe import tool_trace

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / "backend/tmp/n04-wsl/native-profile"


def execute(output, resume=None, retry_failed=False):
    assert not output.exists()
    fixture = json.loads((STATE / "live-fixture.json").read_text())
    binding = json.loads((STATE / "analytics-service/binding.json").read_text())
    previous = json.loads(resume.read_text()) if resume else None
    suffix = secrets.token_hex(5)
    private = STATE / ("mcp-task-" + suffix)
    private.mkdir(mode=0o700)
    result = (
        dict(previous)
        if previous
        else {
            "complete": False,
            "actual_model": fixture["model_name"],
            "simulated_model": False,
            "server_name": binding["server_name"],
        }
    )
    result.update(
        complete=False, private_diagnostics=str(private), new_model_task_submissions=0
    )
    if previous:
        result.pop("failure", None)
        result.pop("failure_type", None)
        result["previous_receipt"] = str(resume)
    clients = []

    def save():
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")

    def call(client, path, body=None, status=200):
        response = client.request(
            "POST" if body is not None else "GET", path, json=body
        )
        assert response.status_code == status, (path, response.status_code)
        return response.json()

    def login(role):
        account = fixture["users"][role]
        client = httpx.Client(
            base_url="http://127.0.0.1:18036",
            headers={
                "X-Tenant-Id": fixture["other_tenant_id"]
                if role == "outsider"
                else fixture["tenant_id"]
            },
            timeout=300,
            trust_env=False,
        )
        clients.append(client)
        session = call(
            client,
            "/api/auth/login",
            {"email": account["email"], "password": account["password"]},
        )
        client.headers["Authorization"] = "Bearer " + session["session"]["token"]
        return client

    def stats():
        token = (STATE / "analytics-service/token").read_text().strip()
        with httpx.Client(trust_env=False, timeout=15) as c:
            r = c.get(
                "http://127.0.0.1:18041/stats",
                headers={"Authorization": "Bearer " + token},
            )
            assert r.status_code == 200
            return r.json()["completed_tool_calls"]

    try:
        requester, nonowner, outsider = [
            login(role) for role in ["requester", "approver", "outsider"]
        ]
        if previous is None:
            agent = call(
                requester,
                "/api/agents",
                {
                    "name": "mcp-task-" + suffix,
                    "model": fixture["model_name"],
                    "tool_groups": [binding["server_name"]],
                    "skills": [],
                    "system_prompt": "Read the supplied data and use the selected MCP analytics tool for actual computation. Write a Markdown report only after a successful real tool result. Use native file tools and present_files. Do not substitute mental calculations, bash, or invented results for the MCP tool. Report failures honestly.",
                },
                status=201,
            )
            thread = call(requester, "/api/langgraph/threads", {})["thread_id"]
            marker = "MCP_TASK_" + secrets.token_hex(12)
            csv_text = (
                "category,amount,marker\nW1,100," + marker + "\nW2,150,\nW3,120,\n"
            )
            response = requester.post(
                "/api/threads/" + thread + "/uploads",
                files={"files": ("revenue.csv", csv_text.encode(), "text/csv")},
            )
            assert response.status_code == 200
            attachment = response.json()["files"][0]
            target = "/mnt/user-data/outputs/mcp-revenue-" + suffix + ".md"
            result.update(
                agent_id=agent["id"],
                agent_name=agent["name"],
                thread_id=thread,
                marker=marker,
                output_path=target,
                receiver_before=stats(),
            )
            save()
            reference = {"attachment_id": attachment["attachment_id"]}
            task = (
                "请读取附件 "
                + attachment["virtual_path"]
                + "，调用已选择的MCP数据分析工具，取得总收入、最高收入周及金额。根据真实工具结果生成中文Markdown报告，保留附件原样验收标识，列明数据来源和计算服务；保存为 "
                + target
                + "，提供可下载结果。"
            )
        elif retry_failed:
            assert not previous["complete"], (
                "Never resubmit an already accepted model task"
            )
            thread = result["thread_id"]
            graph = "/api/langgraph/threads/" + thread
            state = call(requester, graph + "/state")
            assert not state.get("next")
            assert all(
                r["status"] in {"success", "error", "interrupted", "timeout"}
                for r in call(requester, graph + "/runs")
            )
            url = (
                "/api/threads/"
                + thread
                + "/artifacts"
                + result["output_path"]
                + "?download=true"
            )
            assert requester.get(url).status_code == 404, (
                "Existing result must be rechecked, not regenerated"
            )
            human = next(
                m for m in state["values"]["messages"] if m.get("type") == "human"
            )
            reference = human["additional_kwargs"]["attachments"][0]
            agent = {"name": result["agent_name"]}
            task = (
                "运行接缝已修复，请继续完成原任务，使用真实MCP结果后再生成报告："
                + human["content"]
            )
        if previous is None or retry_failed:
            payload = {
                "assistant_id": "lead_agent",
                "input": {
                    "messages": [
                        {
                            "type": "human",
                            "content": task,
                            "additional_kwargs": {"attachments": [reference]},
                        }
                    ]
                },
                "context": {
                    "agent_name": agent["name"],
                    "subagent_enabled": False,
                    "thinking_enabled": False,
                    "is_plan_mode": False,
                    "referenced_attachments": [reference],
                },
                "config": {"recursion_limit": 1000},
                "stream_mode": ["values", "updates"],
            }
            result["new_model_task_submissions"] = 1
            save()
            with requester.stream(
                "POST",
                "/api/langgraph/threads/" + thread + "/runs/stream",
                json=payload,
            ) as response:
                assert response.status_code == 200
                transcript = "\n".join(response.iter_lines())
            raw = private / "stream.txt"
            raw.write_text(transcript)
            raw.chmod(0o600)
            result["actual_tool_calls"] = tool_trace(transcript)
        graph = "/api/langgraph/threads/" + result["thread_id"]
        state = call(requester, graph + "/state")
        raw = private / "state.json"
        raw.write_text(json.dumps(state, ensure_ascii=False))
        raw.chmod(0o600)
        runs = call(requester, graph + "/runs")
        assert runs[0]["status"] == "success" and not state.get("next")
        names = {c["name"] for c in result["actual_tool_calls"]}
        assert {"read_file", "write_file", "present_files"} <= names
        assert any(
            name.startswith(binding["server_name"] + "_")
            and name.endswith("analyze_revenue")
            for name in names
        ), "Selected actual MCP call missing"
        url = (
            "/api/threads/"
            + result["thread_id"]
            + "/artifacts"
            + result["output_path"]
            + "?download=true"
        )
        response = requester.get(url)
        assert response.status_code == 200
        text = response.content.decode()
        assert all(value in text for value in [result["marker"], "370", "W2", "150"])
        digest = hashlib.sha256(response.content).hexdigest()
        if previous and "artifact_sha256" in previous:
            assert digest == previous["artifact_sha256"]
        assert (
            nonowner.get(url).status_code == 404
            and outsider.get(url).status_code == 404
        )
        assert (
            nonowner.get(graph + "/state").status_code == 404
            and outsider.get(graph + "/state").status_code == 404
        )
        actual = [
            json.loads(line)
            for line in (STATE / "analytics-service/calls.jsonl")
            .read_text()
            .splitlines()
        ]
        matching = [c for c in actual if result["marker"] in c["markers"]]
        assert matching and all(
            c["total"] == 370
            and c["highest_category"] == "W2"
            and c["engine"] == "sqlite3"
            for c in matching
        )
        requester.close()
        requester = login("requester")
        assert result["output_path"] in json.dumps(
            call(requester, graph + "/history", {"limit": 20})
        )
        assert hashlib.sha256(requester.get(url).content).hexdigest() == digest
        result.update(
            complete=True,
            run_id=runs[0]["run_id"],
            run_status="success",
            artifact_url=url,
            artifact_sha256=digest,
            artifact_bytes=len(response.content),
            receiver_after=stats(),
            actual_matching_mcp_calls=len(matching),
            real_sqlite_result_verified=True,
            fresh_login_history_and_current_acl=True,
        )
    except Exception as error:
        result.update(failure_type=type(error).__name__, failure=str(error))
        raise
    finally:
        for client in clients:
            client.close()
        save()
    print("Actual selected MCP analytics/report user task accepted")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--resume", type=Path)
    parser.add_argument(
        "--retry-failed",
        action="store_true",
        help="Continue an actually failed terminal task in its original thread; requires absent output",
    )
    args = parser.parse_args()
    execute(args.output, args.resume, args.retry_failed)
