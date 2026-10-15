"""Prepare an owned compatibility worker without changing the host lock/runtime."""

import argparse
import hashlib
import json
import re
import tomllib
from pathlib import Path, PurePosixPath

import octop_external
from octop_sync import archive_files
from packaging.requirements import Requirement

ROOT = Path(__file__).resolve().parents[1]
PACKAGES = {"octop-browser", "octop-gateway", "octop-harness", "octop-memory"}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def write_once(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.is_symlink() or path.read_bytes() != data:
            raise ValueError(
                "Owned worker input already exists with different contents"
            )
    else:
        with path.open("xb") as stream:
            stream.write(data)


def validate_lock(path, requirements, versions):
    """A changed upstream may not silently reuse a stale worker dependency lock."""
    pins = {}
    for line in path.read_text().splitlines():
        if not line or line[0].isspace() or line.startswith("#"):
            continue
        expression = line.removesuffix("\\").strip()
        if not re.fullmatch(r"[A-Za-z0-9_.-]+==[A-Za-z0-9.!+_-]+", expression):
            raise ValueError("Worker lock must contain exact registry version pins")
        requirement = Requirement(expression)
        name = requirement.name.lower().replace("_", "-")
        if name in pins:
            raise ValueError("Duplicate worker dependency pin")
        pins[name] = next(iter(requirement.specifier)).version
    for expression in requirements:
        requirement = Requirement(expression)
        name = requirement.name.lower().replace("_", "-")
        if name not in pins or not requirement.specifier.contains(pins[name]):
            raise ValueError(
                "Worker lock does not satisfy retained source requirements"
            )
    for name, values in versions.items():
        if name in pins and len(values) == 1 and pins[name] not in values:
            raise ValueError("Worker lock differs from unique upstream version")


def prepare(output):
    output = output.absolute()
    if output.resolve() != output or not output.is_relative_to(ROOT / "backend/tmp"):
        raise ValueError(
            "Worker context must be a non-aliased owned backend/tmp directory"
        )
    octop_external.verify()
    manifest_path = ROOT / "vendor/octop/external/manifest.json"
    manifest = json.loads(manifest_path.read_text())
    receipts, requirements, wheels = [], set(), []
    for package in manifest["packages"]:
        core = []
        for expression in package["artifacts"][0]["metadata"]["requirements"]:
            requirement = Requirement(expression)
            if requirement.url is not None:
                raise ValueError(
                    "Direct dependency URLs are unavailable for this worker"
                )
            if requirement.marker and not requirement.marker.evaluate({"extra": ""}):
                continue
            core.append(expression)
            if requirement.name.lower().replace("_", "-") not in PACKAGES:
                requirements.add(expression)
        if package["name"] != "octop-harness":
            artifact = next(a for a in package["artifacts"] if a["kind"] == "wheel")
            data = (ROOT / artifact["path"]).read_bytes()
            assert sha(data) == artifact["retained_sha256"]
            filename = Path(artifact["path"]).name
            write_once(output / "archives" / filename, data)
            wheels.append(f"./archives/{filename} --hash=sha256:{sha(data)}")
        else:
            artifact = package["artifacts"][0]
            members = octop_external.artifact_members(ROOT / artifact["path"])
            prefix = f"octop_harness-{package['version']}/"
            retained = {}
            for name, data in members.items():
                if not name.startswith(prefix):
                    raise ValueError("Filtered source prefix mismatch")
                relative = PurePosixPath(name[len(prefix) :])
                if (
                    relative.is_absolute()
                    or ".." in relative.parts
                    or "\\" in str(relative)
                ):
                    raise ValueError("Filtered source path mismatch")
                if not (
                    str(relative).startswith("src/octop_harness/")
                    or str(relative) == "LICENSE"
                ):
                    continue
                if name in artifact["excluded_members"]:
                    raise ValueError("Excluded source must not enter worker")
                assert sha(data) == artifact["members"][name]
                write_once(output / "harness" / str(relative), data)
                retained[str(relative)] = sha(data)
            if (
                "src/octop_harness/__init__.py" not in retained
                or "LICENSE" not in retained
            ):
                raise ValueError("Filtered source or license missing")
        receipts.append(
            {
                "name": package["name"],
                "version": package["version"],
                "retained_archive_sha256": artifact["retained_sha256"],
                "source_only": package["name"] == "octop-harness",
                "core_requirements": core,
            }
        )
    receipt = {
        "schema": "prismos.octop-compat-source.v1",
        "external_manifest_sha256": sha(manifest_path.read_bytes()),
        "packages": receipts,
        "excluded_harness_members": len(
            next(p for p in manifest["packages"] if p["name"] == "octop-harness")[
                "artifacts"
            ][0]["excluded_members"]
        ),
        "harness_retained_source_sha256": retained,
        "native_execution_enabled": False,
        "host_lock_sha256": sha((ROOT / "backend/uv.lock").read_bytes()),
    }
    write_once(
        output / "requirements.in", ("\n".join(sorted(requirements)) + "\n").encode()
    )
    write_once(output / "wheels.lock", ("\n".join(sorted(wheels)) + "\n").encode())
    write_once(
        output / "source-receipt.json", (json.dumps(receipt, indent=2) + "\n").encode()
    )
    baseline = json.loads((ROOT / "vendor/octop/manifest.json").read_text())
    main_files = archive_files(
        ROOT / "vendor/octop/upstream.tar.gz", baseline["revision"]
    )
    upstream = tomllib.loads(main_files["uv.lock"].decode())
    versions = {}
    for item in upstream["package"]:
        if item.get("version") and item["name"] not in PACKAGES:
            versions.setdefault(item["name"], set()).add(item["version"])
    constraints = [
        name + "==" + next(iter(values))
        for name, values in sorted(versions.items())
        if len(values) == 1
    ]
    write_once(
        output / "constraints-upstream.txt", ("\n".join(constraints) + "\n").encode()
    )
    write_once(
        output / "resolution-inputs.json",
        (
            json.dumps(
                {
                    "upstream_lock_sha256": sha(main_files["uv.lock"]),
                    "unique_version_constraints": len(constraints),
                    "ambiguous_forks_not_constrained": {
                        name: sorted(values)
                        for name, values in versions.items()
                        if len(values) != 1
                    },
                    "host_lock_not_modified": True,
                },
                indent=2,
            )
            + "\n"
        ).encode(),
    )
    validate_lock(
        ROOT / "docker/octop-worker-compat/requirements.lock", requirements, versions
    )
    for name in ["Dockerfile", "worker_rpc.py", "requirements.lock"]:
        write_once(
            output / name, (ROOT / "docker/octop-worker-compat" / name).read_bytes()
        )
    print(
        json.dumps(
            {
                "prepared": True,
                "context": str(output),
                "source_only_harness": True,
                "retained_harness_files": len(retained),
                "excluded_harness_members": receipt["excluded_harness_members"],
                "host_lock_unchanged": receipt["host_lock_sha256"]
                == sha((ROOT / "backend/uv.lock").read_bytes()),
            }
        )
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    prepare(args.output_dir)


if __name__ == "__main__":
    main()
