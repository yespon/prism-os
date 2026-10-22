#!/usr/bin/env python3
"""Exercise production Compose in an owned PostgreSQL stack and clean it up."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import secrets
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
import subprocess as _sp

# The single current chain head, resolved from the repo at run time so the
# smoke never drifts behind new migrations.
EXPECTED_HEAD = _sp.run(
    ["uv", "run", "--frozen", "python", "-m", "alembic", "heads"],
    cwd=str(ROOT / "backend"), capture_output=True, text=True, check=True,
).stdout.split()[0]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend-image", required=True)
    parser.add_argument("--frontend-image", required=True)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    output = args.output_dir.resolve()
    if output.exists() and any(output.iterdir()):
        raise ValueError("Evidence output must be empty")
    output.mkdir(parents=True, exist_ok=True)
    evidence = {"passed": False, "m1_exit": False, "real_model_webhook": "not exercised", "remote_ci": "not run"}
    session_token = ""
    with tempfile.TemporaryDirectory(prefix="prismos-n07-runtime-") as temporary:
        stage = Path(temporary)
        project = "prismos-n07-" + secrets.token_hex(5)
        (stage / "home").mkdir()
        (stage / "langgraph").mkdir()
        config = yaml.safe_load((ROOT / "config.example.yaml").read_text())
        config["database"] = {
            "type": "postgres",
            "url": "postgresql+asyncpg://prismos:prismos@postgres:5432/prismos",
            "echo": False,
            "auth": {"type": "postgres", "url": "postgresql+asyncpg://prismos:prismos@postgres:5432/prismos_auth_db"},
        }
        config["checkpointer"] = {"type": "postgres", "connection_string": "postgresql://prismos:prismos@postgres:5432/prismos_checkpoints"}
        config["plugins"] = {key: {"enabled": False} for key in ["ops-alerting", "ops-assets", "ops-terminal"]}
        (stage / "config.yaml").write_text(yaml.safe_dump(config))
        services = {name: {"container_name": f"{project}-{name}", "restart": "no"} for name in ["db-init", "gateway", "langgraph", "frontend", "nginx", "postgres"]}
        for name in ["db-init", "gateway", "langgraph"]:
            services[name]["image"] = args.backend_image
        services["frontend"]["image"] = args.frontend_image
        services["nginx"]["image"] = "nginx:1.27-alpine"
        services["langgraph"]["volumes"] = [f"{stage}/langgraph:/app/backend/.langgraph_api"]
        (stage / "override.yaml").write_text(yaml.safe_dump({"services": services, "networks": {"prismos": {"name": project + "-network"}}, "volumes": {"postgres-data": {"name": project + "-postgres"}}}))
        environment = dict(os.environ)
        environment.update(
            {
                "PRISMOS_HOME": str(stage / "home"),
                "PRISMOS_CONFIG_PATH": str(stage / "config.yaml"),
                "PRISMOS_REPO_ROOT": str(ROOT),
                "PORT": "127.0.0.1:0",
                "PRISMOS_POSTGRES_USER": "prismos",
                "PRISMOS_POSTGRES_PASSWORD": "prismos",
                "PRISMOS_POSTGRES_DB": "prismos",
                "PRISMOS_TRUSTED_GRAPH_CONTEXT": "off",
                "PRISMOS_GOVERNED_TICKET_ACTION": "off",
                "PRISMOS_GOVERNED_TICKET_VERDICT": "deny",
                "PRISMOS_GOVERNED_TICKET_TENANT": "",
                "PRISMOS_TICKET_SECRET_ADMIN_TENANT": "",
                "DEERFLOW_SECRETS_ENCRYPTION_KEY": "",
                "LANGCHAIN_TRACING_V2": "false",
            }
        )
        compose = ["docker", "compose", "-p", project, "-f", str(ROOT / "docker/docker-compose.yaml"), "-f", str(stage / "override.yaml"), "--profile", "postgres"]

        def run(arguments, *, data=None):
            return subprocess.run(arguments, cwd=ROOT, env=environment, input=data, capture_output=True, check=True).stdout

        def execute(service, arguments):
            return run(["docker", "exec", *(["-w", "/app/backend"] if service != "postgres" else []), f"{project}-{service}", *arguments]).decode()

        def wait_healthy():
            deadline = time.monotonic() + 90
            while time.monotonic() < deadline:
                states = [run(["docker", "inspect", "--format", "{{.State.Health.Status}}", f"{project}-{name}"]).decode().strip() for name in ["postgres", "gateway", "langgraph", "frontend"]]
                if all(state == "healthy" for state in states):
                    return
                time.sleep(1)
            raise RuntimeError("Owned services did not become healthy")

        password = secrets.token_urlsafe(24)
        try:
            resolved = json.loads(run(compose + ["config", "--format", "json"]))
            for name in services:
                assert resolved["services"][name]["container_name"] == f"{project}-{name}"
            for name in ["db-init", "gateway", "langgraph", "frontend"]:
                for volume in resolved["services"][name].get("volumes", []):
                    if volume["target"] in ["/app/backend/.prismos", "/app/backend/.langgraph_api"]:
                        assert volume["source"].startswith(str(stage) + "/")
            result = subprocess.run(compose + ["up", "--no-build", "--wait", "--wait-timeout", "240"], cwd=ROOT, env=environment, capture_output=True)
            (output / "compose-up.log").write_bytes(result.stdout + result.stderr)
            result.check_returncode()
            address = run(compose + ["port", "nginx", "2026"]).decode().strip()
            base = "http://" + address

            def request(path, payload=None, *, method=None, authenticated=False, raw=False):
                headers = {"Content-Type": "application/json"}
                if authenticated:
                    headers["Authorization"] = "Bearer " + session_token
                req = urllib.request.Request(base + path, data=json.dumps(payload).encode() if payload is not None else None, headers=headers, method=method)
                try:
                    with urllib.request.urlopen(req, timeout=30) as response:
                        return response.status, response.read() if raw else json.load(response)
                except urllib.error.HTTPError as exc:
                    return exc.code, None

            def expect(path, payload=None, *, status=200, **kwargs):
                code, body = request(path, payload, **kwargs)
                if code != status:
                    raise RuntimeError(f"{path}: expected HTTP {status}, got {code}")
                return body

            expect("/api/agent-catalog/status", status=401)
            setup = expect("/api/auth/bootstrap-status")
            assert setup["needs_setup"]
            expect("/api/auth/setup-bootstrap-admin", {"user_id": setup["bootstrap_user_id"], "email": "n07-admin@example.invalid", "password": password})
            login = expect("/api/auth/login", {"email": "n07-admin@example.invalid", "password": password})
            session_token = login["session"]["token"]
            assert login["user"]["role"] == "admin"
            assert expect("/api/auth/session", authenticated=True)["user"]["id"] == login["user"]["id"]
            tenant = expect("/api/tenants/current", authenticated=True)
            catalog = expect("/api/agent-catalog/status", authenticated=True)
            assert catalog["integrity_verified"] and catalog["personas"] == 16
            created = expect("/api/agents", {"name": "n07-container-agent", "template_id": "expert:general-assistant", "persona_mbti": "INTJ"}, status=201, authenticated=True)
            edited = expect(
                "/api/agents/n07-container-agent",
                {"welcome_message": "N07 persisted", "avatar_id": "personas:ENFP", "persona_mbti": "ENFP", "system_prompt": "N07 base prompt", "quick_prompts": [{"title": "Inspect", "description": "", "prompt": "Inspect this draft"}]},
                method="PUT",
                authenticated=True,
            )
            assert edited["system_prompt"].count("## ENFP") == 1
            questions = expect("/api/agent-catalog/personality-test?locale=en", authenticated=True)
            assert len(questions["questions"]) == 28
            score = expect("/api/agent-catalog/personality-test", {"answers": {str(i): "A" for i in range(1, 29)}}, authenticated=True)
            assert score["automatic_apply"] is False
            expect("/api/agent-catalog/avatars/personas:ENFP", status=401)
            avatars = expect("/api/agent-catalog/avatars", authenticated=True)["avatars"]
            assert len(avatars) == 52
            svg = expect("/api/agent-catalog/avatars/personas:ENFP", authenticated=True, raw=True)
            assert hashlib.sha256(svg).hexdigest() == next(a["sha256"] for a in avatars if a["id"] == "personas:ENFP")
            expect("/", raw=True)
            expect("/api/langgraph/threads", {}, status=401)
            thread = expect("/api/langgraph/threads", {}, authenticated=True)
            expect(f"/api/langgraph/threads/{thread['thread_id']}/state", authenticated=True)
            resource_check = execute(
                "gateway",
                [
                    "uv",
                    "run",
                    "--frozen",
                    "python",
                    "-c",
                    """import hashlib,json,sys
