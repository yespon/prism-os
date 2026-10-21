"""Existing terminal UI API → real model/SSH commands → original chat history."""

import argparse
import hashlib
import json
from pathlib import Path
import secrets
import uuid

import httpx

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / "backend/tmp/n04-wsl/native-profile"


def execute(output, resume=None):
    assert not output.exists()
    users = json.loads((STATE / "live-fixture.json").read_text())
    target = json.loads((STATE / "ssh-service/fixture.json").read_text())
    previous = json.loads(resume.read_text()) if resume else None
    private = STATE / ("ssh-task-" + secrets.token_hex(5))
    private.mkdir(mode=0o700)
    result = (
        dict(previous)
        if previous
        else {
            "complete": False,
            "actual_model": users["model_name"],
            "simulated_model": False,
            "asset_id": target["asset"]["id"],
        }
    )
    result.update(
        complete=False, private_diagnostics=str(private), new_model_task_submissions=0
    )
    clients = []

    def save():
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")

    def request(client, path, body=None, status=200):
        response = client.request(
            "POST" if body is not None else "GET", path, json=body
        )
        assert response.status_code == status, (path, response.status_code)
        return response.json()

    def login(role):
        account = users["users"][role]
        client = httpx.Client(
            base_url="http://127.0.0.1:18036",
            headers={
                "X-Tenant-Id": users["other_tenant_id"]
                if role == "outsider"
                else users["tenant_id"]
            },
            timeout=300,
            trust_env=False,
        )
        clients.append(client)
        session = request(
            client,
            "/api/auth/login",
            {"email": account["email"], "password": account["password"]},
        )
        client.headers["Authorization"] = "Bearer " + session["session"]["token"]
        return client

    try:
        owner, nonowner, outsider = [
            login(role) for role in ["requester", "approver", "outsider"]
        ]
        if previous is None:
            chat = str(uuid.uuid4())
            task = "这是自有隔离SSH测试主机。请通过已选主机的真实终端工具读取 /home/target/fixture.txt，并执行 uname -s。使用实际工具结果回答文件里的原样验收标识和系统名称；不要推测、不要写文件或访问网络，不要切换root。"
            request(
                owner,
                "/api/v1/terminal/chats",
                {
                    "task_id": chat,
                    "title": "Real SSH read-only task",
                    "model_name": users["model_name"],
                    "mode": "agent",
                    "asset_id": target["asset"]["id"],
                    "asset_ip": "127.0.0.1",
                    "messages": [{"role": "user", "content": task}],
                },
            )
            result["chat_id"] = chat
            save()
            payload = {
                "session_id": chat,
                "terminal_session_id": chat,
                "model_name": users["model_name"],
                "asset_id": target["asset"]["id"],
                "selected_assets": [target["asset"]],
                "mode": "agent",
                "user_input": task,
            }
            with owner.stream("POST", "/api/terminal/chat", json=payload) as response:
                result["entry_status"] = response.status_code
                assert response.status_code == 200, (
                    "Original terminal UI entry",
                    response.status_code,
                )
                result["new_model_task_submissions"] = 1
                transcript = "\n".join(response.iter_lines())
            raw = private / "stream.txt"
            raw.write_text(transcript)
            raw.chmod(0o600)
            events = [
                json.loads(line[5:])
                for line in transcript.splitlines()
                if line.startswith("data:")
            ]
            result["event_types"] = sorted({event.get("type") for event in events})
            errors = [event for event in events if event.get("type") == "RUN_ERROR"]
            assert not errors, [
                ("model/terminal run", event.get("message")) for event in errors
            ]
            assert "RUN_FINISHED" in result["event_types"]
            assert "TOOL_APPROVAL_REQUIRED" not in result["event_types"], (
                "Approval must be handled through original explicit flow"
            )
            tool_results = [
                event for event in events if event.get("type") == "TOOL_CALL_RESULT"
            ]
            assert target["marker"] in json.dumps(
                tool_results
            ) and "Linux" in json.dumps(tool_results)
            final_text = "".join(
                event.get("delta", "")
                for event in events
                if event.get("type") == "TEXT_MESSAGE_CONTENT"
            )
            assert target["marker"] in final_text and "Linux" in final_text
            result["tool_names"] = sorted(
                {
                    event.get("toolCallName")
                    for event in events
                    if event.get("type") == "TOOL_CALL_START"
                }
            )
            # Follow the original terminal UI's explicit transcript-save API;
            # this is not a new durable graph checkpoint implementation.
            messages = [
                {"role": "user", "content": task},
                {
                    "role": "assistant",
                    "content": final_text,
                    "tool_results": tool_results,
                },
            ]
            request(
                owner,
                "/api/v1/terminal/chats",
                {
                    "task_id": chat,
                    "title": "Real SSH read-only task",
                    "model_name": users["model_name"],
                    "messages": messages,
                },
            )
            result["history_messages_sha256"] = hashlib.sha256(
                json.dumps(messages, ensure_ascii=False, sort_keys=True).encode()
            ).hexdigest()
        chat = result["chat_id"]
        owner.close()
        owner = login("requester")
        history = request(owner, "/api/v1/terminal/chats/" + chat)
        messages = history["messages"]
        digest = hashlib.sha256(
            json.dumps(messages, ensure_ascii=False, sort_keys=True).encode()
        ).hexdigest()
        assert digest == result["history_messages_sha256"]
        assert target["marker"] in json.dumps(messages) and "Linux" in json.dumps(
            messages
        )
        assert nonowner.get("/api/v1/terminal/chats/" + chat).status_code == 404
        assert outsider.get("/api/v1/terminal/chats/" + chat).status_code == 404
        assert all(
            row["id"] != target["asset"]["id"]
            for row in request(nonowner, "/api/v1/assets/local")
        )
        assert all(
            row["id"] != target["asset"]["id"]
            for row in request(outsider, "/api/v1/assets/local")
        )
        private_key = (STATE / "ssh-service/id_ed25519").read_text()
        assert private_key not in json.dumps(history)
        result.update(
            complete=True,
            actual_ssh_result_and_model_answer_verified=True,
            original_ui_history_save_and_fresh_login_verified=True,
            nonowner_and_cross_tenant_denied=True,
            private_key_not_in_history=True,
        )
    except Exception as error:
        result.update(failure_type=type(error).__name__, failure=str(error))
        raise
    finally:
        for client in clients:
            client.close()
        save()
    print("Original terminal Agent actual SSH read-only task accepted")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--resume", type=Path)
    args = parser.parse_args()
    execute(args.output, args.resume)
