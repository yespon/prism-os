#!/usr/bin/env python3
"""Boot real Gateway and migrations against temporary databases, then exercise auth."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import secrets
import socket
import sqlite3
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
import zipfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="prismos-octop-smoke-") as folder:
        directory = Path(folder)
        config = yaml.safe_load((ROOT / "config.example.yaml").read_text())
        config["database"]["url"] = f"sqlite+aiosqlite:///{directory}/tenant.db"
        config["database"]["auth"]["url"] = f"sqlite+aiosqlite:///{directory}/auth.db"
        config["plugins"] = {key: {"enabled": False} for key in ["ops-alerting", "ops-assets", "ops-terminal"]}
        (directory / "config.yaml").write_text(yaml.safe_dump(config))
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        environment = {
            key: os.environ[key]
            for key in (
                "PATH",
                "HOME",
                "LANG",
                "LC_ALL",
                "SYSTEMROOT",
                "TEMP",
                "TMP",
                "TMPDIR",
            )
            if key in os.environ
        }
        environment.update(
            PRISMOS_CONFIG_PATH=str(directory / "config.yaml"),
            PRISMOS_HOME=str(directory / "home"),
            AUTH_DB_URL=f"sqlite+pysqlite:///{directory}/auth.db",
            PYTHONPATH=str(ROOT / "backend"),
        )
        isolated_skills = directory / "skills"
        (directory / "gateway_probe_entry.py").write_text(f"""
from pathlib import Path
from app.gateway.app import app
from app.gateway.routers import skills
from app.integrations import skill_imports
from app.integrations.octop import resource_installations
from deerflow.skills import loader,installer
for module in (loader,skills,skill_imports,resource_installations,installer):
    module.get_skills_root_path = lambda: Path({str(isolated_skills)!r})
