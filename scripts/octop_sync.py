#!/usr/bin/env python3
"""Reproducible Octop import, integrity verification and candidate diff (no network)."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import tarfile
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = Path("backend/packages/octop-capabilities/src/prismos_octop")
VENDOR = Path("vendor/octop")
MODULES = {
    "src/octop/infra/agents/persona/mbti_profiles.py": "upstream/mbti_profiles.py",
    "src/octop/infra/utils/frontmatter.py": "upstream/frontmatter.py",
    "src/octop/infra/knowledge/chunk.py": "upstream/chunk.py",
    "src/octop/infra/knowledge/citations.py": "upstream/citations.py",
}
LIBRARIES = {
    "src/octop/infra/agents/experts/library/": "data/experts/",
    "src/octop/infra/agents/subagents/library/": "data/subagents/",
}


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def archive_files(archive: Path, revision: str) -> dict[str, bytes]:
    prefix = f"Octop-{revision}/"
    files = {}
    with tarfile.open(archive) as tar:
        for member in tar:
            if not member.isfile():
                continue
            if not member.name.startswith(prefix):
                raise ValueError("Archive does not match the requested fixed revision")
            name = member.name[len(prefix) :]
            if PurePosixPath(name).is_absolute() or ".." in PurePosixPath(name).parts:
                raise ValueError("Unsafe archive member")
            stream = tar.extractfile(member)
            if stream is None:
                raise ValueError("Unreadable archive member")
            files[name] = stream.read()
    if "LICENSE" not in files or "pyproject.toml" not in files:
        raise ValueError("Incomplete Octop source archive")
    return files


def selected(files: dict[str, bytes]) -> dict[str, str]:
    result = dict(MODULES)
    for source, target in LIBRARIES.items():
        for path in files:
            if path.startswith(source):
                result[path] = target + path[len(source) :]
    for path in result:
        if path not in files:
            raise ValueError(f"Missing import source: {path}")
    return result


def manifest_for(files, archive, revision, release):
    mappings = selected(files)
    return {
        "schema_version": 1,
        "repository": "https://github.com/TencentCloud/Octop",
        "release": release,
        "revision": revision,
        "archive_sha256": digest(archive.read_bytes()),
        "source_files": {path: digest(body) for path, body in sorted(files.items())},
        "imports": [
            {
                "source": source,
                "target": (PACKAGE / target).as_posix(),
                "sha256": digest(files[source]),
            }
            for source, target in sorted(mappings.items())
        ],
        "runtime_modules": list(MODULES),
        "external_packages": [
            "octop-harness",
            "octop-memory",
            "octop-gateway",
            "octop-browser",
        ],
        "external_packages_status": "not imported; existing PrismOS runtime retained",
    }


def sync(archive: Path, revision: str, release: str) -> dict:
    files = archive_files(archive, revision)
    manifest = manifest_for(files, archive, revision, release)
    # Remove only previously imported paths; never remove host adapters or user data.
    prior_path = ROOT / VENDOR / "manifest.json"
    if prior_path.exists():
        prior = json.loads(prior_path.read_text())
        current = {entry["target"] for entry in manifest["imports"]}
        for entry in prior["imports"]:
            target = ROOT / entry["target"]
            if entry["target"] not in current:
                if not target.resolve().is_relative_to((ROOT / PACKAGE).resolve()):
                    raise ValueError("Invalid previous import target")
                if target.is_file():
                    target.unlink()
    for entry in manifest["imports"]:
        target = ROOT / entry["target"]
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(files[entry["source"]])
    vendor = ROOT / VENDOR
    vendor.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(archive, vendor / "upstream.tar.gz")
    (vendor / "LICENSE").write_bytes(files["LICENSE"])
    (vendor / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n"
    )
    package_provenance = dict(manifest)
    package_provenance.pop("source_files")
    for entry in package_provenance["imports"]:
        entry["target"] = str(PurePosixPath(entry["target"]).relative_to(PACKAGE))
    (ROOT / PACKAGE / "data/provenance.json").write_text(
        json.dumps(package_provenance, indent=2) + "\n"
    )
    (ROOT / PACKAGE / "LICENSE").write_bytes(files["LICENSE"])
    return {
        "revision": revision,
        "source_files": len(files),
        "imported_files": len(manifest["imports"]),
    }


def verify() -> dict:
    vendor = ROOT / VENDOR
    manifest = json.loads((vendor / "manifest.json").read_text())
    archive = vendor / "upstream.tar.gz"
    if digest(archive.read_bytes()) != manifest["archive_sha256"]:
        raise ValueError("Upstream archive hash mismatch")
    files = archive_files(archive, manifest["revision"])
    actual = {path: digest(body) for path, body in files.items()}
    if actual != manifest["source_files"]:
        raise ValueError("Upstream source inventory mismatch")
    expected = manifest_for(files, archive, manifest["revision"], manifest["release"])
    if manifest != expected:
        raise ValueError("Import manifest mismatch")
    for entry in manifest["imports"]:
        path = ROOT / entry["target"]
        if digest(path.read_bytes()) != entry["sha256"]:
            raise ValueError(f"Imported source changed: {entry['target']}")
    if (vendor / "LICENSE").read_bytes() != files["LICENSE"]:
        raise ValueError("License mismatch")
    provenance = json.loads((ROOT / PACKAGE / "data/provenance.json").read_text())
    expected.pop("source_files")
    for entry in expected["imports"]:
        entry["target"] = str(PurePosixPath(entry["target"]).relative_to(PACKAGE))
    if (
        provenance != expected
        or (ROOT / PACKAGE / "LICENSE").read_bytes() != files["LICENSE"]
    ):
        raise ValueError("Packaged provenance mismatch")
    return {
        "verified": True,
        "revision": manifest["revision"],
        "source_files": len(files),
        "imported_files": len(manifest["imports"]),
    }


def compare(archive: Path, revision: str, release: str) -> dict:
    baseline = json.loads((ROOT / VENDOR / "manifest.json").read_text())
    candidate = archive_files(archive, revision)
    candidate_hashes = {path: digest(body) for path, body in candidate.items()}
    old = baseline["source_files"]
    added = sorted(candidate_hashes.keys() - old.keys())
    removed = sorted(old.keys() - candidate_hashes.keys())
    changed = sorted(
        path
        for path in candidate_hashes.keys() & old.keys()
        if candidate_hashes[path] != old[path]
    )
    candidate_imports = selected(candidate)
    imported = {
        entry["source"] for entry in baseline["imports"]
    } | candidate_imports.keys()
    return {
        "baseline": baseline["revision"],
        "candidate": revision,
        "release": release,
        "added": added,
        "removed": removed,
        "changed": changed,
        "imported_changed": sorted(set(added + removed + changed) & imported),
        "dependency_changed": "pyproject.toml" in added + removed + changed
        or "uv.lock" in added + removed + changed,
        "runtime_module_changes": sorted(
            set(added + removed + changed) & MODULES.keys()
        ),
        "baseline_modified": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["import", "verify", "compare"])
    parser.add_argument("--archive", type=Path)
    parser.add_argument("--revision")
    parser.add_argument("--release")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.command != "verify" and not all(
        [args.archive, args.revision, args.release]
    ):
        parser.error("archive, revision and release are required")
    if args.command == "verify":
        result = verify()
    elif args.command == "import":
        result = sync(args.archive, args.revision, args.release)
    else:
        result = compare(args.archive, args.revision, args.release)
    text = json.dumps(result, indent=2, ensure_ascii=False) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text)
    else:
        print(text, end="")


if __name__ == "__main__":
    main()
