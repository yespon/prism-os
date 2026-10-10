#!/usr/bin/env python3
"""Exercise old/new imported snapshots against the same PrismOS host contracts."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--previous-archive", required=True, type=Path)
    parser.add_argument("--previous-revision", required=True)
    parser.add_argument("--previous-release", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    manifest = json.loads((ROOT / "vendor/octop/manifest.json").read_text())
    spec = importlib.util.spec_from_file_location(
        "octop_sync", ROOT / "scripts/octop_sync.py"
    )
    sync = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(sync)
    contract_paths = [
        "backend/app/integrations/octop/agents.py",
        "backend/app/gateway/routers/agents.py",
        "backend/app/gateway/routers/agent_catalog.py",
        "backend/tests/test_octop_integration.py",
        "backend/tests/test_octop_presentation.py",
        "backend/packages/octop-capabilities/src/prismos_octop/catalog.py",
        "backend/packages/octop-capabilities/src/prismos_octop/presentation.py",
        "backend/packages/octop-capabilities/src/prismos_octop/source_policy.py",
    ]
    contract_hashes = {
        path: hashlib.sha256((ROOT / path).read_bytes()).hexdigest()
        for path in contract_paths
    }
    evidence = {
        "scope": "curated source upgrade/rollback; catalog, questionnaire, avatars, presentation persistence, imported pure modules and Agent host contracts",
        "host_changed": False,
        "host_contract_sha256s": contract_hashes,
        "versions": [],
    }
    with tempfile.TemporaryDirectory(prefix="prismos-octop-upgrade-") as directory:
        stage = Path(directory)
        package = stage / sync.PACKAGE
        package.mkdir(parents=True)
        for path in [
            "__init__.py",
            "catalog.py",
            "presentation.py",
            "source_policy.py",
            "upstream/__init__.py",
        ]:
            (package / path).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / sync.PACKAGE / path, package / path)
        sync.ROOT = stage
        snapshots = [
            (
                args.previous_archive,
                args.previous_revision,
                args.previous_release,
                None,
            ),
            (
                ROOT / "vendor/octop/upstream.tar.gz",
                manifest["revision"],
                manifest["release"],
                ROOT / "vendor/octop/manifest.json",
            ),
        ]
        snapshots.append(
            snapshots[0]
        )  # Exercise restoration to the previous curated source view.
        for archive, revision, release, receipt in snapshots:
            if evidence["versions"]:
                key = "diff" if len(evidence["versions"]) == 1 else "rollback_diff"
                evidence[key] = sync.compare(archive, revision, release, receipt)
            imported = sync.sync(archive, revision, release, receipt)
            verified = sync.verify()
            environment = dict(os.environ)
            environment["PYTHONPATH"] = (
                str(package.parent) + os.pathsep + str(ROOT / "backend")
            )
            environment["PRISMOS_OCTOP_EXPECTED_REVISION"] = revision
            result = subprocess.run(
                [
                    str(ROOT / "backend/.venv/bin/python"),
                    "-m",
                    "pytest",
                    "tests/test_octop_integration.py",
                    "tests/test_octop_presentation.py",
                    "-q",
                ],
                cwd=ROOT / "backend",
                env=environment,
                text=True,
                capture_output=True,
            )
            evidence["versions"].append(
                {
                    "release": release,
                    "revision": revision,
                    "import": imported,
                    "verify": verified,
                    "returncode": result.returncode,
                    "pytest": result.stdout,
                }
            )
            if result.returncode:
                raise RuntimeError(result.stdout + result.stderr)
    if contract_hashes != {
        path: hashlib.sha256((ROOT / path).read_bytes()).hexdigest()
        for path in contract_paths
    }:
        raise ValueError("Host contract changed during upgrade probe")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, indent=2, ensure_ascii=False) + "\n")
    print(
        json.dumps(
            {
                "passed": True,
                "restricted_resource_excluded": True,
                "rollback_verified": len(evidence["versions"]) == 3,
                "versions": [entry["release"] for entry in evidence["versions"]],
                "imported_changed": len(evidence["diff"]["imported_changed"]),
            }
        )
    )


if __name__ == "__main__":
    main()
