#!/usr/bin/env python3
"""Actual Skill recovery tests against an owned, disposable PostgreSQL instance."""

import argparse
import json
import os
import secrets
import subprocess
import sys
import time
import uuid
from pathlib import Path

from sqlalchemy.engine import make_url

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", default="postgres:16-alpine")
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    if not args.output_dir.is_absolute() or args.output_dir.exists():
        parser.error("output-dir must be a new absolute evidence directory")
    subprocess.run(
        ["docker", "image", "inspect", args.image], check=True, capture_output=True
    )
    args.output_dir.mkdir(parents=True)
    name = "prismos-skill-probe-" + uuid.uuid4().hex[:12]
    password = secrets.token_urlsafe(32)
    owned = False
    try:
        result = subprocess.run(
            [
                "docker",
                "run",
                "--detach",
                "--name",
                name,
                "--label",
                "prismos.probe=skill-import",
                "--memory=512m",
                "--cpus=2",
                "--publish",
                "127.0.0.1::5432",
                "--tmpfs",
                "/var/lib/postgresql/data",
                "--env",
                "POSTGRES_USER=prismos_test",
                "--env",
                "POSTGRES_DB=prismos_skill_probe",
                "--env",
                "POSTGRES_PASSWORD=" + password,
                args.image,
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        owned = True
        container_id = result.stdout.strip()
        for _ in range(60):
            ready = subprocess.run(
                [
                    "docker",
                    "exec",
                    name,
                    "pg_isready",
                    "-U",
                    "prismos_test",
                    "-d",
                    "prismos_skill_probe",
                ],
                capture_output=True,
            )
            if ready.returncode == 0:
                break
            time.sleep(0.5)
        else:
            raise RuntimeError("Owned PostgreSQL did not become ready")
        port = (
            subprocess.check_output(["docker", "port", name, "5432/tcp"], text=True)
            .strip()
            .rsplit(":", 1)[1]
        )
        url = (
            make_url("postgresql+asyncpg://prismos_test@127.0.0.1/prismos_skill_probe")
            .set(password=password, port=int(port))
            .render_as_string(hide_password=False)
        )
        environment = dict(os.environ, PRISMOS_SKILL_TEST_DB_URL=url)
        with (args.output_dir / "pytest.log").open("w") as log:
            run = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "pytest",
                    "tests/test_skill_import_recovery.py",
                    "tests/test_skill_resource_identity.py",
                    "tests/test_skill_mutation_boundaries.py",
                    "tests/test_skill_enablement_boundaries.py",
                    "tests/test_skill_manual_creation.py",
                    "tests/test_skill_resource_deletion.py",
                    "tests/test_skill_reference_transactions.py",
                    "tests/test_agent_skill_references.py",
                    "-q",
                ],
                cwd=ROOT / "backend",
                env=environment,
                stdout=log,
                stderr=subprocess.STDOUT,
            )
        version = subprocess.check_output(
            [
                "docker",
                "exec",
                name,
                "psql",
                "-U",
                "prismos_test",
                "-d",
                "prismos_skill_probe",
                "-At",
                "-c",
                "select version()",
            ],
            text=True,
        ).strip()
        evidence = {
            "passed": run.returncode == 0,
            "database": version,
            "container_id": container_id,
            "loopback_only": True,
            "owned_tmpfs_database": True,
            "schema": "existing SQLModel metadata including native TenantSkill uniqueness; no production database",
            "cases": "import recovery, identity, mutation, enablement, creation, deletion and two-connection Agent reference ordering",
            "credentials_in_evidence": False,
            "returncode": run.returncode,
        }
        (args.output_dir / "postgres.json").write_text(
            json.dumps(evidence, indent=2) + "\n"
        )
        if run.returncode:
            raise RuntimeError(
                "Skill recovery PostgreSQL tests failed; see owned pytest.log"
            )
    finally:
        if owned:
            subprocess.run(
                ["docker", "rm", "--force", name], check=True, capture_output=True
            )
            if (args.output_dir / "postgres.json").is_file():
                evidence = json.loads((args.output_dir / "postgres.json").read_text())
                evidence["owned_container_removed"] = True
                (args.output_dir / "postgres.json").write_text(
                    json.dumps(evidence, indent=2) + "\n"
                )
    print(
        json.dumps(
            {
                "passed": True,
                "owned_container_removed": True,
                "evidence": str(args.output_dir),
            }
        )
    )


if __name__ == "__main__":
    main()
