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
    parser.add_argument("--previous-receipt", type=Path)
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
        "backend/app/integrations/octop/resources.py",
        "backend/app/integrations/octop/resource_installations.py",
        "backend/app/integrations/octop/skill_packages.py",
        "backend/app/integrations/skill_imports.py",
        "backend/app/integrations/skill_mutations.py",
        "backend/tests/test_skill_mutation_boundaries.py",
        "backend/tests/test_skill_enablement_boundaries.py",
        "backend/tests/test_skill_manual_creation.py",
        "backend/tests/test_skill_resource_deletion.py",
        "backend/tests/test_skill_deletion_process.py",
        "backend/tests/test_skill_member_tools.py",
        "backend/tests/test_skill_reference_transactions.py",
        "backend/tests/test_agent_skill_references.py",
        "backend/tests/test_diagnosis_authorization.py",
        "backend/tests/test_runtime_adapters.py",
        "backend/tests/test_incident_diagnosis.py",
        "backend/tests/test_governed_ticket.py",
        "backend/app/alerting/governed_ticket_tool.py",
        "backend/app/alerting/governed_read_tool.py",
        "backend/tests/test_langgraph_proxy.py",
        "backend/app/alerting/diagnosis_authorization.py",
        "backend/app/platform/execution/trust.py",
        "backend/app/alerting/ingest.py",
        "backend/app/alerting/diagnosis_helper.py",
        "backend/app/gateway/routers/alerts.py",
        "backend/app/gateway/routers/langgraph_proxy.py",
        "backend/app/integrations/agent_skill_references.py",
        "backend/app/integrations/agent_skill_members.py",
        "backend/packages/harness/deerflow/sandbox/tools.py",
        "backend/app/runtime_adapters.py",
        "backend/packages/harness/deerflow/runtime.py",
        "backend/packages/harness/deerflow/agents/lead_agent/agent.py",
        "backend/packages/harness/deerflow/agents/lead_agent/prompt.py",
        "backend/app/integrations/skill_reference_transactions.py",
        "backend/app/integrations/skill_deletions.py",
        "backend/packages/harness/deerflow/skills/resource_deletion_files.py",
        "backend/packages/harness/deerflow/database/user_config_service.py",
        "backend/packages/harness/deerflow/skills/loader.py",
        "backend/packages/harness/deerflow/skills/resource_identity.py",
        "backend/tests/test_skill_resource_identity.py",
        "backend/packages/harness/deerflow/skills/install_receipts.py",
        "backend/app/gateway/routers/agents.py",
        "backend/app/gateway/routers/agent_catalog.py",
        "backend/app/gateway/routers/skills.py",
        "backend/packages/harness/deerflow/skills/installer.py",
        "backend/packages/harness/deerflow/skills/validation.py",
        "backend/tests/test_octop_integration.py",
        "backend/tests/test_octop_presentation.py",
        "backend/tests/test_octop_resources.py",
        "backend/tests/test_octop_resource_installations.py",
        "backend/tests/test_octop_skill_packages.py",
        "backend/tests/test_skill_import_recovery.py",
        "backend/packages/octop-capabilities/src/prismos_octop/catalog.py",
        "backend/packages/octop-capabilities/src/prismos_octop/presentation.py",
        "backend/packages/octop-capabilities/src/prismos_octop/resources.py",
        "backend/packages/octop-capabilities/src/prismos_octop/source_policy.py",
    ]
    contract_hashes = {
        path: hashlib.sha256((ROOT / path).read_bytes()).hexdigest()
        for path in contract_paths
    }
    evidence = {
        "scope": (
            "curated source upgrade/rollback; catalog, questionnaire, avatars, presentation persistence, "
            "complete resource declarations, scoped installation facts, derived packages/native installation, "
            "imported pure modules and Agent host contracts"
        ),
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
            "resources.py",
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
                args.previous_receipt,
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
                    "tests/test_octop_resources.py",
                    "tests/test_octop_resource_installations.py",
                    "tests/test_octop_skill_packages.py",
                    "tests/test_skill_import_recovery.py",
                    "tests/test_skill_resource_identity.py",
                    "tests/test_skill_mutation_boundaries.py",
                    "tests/test_skill_enablement_boundaries.py",
                    "tests/test_skill_manual_creation.py",
                    "tests/test_skill_resource_deletion.py",
                    "tests/test_skill_deletion_process.py",
                    "tests/test_skill_member_tools.py",
                    "tests/test_skill_reference_transactions.py",
                    "tests/test_agent_skill_references.py",
                    "tests/test_diagnosis_authorization.py",
                    "tests/test_runtime_adapters.py",
                    "tests/test_incident_diagnosis.py",
                    "tests/test_governed_ticket.py",
                    "tests/test_langgraph_proxy.py",
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
