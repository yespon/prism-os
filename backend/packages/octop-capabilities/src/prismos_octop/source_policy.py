"""Explicit source curation policy shared by importer, catalog and artifact checks."""

POLICY_ID = "2026-10-10-office-resource-exclusions-v1"
LICENSE_SHA256 = "79f6d8f5b427252fa3b1c11ecdbdb6bf610b944f7530b4de78f770f38741cfaa"
OFFICE_ROOT = "src/octop/infra/agents/experts/library/office-automation/skills/"
MAIN_PREFIXES = tuple(OFFICE_ROOT + name + "/" for name in ("docx", "pdf", "pptx", "xlsx"))
HARNESS_PREFIXES = tuple("src/octop_harness/builtin/skills/" + locale + "/powerpoint/" for locale in ("en", "zh"))


def main_exclusions(source_hashes: dict[str, str]) -> dict[str, str]:
    result = {path: sha for path, sha in sorted(source_hashes.items()) if path.startswith(MAIN_PREFIXES)}
    for prefix in MAIN_PREFIXES:
        if any(path.startswith(prefix) for path in result):
            if result.get(prefix + "LICENSE.txt") != LICENSE_SHA256:
                raise ValueError("Office resource license changed or missing; review required")
    return result


def restricted_package_path(path: str) -> bool:
    return any("data/experts/office-automation/skills/" + name + "/" in path for name in ("docx", "pdf", "pptx", "xlsx"))