""")
        environment["PYTHONPATH"] = str(directory) + os.pathsep + str(ROOT / "backend")
        base = f"http://127.0.0.1:{port}"

        def request(path, body=None, token=None, method=None, raw=False):
            headers = {"Content-Type": "application/json"}
            if token:
                headers["Authorization"] = "Bearer " + token
            req = urllib.request.Request(
                base + path,
                data=json.dumps(body).encode() if body is not None else None,
                headers=headers,
                method=method,
            )
            try:
                with urllib.request.urlopen(req, timeout=10) as response:
                    return response.status, response.read() if raw else json.load(response)
            except urllib.error.HTTPError as exc:
                return exc.code, json.load(exc)

        with (directory / "gateway.log").open("w+") as log:
            process = subprocess.Popen(
                [
                    str(ROOT / "backend/.venv/bin/python"),
                    "-m",
                    "uvicorn",
                    "gateway_probe_entry:app",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    str(port),
                ],
                cwd=ROOT / "backend",
                env=environment,
                stdout=log,
                stderr=log,
            )
            try:
                deadline = time.monotonic() + 60
                while time.monotonic() < deadline:
                    if process.poll() is not None:
                        raise RuntimeError("Gateway exited during startup")
                    try:
                        if request("/health")[0] == 200:
                            break
                    except (urllib.error.URLError, ConnectionError):
                        pass
                    time.sleep(0.2)
                else:
                    raise RuntimeError("Gateway startup timed out")
                assert request("/api/agent-catalog/templates")[0] == 401
                token = secrets.token_urlsafe(32)
                now = datetime.now(UTC)
                with sqlite3.connect(directory / "auth.db") as database:
                    database.execute(
                        'INSERT INTO "user" (id,name,email,"emailVerified","createdAt","updatedAt",role,status,"mustChangePassword") VALUES (?,?,?,?,?,?,?,?,?)',
                        (
                            "catalog-smoke-user",
                            "Catalog Smoke",
                            "catalog-smoke@example.invalid",
                            0,
                            now.isoformat(),
                            now.isoformat(),
                            "user",
                            "active",
                            0,
                        ),
                    )
                    database.execute(
                        'INSERT INTO session (id,"expiresAt",token,"createdAt","updatedAt","userId") VALUES (?,?,?,?,?,?)',
                        (
                            "catalog-smoke-session",
                            (now + timedelta(hours=1)).isoformat(),
                            token,
                            now.isoformat(),
                            now.isoformat(),
                            "catalog-smoke-user",
                        ),
                    )
                code, catalog = request("/api/agent-catalog/status", token=token)
                assert code == 200 and catalog["integrity_verified"] and catalog["personas"] == 16
                code, created = request(
                    "/api/agents",
                    {
                        "name": "catalog-smoke",
                        "template_id": "expert:general-assistant",
                        "persona_mbti": "INTJ",
                    },
                    token,
                )
                assert code == 201 and "INTJ" in created["system_prompt"]
                code, reloaded = request("/api/agents/catalog-smoke", token=token)
                assert code == 200 and reloaded["id"] == created["id"]
                assert reloaded["presentation"]["persona_mbti"] == "INTJ"
                assert reloaded["presentation"]["welcome_message"]
                assert reloaded["presentation"]["quick_prompts"]
                base_prompt = "Gateway edited base prompt"
                update = {
                    "system_prompt": base_prompt,
                    "persona_mbti": "ENFP",
                    "template_locale": "en",
                    "welcome_message": "Gateway welcome",
                    "avatar_id": "personas:ENFP",
                    "quick_prompts": [
                        {
                            "title": "Inspect",
                            "prompt": "Inspect this draft",
                            "description": "",
                        }
                    ],
                }
                for _ in range(2):
                    code, edited = request("/api/agents/catalog-smoke", update, token, method="PUT")
                    assert code == 200 and edited["base_system_prompt"] == base_prompt
                code, reloaded = request("/api/agents/catalog-smoke", token=token)
                assert code == 200 and reloaded["presentation"]["welcome_message"] == "Gateway welcome"
                assert reloaded["presentation"]["avatar_id"] == "personas:ENFP"
                assert reloaded["presentation"]["quick_prompts"] == update["quick_prompts"]
                assert reloaded["system_prompt"].count("## ENFP") == 1
                assert reloaded["skills"] == [] and reloaded["tool_groups"] == []
                code, test = request("/api/agent-catalog/personality-test?locale=en", token=token)
                assert code == 200 and len(test["questions"]) == 28
                code, scored = request(
                    "/api/agent-catalog/personality-test",
                    {"answers": {str(i): "A" for i in range(1, 29)}},
                    token,
                )
                assert code == 200 and scored["code"] == "ESTJ" and scored["automatic_apply"] is False
                assert request("/api/agents/catalog-smoke", token=token)[1]["presentation"]["persona_mbti"] == "ENFP"
                assert request("/api/agent-catalog/avatars")[0] == 401
                code, avatars = request("/api/agent-catalog/avatars", token=token)
                assert code == 200 and len(avatars["avatars"]) == 52
                code, image = request("/api/agent-catalog/avatars/personas:ENFP", token=token, raw=True)
                assert code == 200 and hashlib.sha256(image).hexdigest() == next(item["sha256"] for item in avatars["avatars"] if item["id"] == "personas:ENFP")
                assert request("/api/agent-catalog/templates/expert:cvm-ai-doctor/resources")[0] == 401
                resource_files = 0
                for template in request("/api/agent-catalog/templates?kind=expert", token=token)[1]["templates"]:
                    code, resources = request("/api/agent-catalog/templates/" + template["id"] + "/resources", token=token)
                    assert code == 200 and resources["source_verified"] and not resources["permission_grants"]
                    assert not resources["installation_checked"] and not resources["execution_ready"]
                    resource_files += resources["member_count"]
                assert resource_files == 297
                with sqlite3.connect(directory / "tenant.db") as database:
                    config_count_before = database.execute("SELECT count(*) FROM user_configs").fetchone()[0]
                code, scoped = request("/api/agent-catalog/templates/expert:ai-coding-coach/resources?check_installation=true", token=token)
                assert code == 200 and scoped["installation_checked"] and not scoped["permission_grants"]
                source_skill = next(r for r in scoped["resources"] if r["kind"] == "skill_bundle")
                archive_url = "/api/agent-catalog/templates/expert:ai-coding-coach/resources/" + source_skill["id"] + "/archive"
                assert request(archive_url)[0] == 401
                code, package = request(archive_url, token=token, raw=True)
                assert code == 200
                with zipfile.ZipFile(io.BytesIO(package)) as archive:
                    assert all(name.startswith(source_skill["host_adaptation"]["name"] + "/") for name in archive.namelist())
                    assert any(name.endswith("/PRISMOS_ORIGIN.json") for name in archive.namelist())
                    assert any(name.endswith("/LICENSE.octop") for name in archive.namelist())
                with sqlite3.connect(directory / "tenant.db") as database:
                    assert database.execute("SELECT count(*) FROM user_configs").fetchone()[0] == config_count_before
                install_url = archive_url.removesuffix("/archive") + "/install"
                install_body = {"scope": "personal", "bundle_sha256": source_skill["bundle_sha256"]}
                assert request(install_url, install_body)[0] == 401
                assert request(install_url, {**install_body, "scope": "tenant"}, token)[0] == 403
                code, imported = request(install_url, install_body, token)
                assert code == 201 and imported["registered"] and not imported["execution_ready"]
                operation_url = "/api/skills/personal/imports/" + imported["operation_id"]
                assert request(operation_url)[0] == 401
                operation_status = request(operation_url, token=token)
                if operation_status[0] != 200:
                    with sqlite3.connect(directory / "tenant.db") as database:
                        rows = database.execute("SELECT tenant_id,user_id,name,install_dir FROM tenant_skills").fetchall()
                    receipts = [str(path.relative_to(directory)) for path in directory.rglob(".prismos-import-*.json")]
                    raise AssertionError({"operation_response": operation_status, "probe_rows": rows, "probe_receipts": receipts})
                assert operation_status[1]["registered"]
                assert request(operation_url + "/recover", token=token, method="POST")[1]["registered"]
                assert request(install_url, install_body, token)[0] == 409
                list_url = "/api/skills/personal/imports?page_size=1"
                assert request(list_url)[0] == 401
                code, first_page = request(list_url, token=token)
                assert code == 200 and first_page["next_cursor"] and first_page["total"] == 2
                assert first_page["retention"] == {"mode": "retain_all", "automatic_deletion": False, "maintenance": "owned_stage_abort_only"}
                cursor_url = list_url + "&cursor=" + first_page["next_cursor"]
                code, second_page = request(cursor_url, token=token)
                assert code == 200 and second_page["next_cursor"] is None
                assert first_page["operations"][0]["operation_id"] != second_page["operations"][0]["operation_id"]
                assert {item["operation_id"] for item in first_page["operations"] + second_page["operations"]} >= {imported["operation_id"]}
                assert request("/api/tenants/skills/imports?page_size=1&cursor=" + first_page["next_cursor"], token=token)[0] == 403
                code, after_install = request("/api/agent-catalog/templates/expert:ai-coding-coach/resources?check_installation=true", token=token)
                assert code == 200
                installed = next(r for r in after_install["resources"] if r["id"] == source_skill["id"])
                assert installed["installation"]["status"] == "source_match"
                with sqlite3.connect(directory / "tenant.db") as database:
                    assert database.execute("SELECT count(*) FROM tenant_skills").fetchone()[0] == 1
                assert request("/api/agents/catalog-smoke", token=token)[1]["skills"] == []
                with sqlite3.connect(directory / "tenant.db") as database:
                    source = json.loads(
                        database.execute(
                            "SELECT metadata FROM custom_agents WHERE id=?",
                            (created["id"],),
                        ).fetchone()[0]
                    )
                    migration = database.execute("SELECT version_num FROM alembic_version").fetchone()[0]
                assert source["octop_source"]["revision"] == catalog["revision"]
                result = {
                    "passed": True,
                    "gateway": "real uvicorn process",
                    "auth": "real Better Auth session and tenant membership",
                    "migration_head": migration,
                    "catalog": catalog,
                    "agent_created_and_reloaded": True,
                    "presentation_edited_and_reopened": True,
                    "duplicate_persona_prevented": True,
                    "questionnaire_readonly": True,
                    "resource_preflight_all_experts_readonly": True,
                    "scoped_installation_checks_without_config_creation": True,
                    "fixed_upstream_skill_archive_authenticated": True,
                    "upstream_license_in_skill_archive": True,
                    "declared_resource_members": resource_files,
                    "avatars_authenticated_and_hash_verified": True,
                    "temporary_databases": True,
                    "temporary_skill_root": True,
                    "explicit_source_install_and_recovery": True, "scoped_receipt_pagination_and_retention": True,
                    "installation_does_not_bind_agent_or_grant_execution": True,
                }
                if args.output:
                    args.output.parent.mkdir(parents=True, exist_ok=True)
                    args.output.write_text(json.dumps(result, indent=2) + "\n")
                print(json.dumps(result))
            except Exception:
                log.flush()
                log.seek(0)
                # Temporary environment contains no imported deployment credentials.
                print(log.read()[-12000:])
                raise
            finally:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()


if __name__ == "__main__":
    main()
