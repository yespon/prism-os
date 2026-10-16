"""Real original expert task with an explicitly uploaded, owned Unicode font.

System font bytes and the PDF that embeds them stay private; public receipts
contain hashes/text/rendered output only, not the font binary.
"""

import argparse
import hashlib
import json
import secrets
import subprocess
from pathlib import Path

import httpx
from octop_office_report_probe import BASE, STATE


def execute(source: Path, output: Path, font: Path | None, reuse_font: Path | None = None):
    assert not output.exists()
    accepted = json.loads(source.read_text())
    assert accepted["complete"] and accepted["run_status"] == "success"
    fixture = json.loads((STATE / "live-fixture.json").read_text())
    suffix = secrets.token_hex(5)
    private = STATE / ("office-unicode-" + suffix)
    private.mkdir(mode=0o700)
    prior_font = json.loads(reuse_font.read_text()) if reuse_font else None
    font_bytes = font.read_bytes() if prior_font is None and font is not None else b""
    result = {
        "complete": False,
        "template_id": accepted["template_id"],
        "thread_id": accepted["thread_id"],
        "agent_name": accepted["agent_name"],
        "private_diagnostics": str(private),
        "font_name": prior_font["font_name"] if prior_font else font.name,
        "font_sha256": prior_font["font_sha256"] if prior_font else hashlib.sha256(font_bytes).hexdigest(),
        "font_bytes": prior_font["font_bytes"] if prior_font else len(font_bytes),
        "font_binary_exported": False,
        "embedding_pdf_exported": False,
    }
    clients = []

    def call(client, path, body=None):
        response = client.request("POST" if body is not None else "GET", path, json=body)
        assert response.status_code == 200, (path, response.status_code)
        return response.json()

    def login(role):
        account = fixture["users"][role]
        client = httpx.Client(base_url=BASE, headers={"X-Tenant-Id": fixture["other_tenant_id"] if role == "outsider" else fixture["tenant_id"]}, trust_env=False, timeout=240)
        clients.append(client)
        login_response = call(client, "/api/auth/login", {"email": account["email"], "password": account["password"]})
        client.headers["Authorization"] = "Bearer " + login_response["session"]["token"]
        return client

    try:
        requester, outsider, nonowner = [login(role) for role in ["requester", "outsider", "approver"]]
        base = "/api/threads/" + accepted["thread_id"]
        if prior_font:
            files = call(requester, base + "/uploads/list")["files"]
            uploaded = next(v for v in files if v.get("attachment_id") == prior_font["font_attachment_id"])
            current = requester.get(uploaded["artifact_url"])
            assert current.status_code == 200 and hashlib.sha256(current.content).hexdigest() == prior_font["font_sha256"]
            result["reused_font_scope"] = str(reuse_font)
            result["font_uploaded_again"] = False
        else:
            response = requester.post(base + "/uploads", files={"files": ("font-" + suffix + font.suffix, font_bytes, "font/collection")})
            assert response.status_code == 200, ("font upload", response.status_code)
            uploaded = response.json()["files"][0]
        result["font_attachment_id"] = uploaded["attachment_id"]
        assert all(client.get(uploaded["artifact_url"]).status_code == 404 for client in [outsider, nonowner])
        path = "/mnt/user-data/outputs/chinese-report-" + suffix + ".pdf"
        source_path = accepted["artifact_url"].split("/artifacts", 1)[1].split("?")[0]
        task = (
            "请读取本线程 Word 报告 "
            + source_path
            + "，使用我上传的字体 "
            + uploaded["virtual_path"]
            + " 生成完整中文项目进度简报 PDF。标题“中文项目进度报告”，准确保留项目名、已完成、待办和原样验收标识。采用普通文字，不加表情或图标；主动分行，每行不超过三十字。输出 "
            + path
            + " 并提供下载。"
        )
        graph = "/api/langgraph/threads/" + accepted["thread_id"]
        payload = {
            "assistant_id": "lead_agent",
            "input": {"messages": [{"type": "human", "content": task, "additional_kwargs": {"attachments": [{"attachment_id": uploaded["attachment_id"]}]}}]},
            "context": {"agent_name": accepted["agent_name"], "subagent_enabled": False, "thinking_enabled": False, "is_plan_mode": False, "referenced_attachments": [{"attachment_id": uploaded["attachment_id"]}]},
            "config": {"recursion_limit": 1000},
            "stream_mode": ["updates", "values"],
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
        assert runs[0]["status"] == "success" and not state.get("next")
        messages = state["values"]["messages"]
        index = next(i for i, m in enumerate(messages) if m.get("type") == "human" and m.get("content") == task)
        calls = [c for m in messages[index:] for c in m.get("tool_calls", [])]
        assert any(c["name"] == "office_pdf" and c["args"].get("font_path") == uploaded["virtual_path"] for c in calls)
        assert any(c["name"] == "present_files" for c in calls)
        url = base + "/artifacts" + path + "?download=true"
        response = requester.get(url)
        assert response.status_code == 200
        data = response.content
        pdf = private / "chinese-report.pdf"
        pdf.write_bytes(data)
        pdf.chmod(0o600)
        decoded = subprocess.run(["pdftotext", str(pdf), "-"], capture_output=True, text=True, check=True).stdout
        assert all(word in decoded for word in ["中文项目进度报告", "PrismOS", "已完成", "待办", "OFFICE_TASK_"])
        assert all(client.get(url).status_code == 404 for client in [outsider, nonowner])
        requester.close()
        requester = login("requester")
        assert path in json.dumps(call(requester, graph + "/history", {"limit": 5}))
        again = requester.get(url)
        assert again.status_code == 200 and hashlib.sha256(again.content).digest() == hashlib.sha256(data).digest()
        result.update(
            {
                "complete": True,
                "run_id": runs[0]["run_id"],
                "run_status": runs[0]["status"],
                "artifact_url": url,
                "artifact_sha256": hashlib.sha256(data).hexdigest(),
                "artifact_bytes": len(data),
                "actual_tool_names": [c["name"] for c in calls],
                "model_used_owned_font_path": True,
                "independent_reader": "Poppler pdftotext",
                "extracted_text": decoded,
                "font_and_pdf_nonowner_denied": True,
                "fresh_login_history_and_download": True,
                "private_pdf": str(pdf),
            }
        )
    except Exception as error:
        result.update({"failure_type": type(error).__name__, "failure": str(error)})
        raise
    finally:
        for client in clients:
            client.close()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--font", type=Path)
    parser.add_argument("--reuse-font", type=Path)
    args = parser.parse_args()
    if not args.font and not args.reuse_font:
        parser.error("Provide an owned local font or an accepted font receipt")
    execute(args.source, args.output, args.font, args.reuse_font)
