"""Actual original Office expert: turn its existing Word report into a report pack."""

from pathlib import Path
import argparse
import hashlib
import io
import json
import secrets
import zipfile
from xml.etree import ElementTree as ET

import httpx

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / "backend/tmp/n04-wsl"
BASE = "http://127.0.0.1:18026"


def execute(source: Path, output: Path):
    assert not output.exists(), "Preserve prior receipts"
    accepted = json.loads(source.read_text())
    assert accepted["complete"] and accepted["run_status"] == "success"
    fixture = json.loads((STATE / "live-fixture.json").read_text())
    suffix = secrets.token_hex(5)
    private = STATE / ("office-pack-" + suffix)
    private.mkdir(mode=0o700)
    result = {
        "complete": False,
        "source_task": str(source),
        "template_id": accepted["template_id"],
        "thread_id": accepted["thread_id"],
        "private_diagnostics": str(private),
        "actual_model": fixture["model_name"],
    }
    clients = []

    def call(client, path, body=None):
        response = client.request(
            "POST" if body is not None else "GET", path, json=body
        )
        assert response.status_code == 200, (path, response.status_code)
        return response.json()

    def login(role):
        account = fixture["users"][role]
        client = httpx.Client(
            base_url=BASE,
            headers={
                "X-Tenant-Id": fixture["other_tenant_id"]
                if role == "outsider"
                else fixture["tenant_id"]
            },
            timeout=240,
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

    def save():
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")

    try:
        requester, outsider = login("requester"), login("outsider")
        graph = "/api/langgraph/threads/" + accepted["thread_id"]
        source_path = accepted["artifact_url"].split("/artifacts", 1)[1].split("?")[0]
        prefix = "/mnt/user-data/outputs/brief-pack-" + suffix
        paths = {
            extension: prefix + "." + extension for extension in ["xlsx", "pptx", "pdf"]
        }
        task = (
            "请读取本线程已生成的 Word 报告 "
            + source_path
            + "，将同样事实整理成可下载的汇报材料包：中文 Excel 进度表，中文 PowerPoint 演示稿（至少两页），英文 PDF 简报。三份均保留报告中的原样验收标识，区分已完成和待办，不编造数字或完成率。分别保存为 "
            + "、".join(paths.values())
            + "。英文 PDF 使用基本英文字符即可。请提供三份文件的下载结果。"
        )
        result["natural_request"] = task
        payload = {
            "assistant_id": "lead_agent",
            "input": {"messages": [{"type": "human", "content": task}]},
            "context": {
                "agent_name": accepted["agent_name"],
                "subagent_enabled": False,
                "thinking_enabled": False,
                "is_plan_mode": False,
            },
            "config": {"recursion_limit": 1000},
            "stream_mode": ["values", "updates"],
        }
        with requester.stream("POST", graph + "/runs/stream", json=payload) as response:
            assert response.status_code == 200
            transcript = "\n".join(response.iter_lines())
        file = private / "stream.txt"
        file.write_text(transcript)
        file.chmod(0o600)
        state = call(requester, graph + "/state")
        file = private / "state.json"
        file.write_text(json.dumps(state, ensure_ascii=False))
        file.chmod(0o600)
        runs = call(requester, graph + "/runs")
        result["run_status"] = runs[0]["status"] if runs else None
        messages = state.get("values", {}).get("messages", [])
        # Only this request's segment, not earlier DOCX tool calls in the thread.
        index = next(
            i
            for i, m in enumerate(messages)
            if m.get("type") == "human" and m.get("content") == task
        )
        segment = messages[index:]
        result["tool_names"] = [
            c["name"] for m in segment for c in m.get("tool_calls", [])
        ]
        result["tool_outcomes"] = [
            {"name": m.get("name"), "content": m.get("content")}
            for m in segment
            if m.get("type") == "tool"
        ]
        # Tool content is kept private until reduced to safe outcome fields.
        file = private / "tool-outcomes.json"
        file.write_text(json.dumps(result.pop("tool_outcomes"), ensure_ascii=False))
        file.chmod(0o600)
        save()
        assert result["run_status"] == "success" and not state.get("next"), (
            "Task must finish"
        )
        assert {
            "office_docx",
            "office_xlsx",
            "office_pptx",
            "office_pdf",
            "present_files",
        }.issubset(result["tool_names"])
        marker = "OFFICE_TASK_" + accepted["agent_name"].removeprefix("office-task-")
        artifacts = {}
        for extension, virtual in paths.items():
            url = (
                "/api/threads/"
                + accepted["thread_id"]
                + "/artifacts"
                + virtual
                + "?download=true"
            )
            response = requester.get(url)
            assert response.status_code == 200, (extension, response.status_code)
            data = response.content
            assert outsider.get(url).status_code == 404
            if extension == "xlsx":
                import openpyxl

                workbook = openpyxl.load_workbook(
                    io.BytesIO(data), read_only=True, data_only=False
                )
                rows = [
                    [list(row) for row in sheet.iter_rows(values_only=True)]
                    for sheet in workbook
                ]
                workbook.close()
                text = json.dumps(rows, ensure_ascii=False)
                assert (
                    marker in text
                    and "已完成" in text
                    and "待办" in text
                    and "Office" in text
                )
                detail = {"worksheets": len(rows), "rows": rows}
            elif extension == "pptx":
                with zipfile.ZipFile(io.BytesIO(data)) as package:
                    slides = [
                        name
                        for name in package.namelist()
                        if name.startswith("ppt/slides/slide") and name.endswith(".xml")
                    ]
                    text = " ".join(
                        " ".join(ET.fromstring(package.read(name)).itertext())
                        for name in slides
                    )
                assert (
                    len(slides) >= 2
                    and marker in text
                    and "已完成" in text
                    and "待办" in text
                )
                detail = {"slides": len(slides), "text": text}
            else:
                from pypdf import PdfReader

                reader = PdfReader(io.BytesIO(data))
                text = "\n".join(page.extract_text() for page in reader.pages)
                assert (
                    marker in text
                    and "completed" in text.lower()
                    and "pending" in text.lower()
                )
                detail = {"pages": len(reader.pages), "text": text}
            artifacts[extension] = {
                "url": url,
                "sha256": hashlib.sha256(data).hexdigest(),
                "bytes": len(data),
                "independent_content_check": detail,
            }
            file = private / ("report." + extension)
            file.write_bytes(data)
            file.chmod(0o600)
        requester.close()
        requester = login("requester")
        history = call(requester, graph + "/history", {"limit": 10})
        for extension, artifact in artifacts.items():
            assert paths[extension] in json.dumps(history)
            response = requester.get(artifact["url"])
            assert (
                response.status_code == 200
                and hashlib.sha256(response.content).hexdigest() == artifact["sha256"]
            )
        result.update(
            {
                "complete": True,
                "artifacts": artifacts,
                "fresh_session_history_and_hashes": True,
                "cross_tenant_denied": True,
                "new_model_requests": 1,
            }
        )
    except Exception as error:
        result.update({"failure_type": type(error).__name__, "failure": str(error)})
        raise
    finally:
        for client in clients:
            client.close()
        save()
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    execute(args.source, args.output)
