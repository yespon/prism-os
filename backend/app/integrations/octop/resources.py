"""Read-only native format checks; resource rights/installations remain explicit."""

from __future__ import annotations

from prismos_octop import catalog
from prismos_octop.resources import resource_declaration

from deerflow.skills.validation import _validate_skill_frontmatter


def resource_preflight(template_id: str, locale: catalog.Locale = "zh") -> dict:
    declaration = resource_declaration(template_id, locale)
    template_target = declaration["template_source"]["target"]
    folder = (catalog.ROOT / template_target).parent
    for resource in declaration["resources"]:
        if resource["kind"] == "skill_bundle":
            valid, message, name = _validate_skill_frontmatter(folder / resource["root"])
            resource["host_format"] = {"status": "compatible" if valid else "needs_adapter", "skill_name": name, "detail": message}
            resource["remaining_checks"] = ["current_resource_acl", "name_and_source_collision", "runtime_dependencies", "tool_mcp_bindings", "atomic_install_and_recovery", "execution_pep_and_isolation"]
        else:
            resource["host_format"] = {"status": "binding_required"}
            resource["remaining_checks"] = ["current_resource_acl", "runtime_dependencies", "tool_or_delegation_binding", "execution_pep_and_isolation"]
    declaration["preflight_scope"] = "pinned source and native Skill frontmatter format only"
    declaration["runtime_dependencies_checked"] = False
    declaration["permission_grants"] = False
    return declaration
