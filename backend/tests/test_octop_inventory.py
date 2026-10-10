"""Inventory completeness, non-execution, source rejection and explicit license exclusions."""

import io
import json
import sys
import zipfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import octop_external  # noqa: E402
import octop_inventory  # noqa: E402


@pytest.fixture(scope="module")
def inventory():
    return octop_inventory.build()


def test_named_catalogs_and_complete_scope_are_preserved(inventory):
    summary = inventory["summary.json"]
    assert summary["main_source_files"] == 3771 and summary["imported_files"] == 849
    assert summary["retained_main_source_files"] == 3585
    assert summary["excluded_main_source_files"] == 186 and summary["excluded_external_source_files"] == 51
    assert summary["current_capabilities"] == 42 and summary["future_capabilities"] == 12
    items = inventory["capability-items.json"]
    assert len(items["experts"]) == 18 and len(items["subagents"]) == 489
    assert len(items["connectors"]) == 26 and len(items["plugins"]) == 31
    assert len(items["endpoints"]) == 494
    assert {entry["id"] for entry in inventory["capability-ledger.json"]} == {f"O{number:02}" for number in range(1, 43)}
    assert {entry["id"] for entry in inventory["future-ledger.json"]} == {f"F{number:02}" for number in range(1, 13)}
    assert all(not entry["full_parity"] for entry in inventory["capability-ledger.json"])
    for group in items.values():
        for entry in group:
            assert entry["owner_role"] and entry["permissions"] and entry["dependencies"] and entry["remaining"]
            assert not entry["full_parity"]
    assert "octop_harness" not in sys.modules


def test_restricted_skill_is_absent_from_redistributable_artifacts_and_target_is_retained(inventory):
    manifest = json.loads((octop_external.DESTINATION / "manifest.json").read_text())
    harness = next(package for package in manifest["packages"] if package["name"] == "octop-harness")
    source, wheel = harness["artifacts"]
    assert len(source["excluded_members"]) == 51 and wheel["path"] is None
    members = octop_external.artifact_members(octop_external.ROOT / source["path"])
    assert not any(prefix in path for path in members for prefix in octop_external.HARNESS_PREFIXES)
    assert not (octop_external.DESTINATION / "archives/octop_harness-1.0.1.tar.gz").exists()
    assert not (octop_external.DESTINATION / "archives/octop_harness-1.0.1-py3-none-any.whl").exists()
    assert len(inventory["excluded-resources.json"]) == 237
    assert all(not entry["stages"]["archived"] and entry["status"] == "remaining" for entry in inventory["excluded-resources.json"])
    replacement = next(entry for entry in inventory["capability-items.json"]["skills"] if entry["id"].endswith("powerpoint-independent-replacement"))
    assert replacement["status"] == "remaining" and not replacement["stages"]["archived"]
    assert "O07" in replacement["capabilities"] and replacement["remaining"]


def test_dependency_conflict_is_recorded_without_changing_host_lock_or_runtime(inventory):
    dependencies = inventory["dependencies.json"]
    harness = next(package for package in dependencies["packages"] if package["name"] == "octop-harness")
    requirement = next(entry for entry in harness["core"] if entry["name"] == "langchain-mcp-adapters")
    assert requirement["host_check"] == "conflict" and requirement["host_locked"] == "0.2.1"
    assert not dependencies["host_lock_modified"] and not dependencies["full_upstream_lock_installed"]
    assert not inventory["summary.json"]["external_runtime_integration"]
    assert not inventory["summary.json"]["runtime_permission_grants"]


def test_dynamic_connector_identity_is_rejected_without_running_source(tmp_path):
    marker = tmp_path / "executed"
    code = f'ConnectorCatalogEntry(kind=__import__("pathlib").Path({str(marker)!r}).write_text("unsafe"))'
    with pytest.raises(ValueError, match="Dynamic connector"):
        octop_inventory.connector_entries(code.encode())
    assert not marker.exists()


@pytest.mark.parametrize("name", ["../escape.py", "/escape.py"])
def test_external_archive_path_traversal_is_rejected(name):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(name, "untrusted")
    with pytest.raises(ValueError, match="Unsafe external"):
        octop_external.read_members(buffer.getvalue(), wheel=True)


def test_stale_inventory_cannot_pass_verification(inventory, tmp_path, monkeypatch):
    for name, value in inventory.items():
        (tmp_path / name).write_text(json.dumps(value))
    value = json.loads((tmp_path / "capability-items.json").read_text())
    value["connectors"].pop()
    (tmp_path / "capability-items.json").write_text(json.dumps(value))
    monkeypatch.setattr(octop_inventory, "OUTPUT", tmp_path)
    with pytest.raises(ValueError, match="Inventory stale"):
        octop_inventory.verify()


def test_mutated_external_origin_cannot_be_blessed(tmp_path, monkeypatch):
    manifest = json.loads((octop_external.DESTINATION / "manifest.json").read_text())
    manifest["packages"][0]["artifacts"][0]["sha256"] = "0" * 64
    (tmp_path / "manifest.json").write_text(json.dumps(manifest))
    monkeypatch.setattr(octop_external, "DESTINATION", tmp_path)
    with pytest.raises(ValueError, match="External origin lock mismatch"):
        octop_external.verify()


def test_rewriting_external_member_receipt_cannot_forge_original_distribution(tmp_path, monkeypatch):
    manifest = json.loads((octop_external.DESTINATION / "manifest.json").read_text())
    source = manifest["packages"][0]["artifacts"][0]
    name = next(iter(source["members"]))
    source["members"][name] = "0" * 64
    (tmp_path / "manifest.json").write_text(json.dumps(manifest))
    monkeypatch.setattr(octop_external, "DESTINATION", tmp_path)
    with pytest.raises(ValueError, match="external source member receipt"):
        octop_external.verify()
