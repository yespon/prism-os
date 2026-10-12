"""Deterministic host Skill archives from retained sources; never installation."""

from __future__ import annotations

import hashlib
import io
import json
import tempfile
import zipfile
from pathlib import Path, PurePosixPath

import yaml
from prismos_octop import catalog
from prismos_octop.upstream.frontmatter import parse_frontmatter

from deerflow.skills.validation import ALLOWED_FRONTMATTER_PROPERTIES, _validate_skill_frontmatter

ORIGIN_FILE = "PRISMOS_ORIGIN.json"
UPSTREAM_LICENSE_FILE = "LICENSE.octop"
_UPSTREAM_LICENSE_SHA256 = "5f2089cdcc57d00c6b70c0fb83368cbf3a86bb57839385fc6ac9086878d606e8"
_ADAPTATIONS = {
    ("expert:cvm-cluster-doctor", "skills/tencentcloud-infra"): "tencentcloud-infra",
    ("expert:office-automation", "skills/file_reader"): "file-reader",
    ("expert:tencentcloud-api", "skills/tcapi"): "tcapi",
}


class SkillPackageUnavailable(ValueError):
    pass


def _upstream_license_bytes() -> bytes:
    path = catalog.ROOT / "LICENSE"
    if not path.is_file() or path.is_symlink() or path.resolve() != catalog.ROOT.resolve() / "LICENSE":
        raise ValueError("Upstream license integrity failure")
    try:
        data = path.read_bytes()
    except OSError:
        raise ValueError("Upstream license integrity failure") from None
    if hashlib.sha256(data).hexdigest() != _UPSTREAM_LICENSE_SHA256:
        raise ValueError("Upstream license integrity failure")
    return data


def prepare_skill_package(declaration: dict, resource: dict) -> dict:
    if resource["kind"] != "skill_bundle":
        raise SkillPackageUnavailable("Only retained Skill bundles can be exported")
    folder = (catalog.ROOT / declaration["template_source"]["target"]).parent
    root = resource["root"]
    files = {}
    source_hashes = {}
    for member in resource["members"]:
        relative = str(PurePosixPath(member["path"]).relative_to(root))
        if relative in {ORIGIN_FILE, UPSTREAM_LICENSE_FILE}:
            raise SkillPackageUnavailable("Reserved provenance member already exists")
        path = folder / member["path"]
        if path.resolve() != folder.resolve() / member["path"]:
            raise ValueError("Resource source alias is unavailable")
        data = path.read_bytes()
        if hashlib.sha256(data).hexdigest() != member["sha256"]:
            raise ValueError("Resource source integrity failure")
        files[relative] = data
        source_hashes[relative] = member["sha256"]
    metadata, body = parse_frontmatter(files["SKILL.md"].decode())
    adapted = (declaration["template_id"], root) in _ADAPTATIONS
    if adapted:
        metadata = dict(metadata)
        metadata["name"] = _ADAPTATIONS[(declaration["template_id"], root)]
        extra = {key: metadata.pop(key) for key in list(metadata) if key not in ALLOWED_FRONTMATTER_PROPERTIES}
        if extra:
            existing = metadata.get("metadata") or {}
            if not isinstance(existing, dict) or "octop_source" in existing:
                raise SkillPackageUnavailable("Source metadata needs an explicit reviewed adapter")
            metadata["metadata"] = {**existing, "octop_source": extra}
        files["SKILL.md"] = ("---\n" + yaml.safe_dump(metadata, allow_unicode=True, sort_keys=False) + "---\n" + body).encode()
    with tempfile.TemporaryDirectory(prefix="prismos-skill-format-") as directory:
        Path(directory, "SKILL.md").write_bytes(files["SKILL.md"])
        valid, message, name = _validate_skill_frontmatter(Path(directory))
    if not valid or name is None:
        raise SkillPackageUnavailable(message)
    files[UPSTREAM_LICENSE_FILE] = _upstream_license_bytes()
    record = {
        "schema_version": "prismos.skill-origin.v1",
        "template_id": declaration["template_id"],
        "resource_id": resource["id"],
        "revision": declaration["revision"],
        "bundle_source_sha256": resource["bundle_sha256"],
        "adapter_version": 1,
        "upstream_license": {"source": "LICENSE", "file": UPSTREAM_LICENSE_FILE, "sha256": _UPSTREAM_LICENSE_SHA256},
        "host_name": name,
        "files": [{"path": relative, "source_sha256": source_hashes[relative], "host_sha256": hashlib.sha256(data).hexdigest()} for relative, data in sorted(files.items()) if relative in source_hashes],
    }
    files[ORIGIN_FILE] = (json.dumps(record, sort_keys=True, ensure_ascii=False, indent=2) + "\n").encode()
    return {"name": name, "adapted": adapted, "files": files, "source_files_sha256": source_hashes, "host_files_sha256": {p: hashlib.sha256(data).hexdigest() for p, data in files.items()}}


def skill_archive(package: dict) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for relative, data in sorted(package["files"].items()):
            entry = zipfile.ZipInfo(package["name"] + "/" + relative, date_time=(1980, 1, 1, 0, 0, 0))
            entry.compress_type = zipfile.ZIP_DEFLATED
            entry.external_attr = 0o100644 << 16
            archive.writestr(entry, data)
    return output.getvalue()