from pathlib import Path
import prismos_octop
root=Path(prismos_octop.__file__).parent
p=json.loads((root/'data/provenance.json').read_text())
for item in p['imports']:
 assert hashlib.sha256((root/item['target']).read_bytes()).hexdigest()==item['sha256']
print(json.dumps({'verified_files':len(p['imports']),'provenance_sha256':hashlib.sha256((root/'data/provenance.json').read_bytes()).hexdigest(),'python':sys.version.split()[0]}))""",
                ],
            )
            resources = json.loads(resource_check)
            assert resources["verified_files"] == 902
            host_provenance = ROOT / "backend/packages/octop-capabilities/src/prismos_octop/data/provenance.json"
            assert resources["provenance_sha256"] == hashlib.sha256(host_provenance.read_bytes()).hexdigest()
            migration = execute("gateway", ["uv", "run", "--frozen", "alembic", "current"]).strip()
            assert EXPECTED_HEAD in migration
            runtime = execute("gateway", ["sh", "-c", "python --version && node --version && npm --version && npx --version && uv --version"]).strip()
            image_ids = {name: run(["docker", "inspect", "--format", "{{.Image}}", f"{project}-{name}"]).decode().strip() for name in services}
            dump = run(["docker", "exec", f"{project}-postgres", "pg_dump", "-U", "prismos", "-d", "prismos", "-Fc"])
            run(["docker", "exec", f"{project}-postgres", "createdb", "-U", "prismos", "prismos_restore"])
            run(["docker", "exec", "-i", f"{project}-postgres", "pg_restore", "-U", "prismos", "-d", "prismos_restore"], data=dump)
            restored = run(["docker", "exec", f"{project}-postgres", "psql", "-U", "prismos", "-d", "prismos_restore", "-Atc", "SELECT version_num FROM alembic_version"]).decode().strip()
            assert restored == EXPECTED_HEAD
            restored_agent = run(["docker", "exec", f"{project}-postgres", "psql", "-U", "prismos", "-d", "prismos_restore", "-Atc", "SELECT count(*) FROM custom_agents WHERE name='n07-container-agent'"]).decode().strip()
            assert restored_agent == "1"
            guards = {}
            for service in ["gateway", "langgraph"]:
                guards[service] = json.loads(
                    execute(service, ["uv", "run", "--frozen", "python", "-c", "import os,json;print(json.dumps({key:os.environ.get(key) for key in ['PRISMOS_GOVERNED_TICKET_ACTION','PRISMOS_TRUSTED_GRAPH_CONTEXT']}))"])
                )
                assert guards[service]["PRISMOS_GOVERNED_TICKET_ACTION"] == "off"
                assert guards[service]["PRISMOS_TRUSTED_GRAPH_CONTEXT"] == "off"
            run(compose + ["restart", "postgres", "gateway", "langgraph", "frontend"])
            wait_healthy()
            reopened = expect("/api/agents/n07-container-agent", authenticated=True)
            assert reopened["id"] == created["id"] and reopened["presentation"]["welcome_message"] == "N07 persisted"
            assert reopened["presentation"]["persona_mbti"] == "ENFP"
            assert reopened["presentation"]["quick_prompts"] == edited["presentation"]["quick_prompts"]
            assert expect("/api/auth/session", authenticated=True)["user"]["id"] == login["user"]["id"]
            admin_count = execute("postgres", ["psql", "-U", "prismos", "-d", "prismos_auth_db", "-Atc", "SELECT count(*) FROM \"user\" WHERE role='admin'"]).strip()
            assert admin_count == "1"
            evidence.update(
                {
                    "passed": True,
                    "project": project,
                    "services": list(services),
                    "image_ids": image_ids,
                    "resources": resources,
                    "runtime_versions": runtime,
                    "migration_head": EXPECTED_HEAD,
                    "bootstrap_setup_login_session": True,
                    "single_bootstrap_admin_after_restart": True,
                    "tenant_context": tenant,
                    "catalog": catalog,
                    "agent_created_edited_reopened": True,
                    "questionnaire_readonly": True,
                    "avatars_authenticated_hash_verified": True,
                    "gateway_langgraph_thread_proxy": True,
                    "checkpoint_backend_configured": "postgres; no model run/persistent M2 asserted",
                    "postgres_restart": True,
                    "session_and_agent_preserved": True,
                    "backup_restore_head": restored,
                    "backup_restored_agent": True,
                    "runtime_guards": guards,
                    "backup_bytes": len(dump),
                    "backup_sha256": hashlib.sha256(dump).hexdigest(),
                    "governed_action": "off",
                    "plugins_disabled_for_isolation": list(config["plugins"]),
                }
            )
        except Exception as exc:
            evidence["error"] = type(exc).__name__ + ": " + str(exc)
            raise
        finally:
            logs = subprocess.run(compose + ["logs", "--no-color", "--tail", "500"], cwd=ROOT, env=environment, capture_output=True, text=True)
            service_logs = (logs.stdout + logs.stderr).replace(password, "[test password]")
            if session_token:
                service_logs = service_logs.replace(session_token, "[test session]")
            (output / "services.log").write_text(service_logs)
            cleanup = subprocess.run(compose + ["down", "--volumes", "--timeout", "10"], cwd=ROOT, env=environment, capture_output=True)
            (output / "compose-down.log").write_bytes(cleanup.stdout + cleanup.stderr)
            evidence["cleanup_returncode"] = cleanup.returncode
            evidence["remaining_owned_containers"] = run(["docker", "ps", "-a", "--filter", f"label=com.docker.compose.project={project}", "--format", "{{.Names}}"]).decode().splitlines()
            for resource in ["network", "volume"]:
                evidence[f"remaining_owned_{resource}s"] = run(["docker", resource, "ls", "--filter", f"label=com.docker.compose.project={project}", "--format", "{{.Name}}" if resource == "network" else "{{.Name}}"]).decode().splitlines()
            clean = cleanup.returncode == 0 and not any(evidence[key] for key in ["remaining_owned_containers", "remaining_owned_networks", "remaining_owned_volumes"])
            if not clean:
                evidence["passed"] = False
            (output / "validation.json").write_text(json.dumps(evidence, indent=2, ensure_ascii=False) + "\n")
            if not clean:
                raise RuntimeError("Owned verification resources remain after cleanup")
    print(json.dumps({"passed": evidence["passed"], "m1_exit": False, "owned_resources_cleaned": True}))


if __name__ == "__main__":
    main()
