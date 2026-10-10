#!/usr/bin/env python3
"""Archive/verify four exact Octop distributions without installing or importing them."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import tarfile
import tomllib
import urllib.request
import zipfile
from email.parser import BytesParser
from pathlib import Path, PurePosixPath
from urllib.parse import urlsplit

from octop_sync import archive_files
from octop_sync import verify as verify_main

# isort: split
from prismos_octop.source_policy import HARNESS_PREFIXES, LICENSE_SHA256, POLICY_ID

ROOT = Path(__file__).resolve().parents[1]
DESTINATION = ROOT / "vendor/octop/external"
NAMES = {"octop-harness", "octop-memory", "octop-gateway", "octop-browser"}

PINNED_SOURCE_MEMBER_RECEIPTS = {
    (
        "octop-browser",
        "1.0.0",
    ): "df6b53a93449fe6e42b218377da56b9df831cc7c469c6605de9d222e1aa1b22f",
    (
        "octop-gateway",
        "1.0.0",
    ): "11aad1521b3d73bd637132cb3674de4b004356c1b98921b9df8daafdb8c0e12c",
    (
        "octop-harness",
        "1.0.1",
    ): "4145f9081ed0cafbd4759b13662369aa8a59a42550159a2a437007f9c22132b1",
    (
        "octop-memory",
        "1.0.0",
    ): "6a23b78dd7c46d414ac9be70a50d1513d68d36661d2b08c4cfe8a413f51e6668",
}


def digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def locked_packages() -> list[dict]:
    verify_main()
    manifest = json.loads((ROOT / "vendor/octop/manifest.json").read_text())
    files = archive_files(ROOT / "vendor/octop/upstream.tar.gz", manifest["revision"])
    result = [
        entry
        for entry in tomllib.loads(files["uv.lock"].decode())["package"]
        if entry["name"] in NAMES
    ]
    if {entry["name"] for entry in result} != NAMES or len(result) != 4:
        raise ValueError("External lock coverage mismatch")
    return sorted(result, key=lambda entry: entry["name"])


# This exact bundled subtree has independent terms prohibiting copying/distribution.
# Capability stays in the ledger for an independently implemented replacement.
RESTRICTED = HARNESS_PREFIXES[0]
RESTRICTED_LICENSE_SHA = (
    "79f6d8f5b427252fa3b1c11ecdbdb6bf610b944f7530b4de78f770f38741cfaa"
)


def read_members(data: bytes, *, wheel: bool) -> dict[str, bytes]:
    result = {}
    if wheel:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            for entry in archive.infolist():
                if not entry.is_dir():
                    if entry.filename in result:
                        raise ValueError("Duplicate wheel member")
                    result[entry.filename] = archive.read(entry)
    else:
        with tarfile.open(fileobj=io.BytesIO(data)) as archive:
            for entry in archive:
                if entry.issym() or entry.islnk():
                    raise ValueError("Linked source member")
                if entry.isfile():
                    if entry.name in result or entry.size > 16 * 1024 * 1024:
                        raise ValueError("Invalid source member")
                    result[entry.name] = archive.extractfile(entry).read()
    for name in result:
        if PurePosixPath(name).is_absolute() or ".." in PurePosixPath(name).parts:
            raise ValueError("Unsafe external artifact member")
    return result


def artifact_members(path: Path) -> dict[str, bytes]:
    return read_members(path.read_bytes(), wheel=path.suffix == ".whl")


def metadata_for(package: dict, kind: str, members: dict[str, bytes]) -> dict:
    paths = (
        [name for name in members if name.endswith(".dist-info/METADATA")]
        if kind == "wheel"
        else [
            name
            for name in members
            if name.count("/") == 1 and name.endswith("/PKG-INFO")
        ]
    )
    if len(paths) != 1:
        raise ValueError("Distribution metadata missing or ambiguous")
    metadata = BytesParser().parsebytes(members[paths[0]])
    if (
        metadata["Name"].lower().replace("_", "-") != package["name"]
        or metadata["Version"] != package["version"]
    ):
        raise ValueError("Distribution metadata identity mismatch")
    return {
        "metadata_path": paths[0],
        "metadata": {
            "name": metadata["Name"],
            "version": metadata["Version"],
            "requires_python": metadata["Requires-Python"],
            "license": metadata["License"],
            "license_expression": metadata["License-Expression"],
            "classifiers": metadata.get_all("Classifier", []),
            "project_urls": metadata.get_all("Project-URL", []),
            "requirements": metadata.get_all("Requires-Dist", []),
            "extras": metadata.get_all("Provides-Extra", []),
        },
    }


def harness_exclusions(package: dict, source_hashes: dict[str, str]) -> list[str]:
    root = f"octop_harness-{package['version']}/"
    prefixes = tuple(root + prefix for prefix in HARNESS_PREFIXES)
    result = sorted(name for name in source_hashes if name.startswith(prefixes))
    if source_hashes.get(prefixes[0] + "LICENSE.txt") != LICENSE_SHA256:
        raise ValueError("Restricted resource license changed; review before archiving")
    if not any(name.startswith(prefixes[1]) for name in result):
        raise ValueError("Restricted Chinese resource missing; review source change")
    return result


def source_exclusions(package: dict, members: dict[str, bytes]) -> list[str]:
    if package["name"] != "octop-harness":
        return []
    return harness_exclusions(
        package, {name: digest(data) for name, data in members.items()}
    )


def filtered_source(members: dict[str, bytes], exclusions: list[str]) -> bytes:
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode="w", format=tarfile.PAX_FORMAT) as archive:
        for name, data in sorted(members.items()):
            if name in exclusions:
                continue
            entry = tarfile.TarInfo(name)
            entry.size, entry.mode, entry.mtime = len(data), 0o644, 0
            archive.addfile(entry, io.BytesIO(data))
    return gzip.compress(output.getvalue(), mtime=0)


def fetch() -> dict:
    baseline = json.loads((ROOT / "vendor/octop/manifest.json").read_text())
    packages = []
    for package in locked_packages():
        artifacts = []
        for kind, origin in [
            ("sdist", package["sdist"]),
            ("wheel", package["wheels"][0]),
        ]:
            url = urlsplit(origin["url"])
            if url.scheme != "https" or url.netloc != "files.pythonhosted.org":
                raise ValueError("Unexpected distribution origin")
            with urllib.request.urlopen(origin["url"], timeout=60) as response:
                data = response.read(origin["size"] + 1)
            if (
                digest(data) != origin["hash"].removeprefix("sha256:")
                or len(data) != origin["size"]
            ):
                raise ValueError(
                    "Downloaded artifact failed locked hash/size validation"
                )
            members = read_members(data, wheel=kind == "wheel")
            license_names = sorted(
                name
                for name in members
                if PurePosixPath(name)
                .name.upper()
                .startswith(("LICENSE", "COPYING", "NOTICE"))
            )
            if not license_names:
                raise ValueError("External license missing")
            artifact = {
                "kind": kind,
                "url": origin["url"],
                "sha256": digest(data),
                "size": len(data),
                "members": {
                    name: digest(content) for name, content in sorted(members.items())
                },
                "license_files": [
                    {"member": name, "sha256": digest(members[name])}
                    for name in license_names
                ],
                **metadata_for(package, kind, members),
            }
            artifact["excluded_members"] = (
                source_exclusions(package, members) if kind == "sdist" else []
            )
            if package["name"] == "octop-harness" and kind == "wheel":
                artifact.update(
                    path=None,
                    retained_sha256=None,
                    status="metadata receipt only; restricted bundled resource; no wheel retained",
                )
            else:
                name = PurePosixPath(url.path).name
                if artifact["excluded_members"]:
                    name = f"octop_harness-{package['version']}-prismos-source.tar.gz"
                    data = filtered_source(members, artifact["excluded_members"])
                path = DESTINATION / "archives" / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(data)
                artifact.update(
                    path=path.relative_to(ROOT).as_posix(),
                    retained_sha256=digest(data),
                    status="filtered source with explicit exclusions"
                    if artifact["excluded_members"]
                    else "byte-identical locked artifact",
                )
            artifacts.append(artifact)
        if artifacts[0]["metadata"] != artifacts[1]["metadata"]:
            raise ValueError("Source and wheel metadata differ")
        packages.append(
            {
                "name": package["name"],
                "version": package["version"],
                "source": package["source"],
                "status": "source archived with license exclusions as recorded; not installed or enabled",
                "artifacts": artifacts,
                "locked_dependencies": package.get("dependencies", []),
                "locked_optional_dependencies": package.get(
                    "optional-dependencies", {}
                ),
            }
        )
    value = {
        "schema_version": 3,
        "exclusion_policy": POLICY_ID,
        "main_revision": baseline["revision"],
        "main_archive_sha256": baseline["archive_sha256"],
        "lock_source": "uv.lock in pinned main archive",
        "packages": packages,
        "runtime_integration": False,
        "restricted_resource": {
            "source": RESTRICTED,
            "sources": list(HARNESS_PREFIXES),
            "license_sha256": RESTRICTED_LICENSE_SHA,
            "status": "excluded; independently implement capability",
            "capabilities": ["O07", "O05"],
        },
    }
    (DESTINATION / "manifest.json").write_text(
        json.dumps(value, indent=2, ensure_ascii=False) + "\n"
    )
    return {
        "packages": len(packages),
        "retained_artifacts": sum(
            artifact["path"] is not None
            for package in packages
            for artifact in package["artifacts"]
        ),
        "excluded_source_files": len(packages[2]["artifacts"][0]["excluded_members"]),
        "runtime_integration": False,
    }


def verify() -> dict:
    actual = json.loads((DESTINATION / "manifest.json").read_text())
    baseline = json.loads((ROOT / "vendor/octop/manifest.json").read_text())
    packages = {package["name"]: package for package in locked_packages()}
    if (
        actual["schema_version"] != 3
        or actual["exclusion_policy"] != POLICY_ID
        or actual["main_revision"] != baseline["revision"]
        or actual["main_archive_sha256"] != baseline["archive_sha256"]
    ):
        raise ValueError("External baseline mismatch")
    if (
        {package["name"] for package in actual["packages"]} != NAMES
        or len(actual["packages"]) != 4
        or actual["runtime_integration"]
    ):
        raise ValueError("External package coverage/scope mismatch")
    resource = actual["restricted_resource"]
    if (
        resource["sources"] != list(HARNESS_PREFIXES)
        or resource["license_sha256"] != LICENSE_SHA256
    ):
        raise ValueError("External resource policy mismatch")
    expected_paths = set()
    for package in actual["packages"]:
        locked = packages[package["name"]]
        if (
            package["source"] != locked["source"]
            or package["version"] != locked["version"]
            or [artifact["kind"] for artifact in package["artifacts"]]
            != ["sdist", "wheel"]
        ):
            raise ValueError("External version/artifact mismatch")
        for artifact in package["artifacts"]:
            origin = (
                locked["sdist"] if artifact["kind"] == "sdist" else locked["wheels"][0]
            )
            if (
                artifact["url"] != origin["url"]
                or artifact["sha256"] != origin["hash"].removeprefix("sha256:")
                or artifact["size"] != origin["size"]
            ):
                raise ValueError("External origin lock mismatch")
            if artifact["kind"] == "sdist":
                identity = (package["name"], package["version"])
                member_digest = digest(
                    json.dumps(
                        artifact["members"], sort_keys=True, separators=(",", ":")
                    ).encode()
                )
                if (
                    identity not in PINNED_SOURCE_MEMBER_RECEIPTS
                    or member_digest != PINNED_SOURCE_MEMBER_RECEIPTS[identity]
                ):
                    raise ValueError("Pinned external source member receipt mismatch")
            if artifact["path"] is None:
                if package["name"] != "octop-harness" or artifact["kind"] != "wheel":
                    raise ValueError("Unexpected unretained artifact")
                continue
            path = ROOT / artifact["path"]
            if path.is_symlink() or not path.resolve().is_relative_to(
                (DESTINATION / "archives").resolve()
            ):
                raise ValueError("Unsafe retained archive path")
            expected_paths.add(artifact["path"])
            data = path.read_bytes()
            if digest(data) != artifact["retained_sha256"]:
                raise ValueError("Retained artifact hash mismatch")
            members = read_members(data, wheel=artifact["kind"] == "wheel")
            expected = {
                name: checksum
                for name, checksum in artifact["members"].items()
                if name not in artifact["excluded_members"]
            }
            if {
                name: digest(content) for name, content in members.items()
            } != expected or metadata_for(package, artifact["kind"], members) != {
                key: artifact[key] for key in ("metadata_path", "metadata")
            }:
                raise ValueError("Retained source/member metadata mismatch")
            if package["name"] == "octop-harness":
                excluded = harness_exclusions(package, artifact["members"])
                prefixes = tuple(
                    f"octop_harness-{package['version']}/" + prefix
                    for prefix in HARNESS_PREFIXES
                )
                if artifact["excluded_members"] != excluded or any(
                    name.startswith(prefixes) for name in members
                ):
                    raise ValueError("Restricted resource filtering mismatch")
            elif (
                artifact["excluded_members"]
                or artifact["retained_sha256"] != artifact["sha256"]
            ):
                raise ValueError("Unexpected modification of locked artifact")
    if {
        path.relative_to(ROOT).as_posix()
        for path in (DESTINATION / "archives").iterdir()
        if path.is_file()
    } != expected_paths:
        raise ValueError("External archive inventory mismatch")
    return {
        "verified": True,
        "packages": 4,
        "retained_artifacts": len(expected_paths),
        "restricted_resource_excluded": True,
        "runtime_integration": False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("fetch", "verify"))
    args = parser.parse_args()
    print(
        json.dumps(
            fetch() if args.command == "fetch" else verify(),
            ensure_ascii=False,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
