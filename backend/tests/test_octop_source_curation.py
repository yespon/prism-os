"""Exercise origin preservation and reject resource/provenance reintroduction."""

import io
import json
import shutil
import sys
import tarfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import octop_sync as sync  # noqa: E402
import octop_wheel_verify as artifacts  # noqa: E402
from prismos_octop.catalog import get_template  # noqa: E402
from prismos_octop.source_policy import MAIN_PREFIXES  # noqa: E402


@pytest.fixture
def stage(tmp_path, monkeypatch):
    source_root = sync.ROOT
    vendor = tmp_path / sync.VENDOR
    vendor.mkdir(parents=True)
    for name in ("manifest.json", "upstream.tar.gz", "LICENSE"):
        shutil.copyfile(source_root / sync.VENDOR / name, vendor / name)
    shutil.copytree(source_root / sync.PACKAGE, tmp_path / sync.PACKAGE, ignore=shutil.ignore_patterns("__pycache__"))
    monkeypatch.setattr(sync, "ROOT", tmp_path)
    return tmp_path, json.loads((vendor / "manifest.json").read_text())


def write_receipt(root, value):
    (root / sync.VENDOR / "manifest.json").write_text(json.dumps(value))


def test_curated_reimport_is_byte_stable_and_preserves_original_receipt(stage):
    root, before = stage
    archive = root / sync.VENDOR / "upstream.tar.gz"
    result = sync.sync(archive, before["revision"], before["release"], root / sync.VENDOR / "manifest.json")
    after = json.loads((root / sync.VENDOR / "manifest.json").read_text())
    assert before == after
    assert after["archive_sha256"] != after["retained_archive_sha256"]
    assert len(after["source_files"]) == 3771
    assert result["imported_files"] == 849 and result["excluded_source_files"] == 186
    assert sync.verify()["verified"]


def test_curated_archive_cannot_be_imported_as_original(stage):
    root, manifest = stage
    with pytest.raises(ValueError, match="explicit origin receipt"):
        sync.sync(root / sync.VENDOR / "upstream.tar.gz", manifest["revision"], manifest["release"])


@pytest.mark.parametrize("mutation", ["exclusion", "origin", "retained"])
def test_receipt_mutation_cannot_bless_source(stage, mutation):
    root, manifest = stage
    if mutation == "exclusion":
        manifest["excluded_source_files"].pop(next(path for path in manifest["excluded_source_files"] if not path.endswith("LICENSE.txt")))
    elif mutation == "origin":
        manifest["archive_sha256"] = "0" * 64
    else:
        manifest["retained_archive_sha256"] = "0" * 64
    write_receipt(root, manifest)
    with pytest.raises(ValueError, match="receipt|original archive"):
        sync.verify()


def test_restricted_bytes_cannot_reenter_by_changing_retained_hash(stage):
    root, manifest = stage
    archive = root / sync.VENDOR / "upstream.tar.gz"
    files = sync.archive_files(archive, manifest["revision"])
    files[MAIN_PREFIXES[0] + "SKILL.md"] = b"synthetic resource marker"
    archive.write_bytes(sync.curated_archive(files, manifest["revision"]))
    manifest["retained_archive_sha256"] = sync.digest(archive.read_bytes())
    write_receipt(root, manifest)
    with pytest.raises(ValueError, match="receipt member mismatch"):
        sync.verify()


def test_restricted_resource_cannot_reenter_installed_data(stage):
    root, _ = stage
    path = root / sync.PACKAGE / "data/experts/office-automation/skills/docx/SKILL.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("synthetic resource marker")
    with pytest.raises(ValueError, match="resource inventory mismatch"):
        sync.verify()


def test_excluded_resources_remain_visible_as_functional_gaps():
    expert = get_template("expert:office-automation", "zh")
    assert expert["excluded_resources"] == ["skills/docx", "skills/pdf", "skills/pptx", "skills/xlsx"]
    assert expert["system_prompt"] and expert["excluded_resources_status"] == "independent implementation pending"
    assert not any(path.startswith(tuple(expert["excluded_resources"])) for path in expert["bundled_resources"])


@pytest.mark.parametrize(
    "path",
    [
        "prismos_octop/data/experts/office-automation/skills/docx/SKILL.md",
        "package/src/prismos_octop/data/experts/office-automation/skills/pdf/LICENSE.txt",
        "../escaped",
    ],
)
def test_wheel_and_sdist_member_gate_rejects_reintroduced_resource(path):
    with pytest.raises(ValueError, match="Restricted resource|Invalid artifact"):
        artifacts.validate_members([path])


def test_artifact_cannot_forge_its_own_provenance():
    with pytest.raises(ValueError, match="pinned host source"):
        artifacts.verify_artifact_members({"prismos_octop/data/provenance.json": b'{"imports": []}'}, "prismos_octop/")


def test_reader_never_follows_upstream_links(tmp_path):
    archive = tmp_path / "source.tar.gz"
    with tarfile.open(archive, "w:gz") as output:
        for path in ("LICENSE", "pyproject.toml"):
            entry = tarfile.TarInfo("Octop-test/" + path)
            entry.size = 1
            output.addfile(entry, io.BytesIO(b"x"))
        link = tarfile.TarInfo("Octop-test/linked-secret")
        link.type = tarfile.SYMTYPE
        link.linkname = "/unreadable/external/resource"
        output.addfile(link)
    assert sync.archive_files(archive, "test") == {"LICENSE": b"x", "pyproject.toml": b"x"}


def test_rewriting_member_receipt_and_retained_bytes_cannot_forge_origin(stage):
    root, manifest = stage
    archive = root / sync.VENDOR / "upstream.tar.gz"
    files = sync.archive_files(archive, manifest["revision"])
    path = "src/octop/infra/agents/experts/library/general-assistant/SOUL.md"
    files[path] = b"synthetic replacement prompt"
    manifest["source_files"][path] = sync.digest(files[path])
    manifest["retained_source_files"][path] = sync.digest(files[path])
    archive.write_bytes(sync.curated_archive(files, manifest["revision"]))
    manifest["retained_archive_sha256"] = sync.digest(archive.read_bytes())
    write_receipt(root, manifest)
    with pytest.raises(ValueError, match="original member receipt"):
        sync.verify()
