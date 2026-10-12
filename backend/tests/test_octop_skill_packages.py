"""Derived archives preserve pinned inputs and pass the original installer."""

from __future__ import annotations

import hashlib
import json

import pytest
from prismos_octop import catalog

from app.integrations.octop.resources import resource_preflight
from app.integrations.octop.skill_packages import ORIGIN_FILE, UPSTREAM_LICENSE_FILE, SkillPackageUnavailable, _upstream_license_bytes, prepare_skill_package, skill_archive
from deerflow.skills.installer import SkillAlreadyExistsError, install_skill_from_archive
from deerflow.skills.validation import _validate_skill_frontmatter

SKILLS = [(t["id"], r["id"]) for t in catalog.list_templates("zh", "expert") for r in resource_preflight(t["id"])["resources"] if r["kind"] == "skill_bundle"]


@pytest.mark.parametrize("template_id,resource_id", SKILLS)
def test_all_retained_skill_packages_install_with_native_strict_validator(tmp_path, template_id, resource_id):
    declaration = resource_preflight(template_id)
    resource = next(r for r in declaration["resources"] if r["id"] == resource_id)
    package = prepare_skill_package(declaration, resource)
    archive = skill_archive(package)
    assert archive == skill_archive(prepare_skill_package(declaration, resource))
    path = tmp_path / "source.zip"
    path.write_bytes(archive)
    result = install_skill_from_archive(path, skills_root=tmp_path / "skills", target_relative_path="tenant-a/user-a")
    from pathlib import Path

    folder = Path(result["install_dir"])
    assert folder.is_relative_to(tmp_path / "skills/custom/tenant-a/user-a")
    assert _validate_skill_frontmatter(folder)[0]
    origin = json.loads((folder / ORIGIN_FILE).read_text())
    assert origin["revision"] == declaration["revision"] and origin["resource_id"] == resource_id
    license_bytes = (folder / UPSTREAM_LICENSE_FILE).read_bytes()
    assert license_bytes == (catalog.ROOT / "LICENSE").read_bytes()
    assert hashlib.sha256(license_bytes).hexdigest() == origin["upstream_license"]["sha256"]
    for file in origin["files"]:
        assert hashlib.sha256((folder / file["path"]).read_bytes()).hexdigest() == file["host_sha256"]
    source_folder = (catalog.ROOT / declaration["template_source"]["target"]).parent
    for member in resource["members"]:
        assert hashlib.sha256((source_folder / member["path"]).read_bytes()).hexdigest() == member["sha256"]
    with pytest.raises(SkillAlreadyExistsError):
        install_skill_from_archive(path, skills_root=tmp_path / "skills", target_relative_path="tenant-a/user-a")


def test_known_format_adapters_keep_body_and_source_fields():
    for template in ["expert:cvm-cluster-doctor", "expert:office-automation", "expert:tencentcloud-api"]:
        declaration = resource_preflight(template)
        resource = next(r for r in declaration["resources"] if r["host_format"]["status"] == "needs_adapter")
        package = prepare_skill_package(declaration, resource)
        assert package["adapted"]
        source = (catalog.ROOT / declaration["template_source"]["target"]).parent / resource["root"] / "SKILL.md"
        from prismos_octop.upstream.frontmatter import parse_frontmatter

        before, body = parse_frontmatter(source.read_text())
        after, adapted_body = parse_frontmatter(package["files"]["SKILL.md"].decode())
        assert body == adapted_body
        if template == "expert:tencentcloud-api":
            assert after["metadata"]["octop_source"]["display_name"] == before["display_name"]
    declaration = resource_preflight("expert:office-automation")
    reference = next(r for r in declaration["resources"] if r["kind"] != "skill_bundle")
    with pytest.raises(SkillPackageUnavailable):
        prepare_skill_package(declaration, reference)


@pytest.mark.parametrize("case", ["missing", "tampered", "symlink"])
def test_pinned_upstream_license_required_without_aliases(tmp_path, monkeypatch, case):
    license_bytes = (catalog.ROOT / "LICENSE").read_bytes()
    root = tmp_path / "source"
    root.mkdir()
    if case == "tampered":
        (root / "LICENSE").write_bytes(license_bytes + b"changed")
    elif case == "symlink":
        outside = tmp_path / "license"
        outside.write_bytes(license_bytes)
        (root / "LICENSE").symlink_to(outside)
    monkeypatch.setattr(catalog, "ROOT", root)
    with pytest.raises(ValueError, match="Upstream license integrity"):
        _upstream_license_bytes()
