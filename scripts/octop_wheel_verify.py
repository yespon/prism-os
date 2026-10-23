#!/usr/bin/env python3
"""Verify wheel/sdist against the host's pinned provenance and source policy."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tarfile
import tempfile
import zipfile
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "backend/packages/octop-capabilities/src/prismos_octop"
sys.path.insert(0, str(PACKAGE.parent))
from prismos_octop.source_policy import restricted_package_path  # noqa: E402


def validate_members(names):
    if len(names) != len(set(names)):
        raise ValueError("Duplicate artifact member")
    for name in names:
        if PurePosixPath(name).is_absolute() or ".." in PurePosixPath(name).parts:
            raise ValueError("Invalid artifact member")
        if restricted_package_path(name):
            raise ValueError("Restricted resource in artifact")


def verify_artifact_members(members, prefix):
    expected = json.loads((PACKAGE / "data/provenance.json").read_text())
    provenance = json.loads(members[prefix + "data/provenance.json"])
    if provenance != expected:
        raise ValueError("Artifact provenance differs from pinned host source")
    expected_data = {
        prefix + entry["target"]
        for entry in expected["imports"]
        if entry["target"].startswith(
            ("data/experts/", "data/subagents/", "data/avatars/", "data/personality/")
        )
    }
    actual_data = {
        name
        for name in members
        if name.startswith(
            tuple(
                prefix + "data/" + folder + "/"
                for folder in ("experts", "subagents", "avatars", "personality")
            )
        )
    }
    if actual_data != expected_data:
        raise ValueError("Artifact resource inventory mismatch")
    for entry in provenance["imports"]:
        if (
            hashlib.sha256(members[prefix + entry["target"]]).hexdigest()
            != entry["sha256"]
        ):
            raise ValueError("Artifact source integrity failure: " + entry["target"])
    if members[prefix + "LICENSE"] != (PACKAGE / "LICENSE").read_bytes():
        raise ValueError("Artifact license mismatch")
    return provenance


def verify_sdist(path):
    with tarfile.open(path) as archive:
        if any(entry.issym() or entry.islnk() for entry in archive):
            raise ValueError("Linked sdist member")
        names = [entry.name for entry in archive if entry.isfile()]
        validate_members(names)
        members = {name: archive.extractfile(name).read() for name in names}
        roots = {name.split("/", 1)[0] for name in names}
        if len(roots) != 1:
            raise ValueError("Invalid sdist root")
        verify_artifact_members(members, next(iter(roots)) + "/src/prismos_octop/")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("wheel", type=Path)
    parser.add_argument("--sdist", type=Path)
    args = parser.parse_args()
    if args.sdist:
        verify_sdist(args.sdist)
    with zipfile.ZipFile(args.wheel) as wheel:
        names = [name for name in wheel.namelist() if not name.endswith("/")]
        validate_members(names)
        verify_artifact_members(
            {name: wheel.read(name) for name in names}, "prismos_octop/"
        )
        with tempfile.TemporaryDirectory(prefix="prismos-octop-wheel-") as folder:
            installed = Path(folder)
            wheel.extractall(installed)
            environment = dict(os.environ)
            environment["PYTHONPATH"] = str(installed)
            check = """
import json
from pathlib import Path
import prismos_octop.catalog as catalog
assert Path(catalog.__file__).is_relative_to(Path.cwd())
from prismos_octop.presentation import questionnaire, list_avatars, score_answers
from prismos_octop.resources import resource_declaration
origin = catalog.provenance()
assert len(origin['excluded_source_files']) > 0
assert len(questionnaire("en")) == 28 and len(list_avatars()) == 52
assert score_answers({str(i): "A" for i in range(1, 29)})["code"] == "ESTJ"
resources = [resource_declaration(t["id"]) for t in catalog.list_templates("zh", "expert")]
assert len(resources) == 18
assert sum(d['member_count'] for d in resources) == 297
assert sum(d['verified_source_member_count'] for d in resources) == 352
assert all(not d['execution_ready'] and not d['installation_checked'] for d in resources)
print(json.dumps({
    "revision": origin["revision"], "verified_files": len(origin["imports"]),
    "excluded_source_files": len(origin['excluded_source_files']),
    "zh_templates": len(catalog.list_templates("zh")),
    "en_templates": len(catalog.list_templates("en")),
    "personas": len(catalog.list_personas()), "installed_wheel": True,
    "questionnaire_questions": len(questionnaire("en")), "avatars": len(list_avatars()),
    "declared_resource_members": sum(d["member_count"] for d in resources), "verified_expert_source_members": sum(d["verified_source_member_count"] for d in resources),
}))
"""
            subprocess.run(
                [sys.executable, "-c", check],
                cwd=installed,
                env=environment,
                check=True,
            )


if __name__ == "__main__":
    main()
