"""Pending DELETE faults; probes use owned temporary DB/files only."""
from test_skill_import_recovery import archive_bytes, scoped_client as recovery_client
from deerflow.skills import installer
from test_skill_mutation_boundaries import native_rows
from test_skill_resource_identity import source_tree

scoped_client = recovery_client


def test_stale_personal_delete_must_not_remove_current_instance(scoped_client, monkeypatch):
    http, factory, root = source_tree(scoped_client, monkeypatch)
    target = root / "custom/tenant-a/user-a/collision"
    before = (target / "SKILL.md").read_bytes()
    response = http.delete("/api/skills/personal/collision", params={"expected_resource_id": "skill:withdrawn"})
    print({"case": "stale_instance_delete", "status": response.status_code, "directory_retained": target.exists(), "native_rows_after": len(native_rows(factory))})
    assert response.status_code == 409
    assert (target / "SKILL.md").read_bytes() == before
    assert len(native_rows(factory)) == 2


def test_personal_delete_must_not_reclaim_unregistered_directory_by_name(scoped_client, monkeypatch):
    http, factory, root = source_tree(scoped_client, monkeypatch)
    target = root / "custom/tenant-a/user-a/unregistered"
    archive = root.parent / "unknown-published.zip"
    archive.write_bytes(archive_bytes("unregistered"))
    with installer.prepare_skill_installation_from_archive(archive, skills_root=root, target_relative_path="tenant-a/user-a") as prepared:
        published = prepared.publish()
    operation_url = "/api/skills/personal/imports/" + published["operation_id"]
    inspection = http.get(operation_url)
    assert inspection.status_code == 200 and not inspection.json()["registered"]
    before = (target / "SKILL.md").read_bytes()
    response = http.delete("/api/skills/personal/unregistered")
    print({"case": "unregistered_directory_delete", "status": response.status_code, "directory_retained": target.exists(), "native_rows_after": len(native_rows(factory)), "actual_native_publication": True, "registered_before_delete": inspection.json()["registered"]})
    assert response.status_code == 404
    assert (target / "SKILL.md").read_bytes() == before
    assert len(native_rows(factory)) == 2


def test_manual_create_must_not_overwrite_a_native_published_unknown(scoped_client, monkeypatch):
    import hashlib
    http, factory, root = source_tree(scoped_client, monkeypatch)
    archive = root.parent / "manual-target.zip"
    archive.write_bytes(archive_bytes("manual-target"))
    with installer.prepare_skill_installation_from_archive(archive, skills_root=root, target_relative_path="tenant-a/user-a") as prepared:
        published = prepared.publish()
    inspection = http.get("/api/skills/personal/imports/" + published["operation_id"])
    assert inspection.status_code == 200 and not inspection.json()["registered"]
    target = root / "custom/tenant-a/user-a/manual-target/SKILL.md"
    before = target.read_bytes()
    response = http.post("/api/skills/personal", json={"name": "manual-target", "description": "Manual replacement", "instructions": "NEW MANUAL BODY"})
    print({"case": "manual_create_over_published_unknown", "status": response.status_code, "original_bytes_retained": hashlib.sha256(target.read_bytes()).hexdigest()==hashlib.sha256(before).hexdigest(), "native_rows_after": len(native_rows(factory)), "actual_native_publication": True, "registered_before_create": inspection.json()["registered"]})
    assert response.status_code == 409
    assert target.read_bytes() == before
    assert len(native_rows(factory)) == 2
