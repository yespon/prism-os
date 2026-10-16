"""Real configured model Office task via the same authenticated APIs as the Web UI.

Credentials/transcripts stay in the ignored owned WSL runtime. Public receipts
contain only test content, identifiers and outcomes, never tokens/model config.
"""

import argparse
import hashlib
import io
import json
import secrets
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

import httpx

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / "backend/tmp/n04-wsl/native-profile"
BASE = "http://127.0.0.1:18036"


def execute(
    output: Path,
    resume: Path | None = None,
    template_id: str | None = None,
    base_url: str = BASE,
    fixture_path: Path = STATE / "live-fixture.json",
):
    assert not output.exists(), "Keep prior receipts"
    assert base_url in {"http://127.0.0.1:18026", "http://127.0.0.1:18036"}
    fixture = json.loads(fixture_path.read_text())
    suffix = secrets.token_hex(5)
    private = STATE / ("child-task-" + suffix)
    private.mkdir(mode=0o700)
    result = {
        "complete": False,
        "configured_model": fixture["model_name"],
        "simulated_model": False,
        "private_diagnostics": str(private),
        "phases": [],
        "base_url": base_url,
        "new_model_task_submissions": 0,
    }
    clients = []

    def call(client, path, body=None, method=None, status=200, **kwargs):
        response = client.request(
            method or ("POST" if body is not None else "GET"), path, json=body, **kwargs
        )
        assert response.status_code == status, (path, response.status_code)
        return response.json()

    def login(role):
        account = fixture["users"][role]
        client = httpx.Client(
            base_url=base_url,
            headers={
                "X-Tenant-Id": fixture["other_tenant_id"]
                if role == "outsider"
                else fixture["tenant_id"]
            },
            trust_env=False,
            timeout=240,
        )
        clients.append(client)
        session = call(
            client,
            "/api/auth/login",
            {"email": account["email"], "password": account["password"]},
        )
        client.headers["Authorization"] = "Bearer " + session["session"]["token"]
        return client

    def checkpoint():
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")

    try:
        owner, requester, outsider = [
            login(role) for role in ["approver", "requester", "outsider"]
        ]
        if resume is None:
            agent_body = {
                "name": "child-task-" + suffix,
                "description": "Office user-task acceptance",
                "model": fixture["model_name"],
                "tool_groups": [],
                "skills": [],
            }
            if template_id:
                agent_body["template_id"] = template_id
            else:
                agent_body["system_prompt"] = (
                    "完成用户要求的文档任务。必须委派给general-purpose子Agent，让子Agent读取附件并用office_docx生成文件；主Agent不要读取或创建文档。子Agent成功后，主Agent使用present_files提供结果；失败如实说明，不要改为主Agent代做。"
                )
            agent = call(requester, "/api/agents", agent_body, status=201)
            if template_id:
                assert agent["presentation"]["template_id"] == template_id
                result["template_id"] = template_id
                result["stored_template_prompt_sha256"] = hashlib.sha256(
                    agent["system_prompt"].encode()
                ).hexdigest()
            thread = call(requester, "/api/langgraph/threads", {})["thread_id"]
            result.update(
                {
                    "agent_id": agent["id"],
                    "agent_name": agent["name"],
                    "thread_id": thread,
                }
            )
            graph = "/api/langgraph/threads/" + thread
            brief = (
                "项目：PrismOS 集成验收\n已完成：恢复服务后的真实模型任务\n待办：完整 Office 与专家任务\n验收标识：OFFICE_TASK_"
                + suffix
            )
            response = requester.post(
                "/api/threads/" + thread + "/uploads",
                files={"files": ("brief.txt", brief.encode(), "text/plain")},
            )
            assert response.status_code == 200, ("upload", response.status_code)
            uploaded = response.json()["files"][0]
            result["phases"].append("native_login_agent_thread_upload")
            output_path = "/mnt/user-data/outputs/report-" + suffix + ".docx"
            task = (
                "请把以下任务完整委派给一个general-purpose子Agent：读取附件 "
                + uploaded["virtual_path"]
                + "，按附件事实制作中文项目进度 DOCX：标题“集成进度报告”，正文含已完成、待办和原样验收标识，一张表列出已完成与待办。调用 office_docx action=create，output_path="
                + output_path
                + "。成功后调用 present_files，paths=["
                + json.dumps(output_path)
                + "]，回复下载链接。"
            )
            if template_id:
                task = (
                    "请根据附件 "
                    + uploaded["virtual_path"]
                    + " 生成中文项目进度报告 Word 文件。标题为“集成进度报告”，包含原样验收标识、已完成和待办正文，一张进度表。保存为 "
                    + output_path
                    + " 并给出可下载结果。"
                )
            attachment = {"attachment_id": uploaded["attachment_id"]}
            payload = {
                "assistant_id": "lead_agent",
                "input": {
                    "messages": [
                        {
                            "type": "human",
                            "content": task,
                            "additional_kwargs": {"attachments": [attachment]},
                        }
                    ]
                },
                "context": {
                    "agent_name": agent["name"],
                    "model_name": fixture["model_name"],
                    "thinking_enabled": False,
                    "is_plan_mode": False,
                    "subagent_enabled": True,
                    "referenced_attachments": [attachment],
                },
                "config": {"recursion_limit": 1000},
                "stream_mode": ["values", "updates", "custom"],
                "stream_subgraphs": True,
            }
            result["new_model_task_submissions"] = 1
            checkpoint()
            with requester.stream(
                "POST", graph + "/runs/stream", json=payload
            ) as response:
                assert response.status_code == 200, ("run", response.status_code)
                transcript = "\n".join(response.iter_lines())
            saved = private / "stream.txt"
            saved.write_text(transcript)
            saved.chmod(0o600)
            events = []
            for line in transcript.splitlines():
                if not line.startswith("data:"):
                    continue
                try:
                    event = json.loads(line[5:])
                except ValueError:
                    continue
                if isinstance(event, dict) and event.get("type", "").startswith(
                    "task_"
                ):
                    events.append(event)
            child_tools = [
                call["name"]
                for event in events
                for call in event.get("message", {}).get("tool_calls", [])
            ]
            result["child_tool_names"] = child_tools
            result["child_execution_completed"] = any(
                event["type"] == "task_completed" for event in events
            )
            result["stream_received"] = True
            checkpoint()
        else:
            previous = json.loads(resume.read_text())
            assert previous.get("stream_received") and {
                "task",
                "present_files",
            }.issubset(previous["tool_names"])
            result.update(
                {key: previous[key] for key in ["agent_id", "agent_name", "thread_id"]}
            )
            result["child_tool_names"] = previous.get("child_tool_names", [])
            result["child_execution_completed"] = previous.get(
                "child_execution_completed", False
            )
            result["reused_model_execution_receipt"] = str(resume)
            suffix = previous["agent_name"].removeprefix("child-task-")
            thread = previous["thread_id"]
        graph = "/api/langgraph/threads/" + thread
        output_path = "/mnt/user-data/outputs/report-" + suffix + ".docx"
        state = call(requester, graph + "/state")
        saved = private / "state.json"
        saved.write_text(json.dumps(state, ensure_ascii=False))
        saved.chmod(0o600)
        runs = call(requester, graph + "/runs")
        assert runs and runs[0]["status"] == "success" and not state.get("next"), (
            "Actual graph task must finish successfully"
        )
        result["run_status"] = runs[0]["status"]
        messages = state.get("values", {}).get("messages", [])
        calls = [item for message in messages for item in message.get("tool_calls", [])]
        tool_messages = [m for m in messages if m.get("type") == "tool"]
        result["tool_names"] = [item.get("name") for item in calls]
        result["tool_outcomes"] = [
            {
                "name": m.get("name"),
                "status": m.get("status"),
                "content_type": type(m.get("content")).__name__,
            }
            for m in tool_messages
        ]
        checkpoint()
        assert {"task", "present_files"}.issubset(result["tool_names"]), (
            "Required actual delegated task/presentation missing"
        )
        assert not {"read_file", "office_docx"}.intersection(result["tool_names"]), (
            "Parent must not replace the delegated task"
        )
        artifact = (
            "/api/threads/" + thread + "/artifacts" + output_path + "?download=true"
        )
        response = requester.get(artifact)
        assert response.status_code == 200, ("artifact", response.status_code)
        data = response.content
        with zipfile.ZipFile(io.BytesIO(data)) as package:
            root = ET.fromstring(package.read("word/document.xml"))
            text = "".join(root.itertext())
            assert all(
                value in text
                for value in [
                    "集成进度报告",
                    "OFFICE_TASK_" + suffix,
                    "恢复服务",
                    "Office",
                ]
            )
            assert root.findall(
                ".//{http://schemas.openxmlformats.org/wordprocessingml/2006/main}tbl"
            )
        digest = hashlib.sha256(data).hexdigest()
        if resume:
            assert digest == previous["artifact_sha256"], (
                "Previously accepted artifact must remain unchanged"
            )
        assert "no-store" in {
            v.strip() for v in response.headers["cache-control"].split(",")
        }
        assert outsider.get(artifact).status_code == 404
        assert owner.get(artifact).status_code == 404, (
            "Tenant administrator does not own this private thread"
        )
        assert outsider.get(graph + "/state").status_code == 404
        assert owner.get(graph + "/state").status_code == 404
        result["phases"].append("real_model_read_create_present_download_acl")
        requester.close()
        requester = login("requester")
        history = call(requester, graph + "/history", {"limit": 10})
        assert history and output_path in json.dumps(history)
        again = requester.get(artifact)
        assert (
            again.status_code == 200
            and hashlib.sha256(again.content).hexdigest() == digest
        )
        assert "office_docx" in json.dumps(call(requester, graph + "/state"))
        result.update(
            {
                "complete": True,
                "artifact_url": artifact,
                "artifact_sha256": digest,
                "artifact_bytes": len(data),
                "document_text_and_table_verified": True,
                "fresh_session_history_and_download": True,
                "cross_tenant_and_nonowner_denied": True,
                "raw_transcript_exported": False,
            }
        )
        result["phases"].append("fresh_session_history_artifact")
    except Exception as error:
        result["failure_type"] = type(error).__name__
        result["failure"] = str(error)
        raise
    finally:
        for client in clients:
            client.close()
        checkpoint()
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--resume",
        type=Path,
        help="Recheck an already executed model task; never resend the model request",
    )
    parser.add_argument(
        "--template",
        choices=["expert:office-automation"],
        help="Create from the original expert template without overriding its prompt",
    )
    parser.add_argument("--base-url", default=BASE)
    parser.add_argument("--fixture", type=Path, default=STATE / "live-fixture.json")
    args = parser.parse_args()
    execute(args.output, args.resume, args.template, args.base_url, args.fixture)
