"""Pinned resource declarations; reading never installs, grants or executes."""

from __future__ import annotations

import hashlib
import json
from pathlib import PurePosixPath

from . import catalog


def _digest(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


def resource_declaration(template_id: str, locale: catalog.Locale = "zh") -> dict:
    if locale not in ("zh", "en"):
        raise ValueError("Unsupported resource locale")
    template = catalog.get_template(template_id, locale)
    origin = catalog.provenance()
    source_entry = next(entry for entry in origin["imports"] if entry["source"] == template["source_path"])
    if template["kind"] == "expert":
        prefix = str(PurePosixPath(source_entry["target"]).parent) + "/"
        expected = {entry["target"]: entry for entry in origin["imports"] if entry["target"].startswith(prefix)}
        folder = catalog.ROOT / prefix
        actual = set()
        for file in folder.rglob("*"):
            if file.is_symlink():
                raise ValueError("Resource source alias is unavailable")
            if file.is_file() and file.suffix != ".pyc":
                actual.add(file.relative_to(catalog.ROOT).as_posix())
        if actual != set(expected):
            raise ValueError("Resource source inventory mismatch")
    else:
        prefix = ""
        expected = {source_entry["target"]: source_entry}
    # Recheck the selected origin even if the catalog's immutable cache is warm.
    for target, entry in expected.items():
        path = catalog.ROOT / target
        if path.resolve() != catalog.ROOT.resolve() / target or path.is_symlink():
            raise ValueError("Resource source alias is unavailable")
        if hashlib.sha256(path.read_bytes()).hexdigest() != entry["sha256"]:
            raise ValueError("Resource source integrity failure")
    members = []
    template_members = []
    if template["kind"] == "expert":
        manifest = json.loads((catalog.ROOT / source_entry["target"]).read_text())
        prompt_files = set(manifest.get("prompt_files", ["SOUL.md"])) | {"manifest.json"}
        for target, entry in sorted(expected.items()):
            relative = target[len(prefix) :]
            member = {"path": relative, "sha256": entry["sha256"], "source_path": entry["source"]}
            (template_members if relative in prompt_files else members).append(member)
        legacy_members = {member["path"] for member in members if PurePosixPath(member["path"]).parts[0] in {"skills", "scripts", "agents"}}
        if legacy_members != set(template["bundled_resources"]):
            raise ValueError("Resource template inventory mismatch")
    else:
        template_members = [{"path": PurePosixPath(source_entry["target"]).name, "sha256": source_entry["sha256"], "source_path": source_entry["source"]}]
    roots = sorted({str(PurePosixPath(member["path"]).parent) for member in members if PurePosixPath(member["path"]).name == "SKILL.md"}, key=len, reverse=True)
    grouped = {}
    for member in members:
        path = member["path"]
        root = next((root for root in roots if path.startswith(root + "/")), None)
        kind = (
            "skill_bundle"
            if root is not None
            else "subagent_definition"
            if path.startswith("agents/")
            else "script"
            if path.startswith("scripts/") or PurePosixPath(path).suffix in {".py", ".sh", ".js", ".ts", ".ps1"}
            else "reference_asset"
        )
        root = root or path
        grouped.setdefault((kind, root), []).append(member)
    resources = []
    for (kind, root), files in sorted(grouped.items()):
        resource_id = "resource:" + _digest([template_id, kind, root])
        digest = _digest([{key: member[key] for key in ("path", "sha256")} for member in files])
        resources.append({"id": resource_id, "kind": kind, "root": root, "bundle_sha256": digest, "members": files, "installation_status": "not_checked", "execution_ready": False})
    return {
        "schema_version": "octop.resources.v1",
        "template_id": template_id,
        "locale": locale,
        "revision": origin["revision"],
        "source_archive_sha256": origin["archive_sha256"],
        "template_source": {key: source_entry[key] for key in ("source", "target", "sha256")},
        "prompt_sha256": hashlib.sha256(template["system_prompt"].encode()).hexdigest(),
        "source_verified": True,
        "declaration_sha256": _digest([{key: member[key] for key in ("path", "sha256")} for member in members]),
        "resources": resources,
        "member_count": len(members),
        "legacy_bundle_member_count": len(template["bundled_resources"]),
        "additional_member_count": len(members) - len(template["bundled_resources"]),
        "template_members": template_members,
        "verified_source_member_count": len(expected),
        "excluded_resources": template["excluded_resources"],
        "excluded_resources_status": "independent implementation pending",
        "installation_checked": False,
        "execution_ready": False,
    }
