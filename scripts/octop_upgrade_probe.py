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
    parser.add_argument(
        "--test-file",
        action="append",
        help="Changed functional block tests; default retains the complete contract suite",
    )
    args = parser.parse_args()
    test_files = args.test_file or [
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
        "tests/test_skill_scoped_commands.py",
        "tests/test_skill_reference_transactions.py",
        "tests/test_agent_skill_references.py",
        "tests/test_agent_copy_share_boundaries.py",
        "tests/test_resource_catalog_access.py",
        "tests/test_auxiliary_resource_runtime.py",
        "tests/test_legacy_default_scope.py",
        "tests/test_diagnosis_authorization.py",
        "tests/test_runtime_adapters.py",
        "tests/test_terminal_access_boundaries.py",
        "tests/test_terminal_multihost.py",
        "tests/test_terminal_security.py",
        "tests/test_terminal_trimming.py",
        "tests/test_incident_diagnosis.py",
        "tests/test_governed_ticket.py",
        "tests/test_langgraph_proxy.py",
        "tests/test_langgraph_proxy_stream.py",
        "tests/test_file_access_boundaries.py",
        "tests/test_file_access_http.py",
    ]
    for name in test_files:
        path = Path(name)
        if (
            path.parent != Path("tests")
            or not path.name.startswith("test_")
            or path.suffix != ".py"
            or not (ROOT / "backend" / path).is_file()
        ):
            parser.error(
                "test-file must be an existing direct backend/tests/test_*.py file"
            )
    manifest = json.loads((ROOT / "vendor/octop/manifest.json").read_text())
    spec = importlib.util.spec_from_file_location(
        "octop_sync", ROOT / "scripts/octop_sync.py"
    )
    sync = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(sync)
    contract_paths = [
        "backend/tests/test_tenant_context_on_config_routers.py",
        "backend/app/gateway/resource_authorization.py",
        "backend/app/integrations/octop/auxiliary_packages.py",
        "backend/app/integrations/octop/resource_installations.py",
        "backend/app/integrations/octop/skill_packages.py",
        "backend/tests/test_resource_catalog_access.py",
        "backend/tests/test_auxiliary_resource_runtime.py",
        "backend/tests/resource_test_identity.py",
        "backend/tests/test_skills_scope_router.py",
        "backend/packages/harness/deerflow/skills/parser.py",
        "frontend/src/core/agents/api.ts",
        "frontend/src/core/agents/types.ts",
        "frontend/src/components/workspace/agents/copy-agent-dialog.tsx",
        "frontend/src/components/workspace/agents/agent-card.tsx",
        "frontend/src/components/workspace/agents/agent-gallery.tsx",
        "backend/Dockerfile",
        "backend/app/services/terminal/access.py",
        "backend/app/services/terminal/session.py",
        "backend/app/agent/terminal_tools.py",
        "backend/app/agent/terminal_graph.py",
        "backend/app/gateway/routers/terminal.py",
        "backend/tests/test_terminal_access_boundaries.py",
        "backend/tests/test_terminal_multihost.py",
        "backend/tests/test_terminal_security.py",
        "backend/tests/test_terminal_trimming.py",
        "backend/tests/test_lead_agent_model_resolution.py",
        "backend/app/alerting/diagnosis_delivery.py",
        "backend/tests/test_diagnosis_delivery.py",
        "backend/tests/test_incident_diagnosis.py",
        "backend/app/alerting/diagnosis_run_control.py",
        "backend/tests/test_diagnosis_run_control.py",
        "backend/tests/test_runtime_source_revocation.py",
        "backend/app/alerting/governed_ticket.py",
        "backend/tests/test_langgraph_proxy_stream.py",
        "backend/app/integrations/file_access.py",
        "backend/app/gateway/file_authorization.py",
        "backend/app/gateway/routers/artifacts.py",
        "backend/app/gateway/routers/threads.py",
        "backend/app/gateway/routers/uploads.py",
        "backend/packages/harness/deerflow/sandbox/file_access.py",
        "backend/packages/harness/deerflow/tools/builtins/view_image_tool.py",
        "backend/packages/harness/deerflow/tools/builtins/present_file_tool.py",
        "backend/tests/test_file_access_boundaries.py",
        "backend/tests/test_file_access_http.py",
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
        "backend/tests/test_skill_scoped_commands.py",
        "backend/app/integrations/skill_command_views.py",
        "backend/packages/harness/deerflow/sandbox/local/scoped_command.py",
        "backend/packages/harness/deerflow/sandbox/local/local_sandbox_provider.py",
        "backend/packages/harness/deerflow/sandbox/sandbox_provider.py",
        "backend/packages/harness/deerflow/community/aio_sandbox/scoped_command.py",
        "backend/packages/harness/deerflow/community/aio_sandbox/aio_sandbox_provider.py",
        "backend/tests/test_skill_reference_transactions.py",
        "backend/tests/test_agent_skill_references.py",
        "backend/tests/test_agent_copy_share_boundaries.py",
        "backend/tests/test_custom_agent.py",
        "backend/tests/test_octop_integration.py",
        "backend/tests/test_legacy_default_scope.py",
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
        "host_changed": None,
        "complete": False,
        "test_files": test_files,
        "test_scope": "selected changed functional block"
        if args.test_file
        else "complete host contract suite",
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
                    *test_files,
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
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(
                json.dumps(evidence, indent=2, ensure_ascii=False) + "\n"
            )
            if result.returncode:
                raise RuntimeError(result.stdout + result.stderr)
    if contract_hashes != {
        path: hashlib.sha256((ROOT / path).read_bytes()).hexdigest()
        for path in contract_paths
    }:
        evidence["host_changed"] = True
        args.output.write_text(
            json.dumps(evidence, indent=2, ensure_ascii=False) + "\n"
        )
        raise ValueError("Host contract changed during upgrade probe")
    evidence["host_changed"] = False
    evidence["complete"] = True
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
