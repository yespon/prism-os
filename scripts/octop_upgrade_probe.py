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
        "tests/test_governed_native_reads.py",
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
        "tests/test_office_pdf_fonts.py",
        "tests/test_office_docx_images.py",
        "tests/test_office_pptx_images.py",
        "tests/test_n04_ticket_receiver.py",
        "tests/test_n04_deployment_snapshot.py",
        "tests/test_ticket_policy_changes.py",
        "tests/test_runtime_worker_bootstrap.py",
        "tests/test_langgraph_proxy_nginx.py",
        "tests/test_nginx_runtime_resolution.py",
        "tests/test_office_chart_editing.py",
        "tests/test_office_charts.py",
        "tests/test_office_xlsx.py",
        "tests/test_office_formats.py",
        "tests/test_office_docx.py",
        "tests/test_terminal_socket_sessions.py",
        "tests/test_auth_session_delivery.py",
        "tests/test_auth_middleware_status.py",
        "tests/test_runtime_actor_status.py",
        "tests/test_credential_asset_access.py",
        "tests/test_remote_scoped_commands.py",
        "tests/test_provisioner_kubeconfig.py",
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
        "backend/app/alerting/governed_native_reads.py",
        "backend/tests/test_governed_native_reads.py",
        "docs/superpowers/evidence/2026-10-16-octop-governed-readers/live_binary_task.py",
        "docs/superpowers/evidence/2026-10-16-octop-governed-readers/live_binary_faults.py",
        'backend/tests/test_ticket_policy_changes.py',
        'backend/packages/harness/deerflow/database/session.py',
        'backend/tests/test_runtime_worker_bootstrap.py',
        'backend/tests/test_langgraph_proxy_nginx.py',
        'backend/tests/test_nginx_runtime_resolution.py',
        'docker/nginx/nginx.conf',
        'docker/nginx/nginx.local.conf',
        'docker/docker-compose.yaml',

        "backend/packages/harness/deerflow/tools/builtins/office_pptx_images.py",
        "backend/tests/test_office_pptx_images.py",
        "scripts/octop_wsl_test_env.py",
        "scripts/octop_wsl_test_snapshot.py",
        "scripts/octop_office_task_probe.py",
        "scripts/octop_office_report_probe.py",
        "scripts/octop_office_unicode_probe.py",
        "docs/superpowers/evidence/2026-10-16-octop-office-chinese-task/native_preview.py",
        "backend/app/integrations/octop/runtime_prompts.py",
        "backend/tests/test_n04_deployment_snapshot.py",
        "scripts/octop_wsl_test_probe.py",
        "docker/n04-test/ticket_receiver.py",
        "backend/tests/test_n04_ticket_receiver.py",
        "backend/packages/harness/deerflow/tools/builtins/office_docx_images.py",
        "backend/tests/test_office_docx_images.py",
        "backend/tests/test_office_chart_editing.py",
        "backend/packages/harness/deerflow/tools/builtins/office_fonts.py",
        "backend/tests/test_office_pdf_fonts.py",
        "backend/tests/fixtures/pdf-fonts/NotoMono-Regular.ttf",
        "backend/tests/fixtures/pdf-fonts/copyright.txt",
        "backend/tests/fixtures/pdf-fonts/provenance.json",
        "backend/tests/test_office_charts.py",
        "scripts/octop_worker_compat.py",
        "scripts/octop_worker_probe.py",
        "docker/octop-worker-compat/Dockerfile",
        "docker/octop-worker-compat/worker_rpc.py",
        "docker/octop-worker-compat/requirements.lock",
        "backend/tests/test_octop_worker_compat.py",
        'backend/packages/harness/deerflow/tools/builtins/office_common.py',
        'backend/packages/harness/deerflow/tools/builtins/office_xlsx.py',
        'backend/packages/harness/deerflow/tools/builtins/office_pptx.py',
        'backend/packages/harness/deerflow/tools/builtins/office_pdf.py',
        'backend/tests/test_office_xlsx.py',
        'backend/tests/test_office_formats.py',
        'backend/packages/harness/pyproject.toml',
        'backend/uv.lock',
        'backend/packages/harness/deerflow/tools/builtins/office_docx.py',
        'backend/tests/test_office_docx.py',
        'backend/packages/harness/deerflow/sandbox/file_access.py',
        'backend/packages/harness/deerflow/tools/tools.py',
        'backend/app/integrations/file_access.py',
        'backend/app/services/terminal/socket_access.py',
        'backend/tests/test_terminal_socket_sessions.py',
        'backend/app/gateway/auth.py',
        'backend/app/gateway/routers/auth.py',
        'backend/app/gateway/session_authorization.py',
        'backend/tests/test_auth_session_delivery.py',
        'backend/tests/test_auth_middleware_status.py',
        'backend/app/integrations/actor_authorization.py',
        'backend/tests/native_auth_test_identity.py',
        'backend/tests/test_runtime_actor_status.py',
        'backend/tests/conftest.py',
        "frontend/src/core/terminal-agent/assets-api.ts",
        "frontend/src/core/terminal-agent/assets-api.test.ts",
        "frontend/src/components/workspace/terminal/asset-sidebar.tsx",
        "frontend/src/components/workspace/terminal/add-host-dialog.tsx",
        "frontend/src/components/workspace/terminal/add-credential-dialog.tsx",
        "frontend/src/components/workspace/terminal/asset-dialogs.test.tsx",
        "frontend/src/components/workspace/terminal/persistent-terminal.tsx",
        "backend/app/gateway/routers/assets.py",
        "backend/app/services/terminal/credential_access.py",
        "backend/scripts/rotate_encrypted_secrets.py",
        "backend/tests/test_credential_asset_access.py",
        "docker/provisioner/requirements.lock",
        "scripts/octop_remote_smoke.py",
        "backend/packages/harness/deerflow/community/aio_sandbox/remote_backend.py",
        "backend/packages/harness/deerflow/community/aio_sandbox/backend.py",
        "docker/provisioner/app.py",
        "docker/provisioner/scoped_commands.py",
        "docker/provisioner/Dockerfile",
        "backend/tests/test_remote_scoped_commands.py",
        "backend/tests/test_provisioner_kubeconfig.py",
        "backend/packages/harness/deerflow/community/aio_sandbox/remote_command.py",
        "backend/packages/harness/deerflow/config/sandbox_config.py",
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
