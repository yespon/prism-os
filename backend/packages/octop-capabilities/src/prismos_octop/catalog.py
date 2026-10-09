"""Read-only template catalog. Does not load plugins, execute scripts or grant tools."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from functools import lru_cache
from pathlib import Path
from typing import Literal

from .upstream.frontmatter import parse_frontmatter
from .upstream.mbti_profiles import get_all_profiles, get_profile

Locale = Literal["zh", "en"]
ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"


@lru_cache(maxsize=1)
def provenance() -> dict:
    value = json.loads((DATA / "provenance.json").read_text(encoding="utf-8"))
    expected_data = {entry["target"] for entry in value["imports"] if entry["target"].startswith(("data/experts/", "data/subagents/"))}
    actual_data = {path.relative_to(ROOT).as_posix() for folder in (DATA / "experts", DATA / "subagents") for path in folder.rglob("*") if path.is_file() and path.suffix != ".pyc"}
    if actual_data != expected_data:
        raise ValueError("Catalog source inventory mismatch")
    for entry in value["imports"]:
        path = ROOT / entry["target"]
        if not path.resolve().is_relative_to(ROOT.resolve()) or path.is_symlink():
            raise ValueError("Invalid catalog source path")
        if hashlib.sha256(path.read_bytes()).hexdigest() != entry["sha256"]:
            raise ValueError("Catalog source integrity failure")
    return value


def _localized(value, locale: Locale, fallback="") -> str:
    if isinstance(value, dict):
        return str(value.get(locale) or value.get("en") or fallback)
    return str(value or fallback)


@lru_cache(maxsize=2)
def _templates(locale: Locale) -> dict[str, dict]:
    origin = provenance()
    entries = {}
    for folder in sorted((DATA / "experts").iterdir()):
        manifest = folder / "manifest.json"
        if not folder.is_dir() or not manifest.is_file():
            continue
        metadata = json.loads(manifest.read_text(encoding="utf-8"))
        text = []
        for filename in metadata.get("prompt_files", ["SOUL.md"]):
            # Only declared root persona files, never arbitrary paths or scripts.
            if Path(filename).name != filename or not filename.endswith(".md"):
                raise ValueError("Invalid expert prompt path")
            path = folder / filename
            if path.is_file():
                _, body = parse_frontmatter(path.read_text(encoding="utf-8"))
                text.append(body.strip())
        if not text:
            continue
        template_id = f"expert:{folder.name}"
        resources = sorted(p.relative_to(folder).as_posix() for p in folder.rglob("*") if p.is_file() and p.relative_to(folder).parts[0] in {"skills", "agents", "scripts"})
        entries[template_id] = {
            "id": template_id,
            "kind": "expert",
            "name": _localized(metadata.get("label"), locale, folder.name),
            "suggested_name": folder.name,
            "description": _localized(metadata.get("description"), locale),
            "locale": locale,
            "division": "experts",
            "system_prompt": "\n\n".join(text),
            "bundled_resources": resources,
            "source_path": f"src/octop/infra/agents/experts/library/{folder.name}/manifest.json",
            "revision": origin["revision"],
        }
    locale_root = DATA / "subagents" / locale
    for path in sorted(locale_root.glob("*/*.md")):
        meta, body = parse_frontmatter(path.read_text(encoding="utf-8"))
        if not meta or meta.get("name") == "TODO_TRANSLATE" or not body.strip():
            continue
        template_id = f"subagent:{path.parent.name}.{path.stem}"
        entries[template_id] = {
            "id": template_id,
            "kind": "subagent",
            "name": str(meta.get("name") or path.stem),
            "suggested_name": path.stem,
            "description": str(meta.get("description") or ""),
            "locale": locale,
            "division": path.parent.name,
            "system_prompt": body.strip(),
            "bundled_resources": [],
            "source_path": f"src/octop/infra/agents/subagents/library/{locale}/{path.parent.name}/{path.name}",
            "revision": origin["revision"],
        }
    return entries


def list_templates(locale: Locale = "zh", kind: str | None = None) -> list[dict]:
    return [{key: value for key, value in entry.items() if key != "system_prompt"} for entry in _templates(locale).values() if kind is None or entry["kind"] == kind]


def get_template(template_id: str, locale: Locale = "zh") -> dict:
    entry = _templates(locale).get(template_id)
    if entry is None:
        raise KeyError(template_id)
    return dict(entry)


def list_personas() -> list[dict]:
    provenance()
    return [asdict(profile) for profile in get_all_profiles()]


def render_persona(code: str, locale: Locale = "zh") -> str:
    profile = get_profile(code)
    if profile is None:
        raise ValueError("Unknown personality type")
    behavior = asdict(profile.behavior)
    keys = ["answer_style", "casual_chat", "conflict", "creativity", "emotion", "planning"]
    suffix = "_zh" if locale == "zh" else ""
    name = profile.name_zh if locale == "zh" else profile.name_en
    return f"## {profile.code} · {name}\n\n" + "\n".join(f"- {behavior[key + suffix]}" for key in keys)
