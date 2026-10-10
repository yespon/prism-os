#!/usr/bin/env python3
"""Reproducible curated Octop import, integrity verification and candidate diff."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import re
import sys
import tarfile
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = Path("backend/packages/octop-capabilities/src/prismos_octop")
VENDOR = Path("vendor/octop")
PINNED_ORIGINS = {
    "eb28011249c02cafd389b2d424294c6c1b9cf422": "270dc73f7fb8f12486d31731b540ca7fdd75180b78d33d38f3b3008faedc572b",
    "e473dd3c4a4741618ffde1a42a3492341a189e8e": "d61c73d5831d83de4aad2e4bf1459c32786db4890381b6344c9a465513c55682",
}
PINNED_MEMBER_RECEIPTS = {
    "eb28011249c02cafd389b2d424294c6c1b9cf422": "39e4d1715a8ad2b09fd4e47a628bd01f20c9661bd93de358236bab004994111f",
    "e473dd3c4a4741618ffde1a42a3492341a189e8e": "302e0008ada5cc665ff4e22d94ecb368de37b1e6954fe02403a111eeab8ff91b",
}

sys.path.insert(0, str(ROOT / PACKAGE.parent))
from prismos_octop.source_policy import MAIN_PREFIXES, POLICY_ID, main_exclusions  # noqa: E402

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
            if member.issym() or member.islnk():
                # Upstream contains links; never follow, import or materialize them.
                continue
            if not member.isfile():
                continue
            if not member.name.startswith(prefix):
                raise ValueError("Archive does not match the requested fixed revision")
            name = member.name[len(prefix) :]
            if PurePosixPath(name).is_absolute() or ".." in PurePosixPath(name).parts:
                raise ValueError("Unsafe archive member")
            if name in files or member.size > 32 * 1024 * 1024:
                raise ValueError("Duplicate or oversized archive member")
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
            if path.startswith(source) and not path.startswith(MAIN_PREFIXES):
                result[path] = target + path[len(source) :]
    for path in result:
        if path not in files:
            raise ValueError(f"Missing import source: {path}")
    return result


def curated_archive(files: dict[str, bytes], revision: str) -> bytes:
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode="w", format=tarfile.PAX_FORMAT) as tar:
        for path, data in sorted(files.items()):
            entry = tarfile.TarInfo(f"Octop-{revision}/" + path)
            entry.size, entry.mode, entry.mtime = len(data), 0o644, 0
            tar.addfile(entry, io.BytesIO(data))
    return gzip.compress(output.getvalue(), mtime=0)


def audit_retained(files: dict[str, bytes]) -> None:
    for path, data in files.items():
        if path.startswith(MAIN_PREFIXES):
            raise ValueError("Restricted resource retained")
        if path.endswith("/SKILL.md") and re.search(
            rb"(?im)^license:\s*[\"']?Proprietary", data[:4096]
        ):
            raise ValueError("Unreviewed proprietary resource: " + path)


def snapshot(archive: Path, revision: str, receipt: Path | None = None):
    files = archive_files(archive, revision)
    hashes = {path: digest(data) for path, data in sorted(files.items())}
    if receipt is None:
        prior_path = ROOT / VENDOR / "manifest.json"
        if prior_path.is_file():
            prior = json.loads(prior_path.read_text())
            if (
                prior.get("schema_version") == 2
                and digest(archive.read_bytes()) == prior["retained_archive_sha256"]
            ):
                raise ValueError("Curated archive requires an explicit origin receipt")
        original_hashes, original_digest = hashes, digest(archive.read_bytes())
    else:
        origin = json.loads(receipt.read_text())
        if origin["schema_version"] != 2 or origin["revision"] != revision:
            raise ValueError("Curated source receipt identity mismatch")
        if digest(archive.read_bytes()) != origin["retained_archive_sha256"]:
            raise ValueError("Curated source receipt archive mismatch")
        original_hashes, original_digest = (
            origin["source_files"],
            origin["archive_sha256"],
        )
        excluded = main_exclusions(original_hashes)
        expected = {
            path: sha for path, sha in original_hashes.items() if path not in excluded
        }
        if (
            origin["exclusion_policy"] != POLICY_ID
            or origin["excluded_source_files"] != excluded
            or origin["retained_source_files"] != expected
            or hashes != expected
        ):
            raise ValueError("Curated source receipt member mismatch")
    if revision in PINNED_ORIGINS and original_digest != PINNED_ORIGINS[revision]:
        raise ValueError("Pinned original archive digest mismatch")
    receipt_digest = digest(
        json.dumps(original_hashes, sort_keys=True, separators=(",", ":")).encode()
    )
    if (
        revision in PINNED_MEMBER_RECEIPTS
        and receipt_digest != PINNED_MEMBER_RECEIPTS[revision]
    ):
        raise ValueError("Pinned original member receipt mismatch")
    exclusions = main_exclusions(original_hashes)
    retained = {path: data for path, data in files.items() if path not in exclusions}
    audit_retained(retained)
    return retained, original_hashes, original_digest, exclusions


def manifest_for(
    files, original_hashes, original_digest, retained_digest, revision, release
):
    exclusions = main_exclusions(original_hashes)
    actual = {path: digest(data) for path, data in sorted(files.items())}
    if actual != {
        path: sha for path, sha in original_hashes.items() if path not in exclusions
    }:
        raise ValueError("Retained source differs from origin receipt")
    return {
        "schema_version": 2,
        "repository": "https://github.com/TencentCloud/Octop",
        "release": release,
        "revision": revision,
        "archive_sha256": original_digest,
        "retained_archive_sha256": retained_digest,
        "archive_kind": "deterministic filtered source view; not original upstream distribution",
        "origin_verification": "original artifact and member hashes verified at import; offline retained bytes checked against receipt",
        "exclusion_policy": POLICY_ID,
        "source_files": original_hashes,
        "retained_source_files": actual,
        "excluded_source_files": exclusions,
        "imports": [
            {
                "source": source,
                "target": (PACKAGE / target).as_posix(),
                "sha256": digest(files[source]),
            }
            for source, target in sorted(selected(files).items())
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


def packaged_provenance(manifest):
    value = {
        key: content
        for key, content in manifest.items()
        if key not in {"source_files", "retained_source_files"}
    }
    value["imports"] = [
        {**entry, "target": str(PurePosixPath(entry["target"]).relative_to(PACKAGE))}
        for entry in manifest["imports"]
    ]
    return value


def sync(
    archive: Path, revision: str, release: str, receipt: Path | None = None
) -> dict:
    # Read and validate everything before changing either source view or imports.
    files, original_hashes, original_digest, exclusions = snapshot(
        archive, revision, receipt
    )
    retained = curated_archive(files, revision)
    manifest = manifest_for(
        files, original_hashes, original_digest, digest(retained), revision, release
    )
    prior_path = ROOT / VENDOR / "manifest.json"
    if prior_path.exists():
        prior = json.loads(prior_path.read_text())
        current = {entry["target"] for entry in manifest["imports"]}
        for entry in prior["imports"]:
            target = ROOT / entry["target"]
            if entry["target"] not in current:
                if (
                    not target.resolve().is_relative_to((ROOT / PACKAGE).resolve())
                    or target.is_symlink()
                ):
                    raise ValueError("Invalid previous import target")
                if target.is_file():
                    target.unlink()
    for entry in manifest["imports"]:
        target = ROOT / entry["target"]
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(files[entry["source"]])
    vendor = ROOT / VENDOR
    vendor.mkdir(parents=True, exist_ok=True)
    (vendor / "upstream.tar.gz").write_bytes(retained)
    (vendor / "LICENSE").write_bytes(files["LICENSE"])
    (vendor / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n"
    )
    (ROOT / PACKAGE / "data/provenance.json").write_text(
        json.dumps(packaged_provenance(manifest), indent=2) + "\n"
    )
    (ROOT / PACKAGE / "LICENSE").write_bytes(files["LICENSE"])
    return {
        "revision": revision,
        "source_files": len(original_hashes),
        "retained_source_files": len(files),
        "excluded_source_files": len(exclusions),
        "imported_files": len(manifest["imports"]),
    }


def verify() -> dict:
    vendor = ROOT / VENDOR
    manifest = json.loads((vendor / "manifest.json").read_text())
    archive = vendor / "upstream.tar.gz"
    files, original_hashes, original_digest, exclusions = snapshot(
        archive, manifest["revision"], vendor / "manifest.json"
    )
    expected = manifest_for(
        files,
        original_hashes,
        original_digest,
        digest(archive.read_bytes()),
        manifest["revision"],
        manifest["release"],
    )
    if manifest != expected:
        raise ValueError("Import manifest mismatch")
    for entry in manifest["imports"]:
        path = ROOT / entry["target"]
        if (
            path.is_symlink()
            or not path.resolve().is_relative_to((ROOT / PACKAGE).resolve())
            or digest(path.read_bytes()) != entry["sha256"]
        ):
            raise ValueError(f"Imported source changed: {entry['target']}")
    expected_data = {
        entry["target"] for entry in manifest["imports"] if "/data/" in entry["target"]
    }
    actual_data = {
        path.relative_to(ROOT).as_posix()
        for directory in ("experts", "subagents")
        for path in (ROOT / PACKAGE / "data" / directory).rglob("*")
        if path.is_file() and path.suffix != ".pyc"
    }
    if actual_data != expected_data:
        raise ValueError("Imported resource inventory mismatch")
    if (vendor / "LICENSE").read_bytes() != files["LICENSE"]:
        raise ValueError("License mismatch")
    provenance = json.loads((ROOT / PACKAGE / "data/provenance.json").read_text())
    if (
        provenance != packaged_provenance(expected)
        or (ROOT / PACKAGE / "LICENSE").read_bytes() != files["LICENSE"]
    ):
        raise ValueError("Packaged provenance mismatch")
    return {
        "verified": True,
        "revision": manifest["revision"],
        "source_files": len(original_hashes),
        "retained_source_files": len(files),
        "excluded_source_files": len(exclusions),
        "imported_files": len(manifest["imports"]),
    }


def compare(
    archive: Path, revision: str, release: str, receipt: Path | None = None
) -> dict:
    baseline = json.loads((ROOT / VENDOR / "manifest.json").read_text())
    candidate, candidate_hashes, _, exclusions = snapshot(archive, revision, receipt)
    old = baseline["source_files"]
    added = sorted(candidate_hashes.keys() - old.keys())
    removed = sorted(old.keys() - candidate_hashes.keys())
    changed = sorted(
        path
        for path in candidate_hashes.keys() & old.keys()
        if candidate_hashes[path] != old[path]
    )
    imported = {entry["source"] for entry in baseline["imports"]} | selected(
        candidate
    ).keys()
    return {
        "baseline": baseline["revision"],
        "candidate": revision,
        "release": release,
        "added": added,
        "removed": removed,
        "changed": changed,
        "imported_changed": sorted(set(added + removed + changed) & imported),
        "excluded_source_files": sorted(exclusions),
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
    parser.add_argument(
        "--receipt",
        type=Path,
        help="Required when importing/comparing an already curated source view",
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.command != "verify" and not all(
        [args.archive, args.revision, args.release]
    ):
        parser.error("archive, revision and release are required")
    if args.command == "verify":
        result = verify()
    elif args.command == "import":
        result = sync(args.archive, args.revision, args.release, args.receipt)
    else:
        result = compare(args.archive, args.revision, args.release, args.receipt)
    text = json.dumps(result, indent=2, ensure_ascii=False) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text)
    else:
        print(text, end="")


if __name__ == "__main__":
    main()
