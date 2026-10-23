#!/usr/bin/env python3
"""Generate/verify exhaustive static inventories; never load upstream plugins or tools."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
import sys
import tomllib
from pathlib import Path, PurePosixPath

import yaml
from octop_external import artifact_members
from octop_external import verify as verify_external
from octop_sync import archive_files
from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

# Dependency inventory evaluates a declared target, independent of the generating host.
TARGET_ENVIRONMENT = {
    "implementation_name": "cpython",
    "implementation_version": "3.12.0",
    "os_name": "posix",
    "platform_machine": "x86_64",
    "platform_python_implementation": "CPython",
    "platform_release": "",
    "platform_system": "Linux",
    "platform_version": "",
    "python_full_version": "3.12.0",
    "python_version": "3.12",
    "sys_platform": "linux",
}

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "docs/superpowers/evidence/2026-10-10-octop-n06-presentation/inventory"
EXPERTS = "src/octop/infra/agents/experts/library/"
SUBAGENTS = "src/octop/infra/agents/subagents/library/"
CATALOG = "src/octop/infra/connectors/catalog.py"
REVIEW = "docs/strategy/2026-10-08-octop-full-capability-roadmap-review.md"
OLD_LEDGER = (
    "docs/superpowers/evidence/2026-10-09-octop-source-import/capability-ledger.json"
)

# Source-level grouping; deployed route prefixes and behavior still need host tests.
ROUTER_GROUPS = [
    (
        [
            "setup.py",
            "auth.py",
            "auth_oidc.py",
            "auth_oauth.py",
            "auth_ldap.py",
            "users.py",
            "user_roles.py",
            "invites.py",
        ],
        ["O01", "O02", "O03"],
        "identity",
        "N14",
    ),
    (
        ["agents.py", "experts.py", "teams.py", "mbti.py", "subagents.py"],
        ["O04", "O05", "O06", "O08", "O09"],
        "agent assets",
        "N09",
    ),
    (
        ["agent_tools.py", "skills.py", "skill_packages.py", "internal_mcp.py"],
        ["O07", "O08", "O26"],
        "extensions",
        "N09",
    ),
    (["chat/", "slash.py"], ["O10", "O11"], "entry and execution", "N08"),
    (
        ["channels.py", "cron.py", "proactive_care.py"],
        ["O12", "O13", "O14"],
        "automation and channels",
        "N11",
    ),
    (
        [
            "providers.py",
            "media_generation.py",
            "ollama_models.py",
            "ollama_download_store.py",
            "onnx_models.py",
            "voice.py",
        ],
        ["O15", "O16", "O17", "O18"],
        "models and media",
        "N12",
    ),
    (
        ["memory.py", "memory_portable.py", "knowledge_bases.py"],
        ["O19", "O20"],
        "knowledge and data",
        "N10",
    ),
    (
        [
            "workspace.py",
            "agent_files.py",
            "filesystem.py",
            "search.py",
            "uploads.py",
            "storage_backends.py",
            "envs.py",
        ],
        ["O21", "O22", "O23"],
        "storage and data",
        "N13",
    ),
    (
        ["connectors.py", "acp.py"],
        ["O24", "O25", "O27", "O28"],
        "connectors and protocols",
        "N10",
    ),
    (["terminal.py", "browser/"], ["O29", "O30", "O31"], "tools and devices", "N12"),
    (["desktop/"], ["O32"], "tools and devices", "N12"),
    (["mobile/"], ["O33"], "tools and devices", "N12"),
    (["plugins.py"], ["O36", "O37"], "extensions", "N14"),
    (
        ["security.py", "observability.py", "usage.py", "admin.py"],
        ["O38", "O39"],
        "platform governance",
        "N13",
    ),
    (
        [
            "backup.py",
            "update.py",
            "update_store.py",
            "tls.py",
            "health.py",
            "i18n.py",
            "preferences.py",
            "settings.py",
        ],
        ["O01", "O34", "O35", "O40"],
        "delivery",
        "N07",
    ),
    (["bridge.py"], ["O41"], "remote protocols", "N14"),
]
EXTERNAL_ROLES = {
    "octop-browser": ("tools and devices", "N12"),
    "octop-gateway": ("automation and channels", "N11"),
    "octop-harness": ("runtime integration", "N09"),
    "octop-memory": ("knowledge and data", "N10"),
}


def digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def literal(node):
    """Never eval source or import Octop. Unknown dynamic fields stay explicit."""
    try:
        return ast.literal_eval(node)
    except (ValueError, TypeError):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "ConnectorCredentialField"
        ):
            return {keyword.arg: literal(keyword.value) for keyword in node.keywords}
        if isinstance(node, (ast.Tuple, ast.List)):
            return [literal(element) for element in node.elts]
        return {"dynamic_expression": ast.unparse(node)}


def connector_entries(source: bytes) -> list[dict]:
    result = []
    for node in ast.walk(ast.parse(source)):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "ConnectorCatalogEntry"
        ):
            entry = {keyword.arg: literal(keyword.value) for keyword in node.keywords}
            if not isinstance(entry.get("kind"), str):
                raise ValueError("Dynamic connector identity requires explicit review")
            result.append({**entry, "line": node.lineno})
    if len({entry["kind"] for entry in result}) != len(result):
        raise ValueError("Duplicate connector identity")
    return result


def imports(source: bytes) -> dict:
    try:
        tree = ast.parse(source)
    except (SyntaxError, UnicodeError):
        return {"imports": [], "parse_status": "requires source review"}
    values = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            values.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            values.add("." * node.level + node.module)
    return {
        "imports": sorted(values),
        "parse_status": "parsed statically; not executed",
    }


def group_router(path: str):
    for prefixes, capabilities, role, next_task in ROUTER_GROUPS:
        if any(
            path == prefix or prefix.endswith("/") and path.startswith(prefix)
            for prefix in prefixes
        ):
            return capabilities, role, next_task
    raise ValueError(f"Unclassified router: {path}")


def item(
    item_id,
    sources,
    capabilities,
    role,
    next_task,
    *,
    archived=None,
    imported=False,
    adapted=False,
    verified=False,
    remaining=None,
    permissions=None,
    evidence=None,
    **extra,
):
    return {
        "id": item_id,
        "source_refs": sources,
        "capabilities": capabilities,
        "stages": {
            "archived": bool(sources) if archived is None else archived,
            "imported": imported,
            "adapted": adapted,
            "verified": verified,
        },
        "status": "verified"
        if verified
        else "adapted"
        if adapted
        else "imported"
        if imported
        else "archived"
        if sources and archived is not False
        else "remaining",
        "permissions": permissions
        or ["tenant_resource_acl", "runtime permissions require host review"],
        "dependencies": [next_task],
        "owner_role": role,
        "owner_assignment": "role only; no human assigned",
        "verification_evidence": evidence or [],
        "remaining": remaining or [],
        "full_parity": False,
        **extra,
    }


def dependency_inventory(externals, main_files):
    host_bytes = (ROOT / "backend/uv.lock").read_bytes()
    host = {
        package["name"]: package["version"]
        for package in tomllib.loads(host_bytes.decode())["package"]
        if package.get("source", {}).get("registry")
    }
    upstream = {
        package["name"]: package["version"]
        for package in tomllib.loads(main_files["uv.lock"].decode())["package"]
    }
    result = []
    for package in externals["packages"]:
        metadata = package["artifacts"][0]["metadata"]
        core, extras = [], {}
        for raw in metadata["requirements"]:
            requirement = Requirement(raw)
            name = canonicalize_name(requirement.name)
            base = not requirement.marker or requirement.marker.evaluate(
                {**dict(TARGET_ENVIRONMENT), "extra": ""}
            )
            candidate = {
                "requirement": raw,
                "name": name,
                "host_locked": host.get(name),
                "upstream_locked": upstream.get(name),
                "host_check": "missing"
                if name not in host
                else "compatible"
                if requirement.specifier.contains(host[name])
                else "conflict",
            }
            if base:
                core.append(candidate)
            else:
                for extra in metadata["extras"]:
                    if requirement.marker.evaluate(
                        {**dict(TARGET_ENVIRONMENT), "extra": extra}
                    ):
                        extras.setdefault(extra, []).append(candidate)
        role, task = EXTERNAL_ROLES[package["name"]]
        result.append(
            {
                "name": package["name"],
                "version": package["version"],
                "license_declared": metadata["license_expression"]
                or metadata["license"],
                "source_urls": metadata["project_urls"],
                "requires_python": metadata["requires_python"],
                "core": core,
                "extras": extras,
                "owner_role": role,
                "dependencies": [task],
                "runtime_integrated": False,
                "coupling_review": "AST imports in source-index.json; runtime semantics not tested",
                "decision": "explicit host adapter or isolated worker; preserve PrismOS runtime and facts",
            }
        )
    return {
        "host_lock_sha256": digest(host_bytes),
        "upstream_lock_sha256": digest(main_files["uv.lock"]),
        "marker_environment": {
            key: dict(TARGET_ENVIRONMENT)[key]
            for key in ("python_version", "sys_platform", "platform_machine")
        },
        "packages": result,
        "full_upstream_lock_installed": False,
        "host_lock_modified": False,
    }


def build() -> dict[str, dict | list]:
    verify_external()  # Also validates main source/import integrity.
    baseline = json.loads((ROOT / "vendor/octop/manifest.json").read_text())
    main_files = archive_files(
        ROOT / "vendor/octop/upstream.tar.gz", baseline["revision"]
    )
    externals = json.loads((ROOT / "vendor/octop/external/manifest.json").read_text())
    mappings = {entry["source"]: entry["target"] for entry in baseline["imports"]}
    sys.path.insert(0, str(ROOT / "backend/packages/octop-capabilities/src"))
    from prismos_octop.catalog import get_template, list_personas, list_templates
    from prismos_octop.upstream.frontmatter import parse_frontmatter

    catalogs = {
        locale: {entry["id"]: entry for entry in list_templates(locale)}
        for locale in ("zh", "en")
    }
    source_index = [
        {
            "id": "main:" + path,
            "origin": "main",
            "path": path,
            "sha256": digest(data),
            "status": "imported" if path in mappings else "archived",
            "imported_target": mappings.get(path),
            "integrity_verified": True,
            "behavior_verified": False,
            **(imports(data) if path.endswith(".py") else {}),
        }
        for path, data in sorted(main_files.items())
    ]
    (
        skills,
        scripts,
        resources,
        experts,
        subagents,
        persona,
        plugins,
        connectors,
        endpoints,
    ) = [], [], [], [], [], [], [], [], []
    for path, data in sorted(main_files.items()):
        ref = "main:" + path
        if path.startswith(EXPERTS) and path.endswith("/manifest.json"):
            meta = json.loads(data)
            name = PurePosixPath(path).parent.name
            folder = str(PurePosixPath(path).parent) + "/"
            prompt_paths = []
            for prompt in meta["prompt_files"]:
                if PurePosixPath(prompt).name != prompt or not prompt.endswith(".md"):
                    raise ValueError("Unsafe expert prompt path")
                if folder + prompt in main_files:
                    prompt_paths.append(folder + prompt)
            for locale in ("zh", "en"):
                template = get_template("expert:" + name, locale)
                expected = "\n\n".join(
                    parse_frontmatter(main_files[p].decode())[1].strip()
                    for p in prompt_paths
                )
                if template["system_prompt"] != expected:
                    raise ValueError("Expert prompt host materialization mismatch")
            own_resources = [
                "main:" + p
                for p in main_files
                if p.startswith(folder) and p not in prompt_paths and p != path
            ]
            experts.append(
                item(
                    "expert:" + name,
                    [ref] + ["main:" + p for p in prompt_paths],
                    ["O05", "O06", "O07", "O08"],
                    "agent assets",
                    "N09",
                    imported=True,
                    adapted=True,
                    permissions=[
                        "agent.create",
                        "tenant membership",
                        "shared creation requires tenant admin",
                    ],
                    evidence=[
                        "backend/tests/test_octop_integration.py",
                        "generator: both locale prompt materializations",
                    ],
                    remaining=[
                        "full resource installation/binding",
                        "sharing/use/edit/revoke paths",
                        "actual expert execution",
                    ],
                    name=meta["label"],
                    required_skills=meta.get("requires_skills", []),
                    bundled_resource_refs=sorted(own_resources),
                    excluded_resource_refs=sorted(
                        "main:" + path
                        for path in baseline["excluded_source_files"]
                        if path.startswith(folder)
                    ),
                )
            )
            for field, task in [
                ("welcome_message", "N06"),
                ("quick_prompts", "N06"),
                ("task_examples", "N11"),
            ]:
                if field in meta:
                    persona.append(
                        item(
                            f"expert:{name}:{field}",
                            [ref],
                            ["O06"] if field != "task_examples" else ["O13"],
                            "content experience",
                            task,
                            imported=True,
                            remaining=[
                                "localized host flow and persistence",
                                "no automatic task activation",
                            ],
                            permissions=[
                                "agent.create/edit",
                                "task examples do not grant execution",
                            ],
                            localized_content=meta[field],
                        )
                    )
        if path.startswith(EXPERTS):
            relative = PurePosixPath(path[len(EXPERTS) :])
            if len(relative.parts) > 1:
                expert_id = relative.parts[0]
                resources.append(
                    item(
                        "resource:" + path,
                        [ref],
                        ["O05", "O07", "O08"],
                        "agent resources",
                        "N09",
                        imported=path in mappings,
                        remaining=[
                            "resource-specific dependency/permission preflight",
                            "host installation/binding and behavior",
                        ],
                        expert_id=expert_id,
                        resource_path="/".join(relative.parts[1:]),
                    )
                )
        if path.endswith("/SKILL.md"):
            meta, _body = parse_frontmatter(data.decode())
            skills.append(
                item(
                    "skill:" + path,
                    [ref],
                    ["O07"],
                    "extensions",
                    "N09",
                    imported=path in mappings,
                    remaining=[
                        "versioned install/share/bind",
                        "individual tools, dependencies and effects review",
                    ],
                    permissions=[
                        "skill.install/use",
                        "no tools automatically granted",
                        "execution PEP and isolation",
                    ],
                    metadata=meta,
                    development_only=path.startswith(".cursor/"),
                )
            )
        if (
            path.startswith(EXPERTS)
            and PurePosixPath(path).suffix in {".py", ".sh", ".js", ".ts"}
        ) or ("/scripts/" in path and path.startswith("src/octop/infra/agents/")):
            scripts.append(
                item(
                    "script:" + path,
                    [ref],
                    ["O07", "O26"],
                    "tools integration",
                    "N09",
                    imported=path in mappings,
                    permissions=[
                        "explicit tool schema",
                        "execution PEP",
                        "filesystem/network/secret scope",
                        "sandbox and cancellation",
                    ],
                    remaining=[
                        "per-script dependency and risk review",
                        "host tool wrapper",
                        "success/deny/cancel/fault tests",
                    ],
                    analysis=imports(data)
                    if path.endswith(".py")
                    else {"parse_status": "not executed"},
                )
            )
        if path.startswith(SUBAGENTS):
            parts = PurePosixPath(path[len(SUBAGENTS) :]).parts
            if len(parts) == 3 and parts[0] in catalogs and path.endswith(".md"):
                locale, division, filename = parts
                template_id = f"subagent:{division}.{PurePosixPath(filename).stem}"
                available = template_id in catalogs[locale]
                if available:
                    meta, body = parse_frontmatter(data.decode())
                    if (
                        get_template(template_id, locale)["system_prompt"]
                        != body.strip()
                    ):
                        raise ValueError(
                            "Subagent prompt host materialization mismatch"
                        )
                subagents.append(
                    item(
                        f"{template_id}:{locale}",
                        [ref],
                        ["O08", "O09"],
                        "agent resources",
                        "N09",
                        imported=True,
                        adapted=available,
                        remaining=[
                            "runtime member binding/delegation",
                            "shared pools, revoke and versions",
                        ]
                        + (
                            []
                            if available
                            else ["translation/metadata unavailable in current catalog"]
                        ),
                        locale=locale,
                        catalog_available=available,
                        template_id=template_id,
                    )
                )
        if path.startswith("dashboard/public/experts/avatars/") or path.startswith(
            "dashboard/public/assets/mbti/"
        ):
            persona.append(
                item(
                    "avatar:" + path,
                    [ref],
                    ["O06"],
                    "content experience",
                    "N06",
                    remaining=[
                        "byte-preserving asset import",
                        "locale/tenant-safe host avatar flow",
                    ],
                    permissions=["public static asset; no tool grants"],
                )
            )
        if path.endswith("/plugin.yaml"):
            meta = yaml.safe_load(data)
            if not isinstance(meta, dict) or not isinstance(meta.get("id"), str):
                raise ValueError("Invalid plugin manifest")
            folder = str(PurePosixPath(path).parent) + "/"
            plugins.append(
                item(
                    "plugin:" + path,
                    [ref],
                    ["O36", "O37"],
                    "extensions",
                    "N14",
                    remaining=[
                        "SDK/manifest compatibility",
                        "install/enable/reload/uninstall",
                        "tool/UI/hook permissions and isolation",
                        "upgrade rollback",
                    ],
                    permissions=[
                        "plugin.install by authorized admin",
                        "declared permissions need per-tool review",
                        "no Gateway execution on discovery",
                    ],
                    manifest=meta,
                    bundled=path.startswith("src/"),
                    files=["main:" + p for p in main_files if p.startswith(folder)],
                )
            )
        if (
            path.startswith("src/octop/api/routers/")
            and path.endswith(".py")
            and not path.endswith("/__init__.py")
        ):
            relative = path[len("src/octop/api/routers/") :]
            capabilities, role, task = group_router(relative)
            tree = ast.parse(data)
            prefix = ""
            for node in tree.body:
                if (
                    isinstance(node, ast.Assign)
                    and any(
                        isinstance(target, ast.Name) and target.id == "router"
                        for target in node.targets
                    )
                    and isinstance(node.value, ast.Call)
                ):
                    prefix = next(
                        (
                            literal(keyword.value)
                            for keyword in node.value.keywords
                            if keyword.arg == "prefix"
                        ),
                        "",
                    )
            for function in ast.walk(tree):
                if not isinstance(function, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                for decorator in function.decorator_list:
                    if (
                        isinstance(decorator, ast.Call)
                        and isinstance(decorator.func, ast.Attribute)
                        and decorator.func.attr
                        in {
                            "get",
                            "post",
                            "put",
                            "patch",
                            "delete",
                            "websocket",
                            "api_route",
                        }
                    ):
                        route = literal(decorator.args[0]) if decorator.args else None
                        endpoints.append(
                            item(
                                f"endpoint:{relative}:{function.name}:{decorator.lineno}",
                                [ref],
                                capabilities,
                                role,
                                task,
                                remaining=[
                                    "host API/identity mapping",
                                    "success/deny/recovery/fault acceptance",
                                ],
                                method=decorator.func.attr,
                                declared_router_prefix=prefix,
                                declared_path=route,
                                line=decorator.lineno,
                                path_scope="source declaration; deployed mount prefix not inferred",
                            )
                        )
    for entry in connector_entries(main_files[CATALOG]):
        refs = ["main:" + CATALOG]
        for path, data in main_files.items():
            if (
                path.startswith("src/octop/infra/connectors/")
                and path != CATALOG
                and path.endswith(".py")
                and any(
                    token in data.decode()
                    for token in (f'"{entry["kind"]}"', f"'{entry['kind']}'")
                )
            ):
                refs.append("main:" + path)
        connectors.append(
            item(
                "connector:" + entry["kind"],
                refs,
                ["O24", "O25"],
                "connectors and data",
                "N10",
                remaining=[
                    "tenant instance/ACL and scoped Secret",
                    "auth/refresh/revoke",
                    "host MCP/tool binding",
                    "individual provider acceptance",
                ],
                permissions=[
                    "connector.configure",
                    "connector.use",
                    "credential purpose/tenant/resource scope",
                    "per-tool read/write PEP",
                ],
                declaration=entry,
                implementation_reference_scope="static kind mentions only; not verified runtime availability",
            )
        )
    for profile in list_personas():
        persona.append(
            item(
                "persona:" + profile["code"],
                ["main:src/octop/infra/agents/persona/mbti_profiles.py"],
                ["O06"],
                "content experience",
                "N06",
                imported=True,
                adapted=True,
                evidence=["backend/tests/test_octop_integration.py"],
                remaining=["complete questionnaire/welcome/avatar user path"],
                permissions=["agent.create/edit; no tools granted"],
                profile=profile,
            )
        )
    for path in (
        "src/octop/api/routers/mbti.py",
        "dashboard/src/pages/Agent/Personalization/components/MBTITest.tsx",
    ):
        persona.append(
            item(
                "questionnaire:" + path,
                ["main:" + path],
                ["O06"],
                "content experience",
                "N06",
                remaining=[
                    "pure host scoring/questions",
                    "authenticated user path and reset/error handling",
                ],
                permissions=["agent.create/edit"],
            )
        )

    for package in externals["packages"]:
        source = package["artifacts"][0]
        role, task = EXTERNAL_ROLES[package["name"]]
        for path, data in sorted(artifact_members(ROOT / source["path"]).items()):
            ref = f"{package['name']}:{path}"
            source_index.append(
                {
                    "id": ref,
                    "origin": package["name"],
                    "path": path,
                    "archive": source["path"],
                    "sha256": digest(data),
                    "status": "archived",
                    "imported_target": None,
                    "integrity_verified": True,
                    "behavior_verified": False,
                    **(imports(data) if path.endswith(".py") else {}),
                }
            )
            if path.endswith("/SKILL.md"):
                meta, _body = parse_frontmatter(data.decode())
                skills.append(
                    item(
                        "skill:" + ref,
                        [ref],
                        ["O07"],
                        role,
                        "N09",
                        metadata=meta,
                        remaining=[
                            "per-resource license, dependencies, tools and side effects review",
                            "host installation/binding",
                        ],
                        permissions=[
                            "skill.install/use",
                            "execution PEP and isolation",
                        ],
                    )
                )
            if path.endswith((".py", ".sh")) and (
                "/scripts/" in path or "/skills/" in path
            ):
                scripts.append(
                    item(
                        "script:" + ref,
                        [ref],
                        ["O07", "O26"],
                        role,
                        task,
                        analysis=imports(data)
                        if path.endswith(".py")
                        else {"parse_status": "not executed"},
                        remaining=[
                            "individual dependencies/risk/schema/isolation review",
                            "host execution acceptance",
                        ],
                    )
                )
    excluded_resources = []
    excluded_records = [
        ("main", path, sha) for path, sha in baseline["excluded_source_files"].items()
    ]
    for package in externals["packages"]:
        source = package["artifacts"][0]
        excluded_records.extend(
            (package["name"], path, source["members"][path])
            for path in source["excluded_members"]
        )
    for origin, path, sha in excluded_records:
        ref = origin + ":" + path
        source_index.append(
            {
                "id": ref,
                "origin": origin,
                "path": path,
                "sha256": sha,
                "status": "excluded",
                "imported_target": None,
                "integrity_verified": False,
                "behavior_verified": False,
                "content_retained": False,
                "evidence_scope": "original member hash receipt; bytes not retained or executable",
            }
        )
        common = dict(
            archived=False,
            remaining=[
                "independent equivalent implementation",
                "host resource and tool behavior acceptance",
            ],
            permissions=[
                "same governed file/tool permissions",
                "no execution or installation from excluded content",
            ],
            source_excluded=True,
            source_sha256=sha,
            evidence=["explicit source policy and original member hash receipt"],
        )
        excluded_resources.append(
            item(
                "excluded-resource:" + ref,
                [ref],
                ["O05", "O07"],
                "resources integration",
                "N09",
                **common,
            )
        )
        if origin == "main":
            relative = PurePosixPath(path[len(EXPERTS) :])
            resources.append(
                item(
                    "resource:" + path,
                    [ref],
                    ["O05", "O07", "O08"],
                    "agent resources",
                    "N09",
                    expert_id=relative.parts[0],
                    resource_path="/".join(relative.parts[1:]),
                    **common,
                )
            )
        if path.endswith("/SKILL.md"):
            skills.append(
                item(
                    "skill:" + (path if origin == "main" else ref),
                    [ref],
                    ["O07"],
                    "extensions",
                    "N09",
                    metadata_scope="identifier and hash receipt only; original prompt not retained",
                    **common,
                )
            )
        if (
            origin == "main"
            and (
                (
                    path.startswith(EXPERTS)
                    and PurePosixPath(path).suffix in {".py", ".sh", ".js", ".ts"}
                )
                or ("/scripts/" in path and path.startswith("src/octop/infra/agents/"))
            )
        ) or (
            origin != "main"
            and path.endswith((".py", ".sh"))
            and ("/scripts/" in path or "/skills/" in path)
        ):
            scripts.append(
                item(
                    "script:" + (path if origin == "main" else ref),
                    [ref],
                    ["O07", "O26"],
                    "tools integration",
                    "N09",
                    analysis={"parse_status": "excluded; not executed or parsed"},
                    **common,
                )
            )
    for office in ("docx", "pdf", "pptx", "xlsx"):
        skills.append(
            item(
                "skill:office:" + office + "-independent-replacement",
                [],
                ["O05", "O07"],
                "extensions",
                "N09",
                remaining=[
                    "independent format implementation",
                    "create/read/edit/export user paths",
                    "authorization and fault acceptance",
                ],
                permissions=["same governed file/tool permissions"],
            )
        )
    restricted = externals["restricted_resource"]
    skills.append(
        item(
            "skill:octop-harness:powerpoint-independent-replacement",
            [],
            ["O07", "O05"],
            "extensions",
            "N09",
            remaining=[
                "independent equivalent implementation; restricted source excluded"
            ],
            permissions=["same governed office file/tool path"],
            restricted_source=restricted,
            archived_hash_receipt_only=True,
        )
    )
    ledger = json.loads((ROOT / OLD_LEDGER).read_text())
    if {entry["id"] for entry in ledger} != {
        f"O{number:02}" for number in range(1, 43)
    } or any(entry["full_parity"] for entry in ledger):
        raise ValueError("Original full capability scope mismatch")
    for entry in persona:
        if entry["dependencies"] == ["N06"]:
            entry["stages"]["imported"] = entry["stages"]["imported"] or any(
                ref.removeprefix("main:") in mappings for ref in entry["source_refs"]
            )
            entry["stages"]["adapted"] = True
            entry["stages"]["verified"] = True
            entry["status"] = "verified"
            entry["verification_evidence"] = [
                "backend/tests/test_octop_presentation.py",
                "frontend/src/components/workspace/agents/agent-presentation.test.tsx",
                "frontend/src/components/workspace/agents/agent-avatar.test.tsx",
                "docs/superpowers/evidence/2026-10-10-octop-n06-presentation/validation.json",
            ]
            entry["implementation_scope"] = (
                "bounded CustomAgent draft/persistence/chat welcome; no runtime/resource permissions granted"
            )
            entry["remaining"] = [
                "target deployment and complete O06 acceptance remain pending",
                "full O06 account and runtime behavior remains separately gated",
            ]

    groups = {
        "experts": experts,
        "expert_resources": resources,
        "excluded_resources": excluded_resources,
        "skills": skills,
        "scripts": scripts,
        "subagents": subagents,
        "personality": persona,
        "plugins": plugins,
        "connectors": connectors,
        "endpoints": endpoints,
    }
    entries = [entry for values in groups.values() for entry in values]
    identities = {entry["id"] for entry in entries}
    if len(identities) != len(entries):
        raise ValueError("Duplicate capability item identity")
    source_ids = {source["id"] for source in source_index}
    if any(ref not in source_ids for entry in entries for ref in entry["source_refs"]):
        raise ValueError("Inventory has an unresolved source reference")
    for capability in ledger:
        if capability["id"] == "O06":
            capability["status"] = (
                "partial: N06 CustomAgent questionnaire, 16 personas, welcome, 52 avatars and starter drafts locally verified"
            )
            capability["remaining"] = [
                "target deployment acceptance",
                "complete O06 behavior beyond the bounded CustomAgent path",
            ]
        capability["owner_role"] = "platform/product integration; role only"
        capability["permissions"] = [
            "tenant/actor/resource ACL",
            "each read/write tool uses platform governance",
        ]
        capability.setdefault(
            "remaining",
            [
                "all named subcapabilities and directory entries need behavior acceptance"
            ],
        )
        capability["children"] = sorted(
            entry["id"]
            for entry in entries
            if capability["id"] in entry["capabilities"]
        )
        capability["verification_rule"] = (
            "All explicit subcapabilities and directory entries require host success/deny/recovery/fault evidence; hashes are not behavior"
        )
    future = []
    for line in (ROOT / REVIEW).read_text().splitlines():
        if re.match(r"\| F\d{2} \|", line):
            cells = [cell.strip() for cell in line.strip("|").split("|")]
            future.append(
                {
                    "id": cells[0],
                    "official_direction_at_review": cells[1],
                    "code_release_evidence_at_review": cells[2],
                    "prismos_relationship": cells[3],
                    "delivery_mapping": cells[4],
                    "status": "remaining",
                    "full_parity": False,
                    "source": REVIEW,
                    "source_sha256": digest((ROOT / REVIEW).read_bytes()),
                    "state_basis": "prior fixed review; not a new live roadmap claim",
                    "owner_role": "platform/product integration; role only",
                    "permissions": ["same PrismOS tenant/resource/Action governance"],
                    "dependencies": ["N15", "corresponding original M2-M7 exit gates"],
                    "remaining": [
                        "published-source availability",
                        "individual host implementation and acceptance",
                    ],
                }
            )
    if {entry["id"] for entry in future} != {
        f"F{number:02}" for number in range(1, 13)
    } or len(future) != 12:
        raise ValueError("Future capability scope incomplete")
    counts = {name: len(values) for name, values in groups.items()}
    summary = {
        "schema_version": 1,
        "date": "2026-10-10",
        "revision": baseline["revision"],
        "release": baseline["release"],
        "main_source_files": len(baseline["source_files"]),
        "retained_main_source_files": len(main_files),
        "excluded_main_source_files": len(baseline["excluded_source_files"]),
        "retained_external_source_files": sum(
            source["origin"] != "main" and source["status"] != "excluded"
            for source in source_index
        ),
        "excluded_external_source_files": sum(
            source["origin"] != "main" and source["status"] == "excluded"
            for source in source_index
        ),
        "imported_files": len(mappings),
        "counts": counts,
        "current_catalog_counts": {
            locale: len(values) for locale, values in catalogs.items()
        },
        "current_capabilities": len(ledger),
        "future_capabilities": len(future),
        "runtime_permission_grants": False,
        "external_runtime_integration": False,
        "main_manifest_sha256": digest(
            (ROOT / "vendor/octop/manifest.json").read_bytes()
        ),
        "external_manifest_sha256": digest(
            (ROOT / "vendor/octop/external/manifest.json").read_bytes()
        ),
        "scope": "static source, dependency and content inventory; original full behavior scope remains pending",
    }
    families = {
        "octop_harness",
        "octop_memory",
        "octop_gateway",
        "octop_browser",
        "deepagents",
        "langgraph",
        "langchain_core",
        "langchain_mcp_adapters",
    }
    coupling = [
        {
            "source_ref": source["id"],
            "import": name,
            "family": name.split(".")[0],
            "verified_behavior": False,
            "required_host_review": "identity/facts/PEP/secrets/version/cancel interfaces",
        }
        for source in source_index
        for name in source.get("imports", [])
        if name.split(".")[0] in families
    ]
    return {
        "summary.json": summary,
        "source-index.json": source_index,
        "capability-items.json": groups,
        "capability-ledger.json": ledger,
        "future-ledger.json": future,
        "dependencies.json": dependency_inventory(externals, main_files),
        "coupling-edges.json": coupling,
        "excluded-resources.json": excluded_resources,
    }


def generate():
    values = build()
    OUTPUT.mkdir(parents=True, exist_ok=True)
    for name, value in values.items():
        (OUTPUT / name).write_text(
            json.dumps(value, indent=2, ensure_ascii=False) + "\n"
        )
    return values["summary.json"]


def verify():
    values = build()
    for name, value in values.items():
        if json.loads((OUTPUT / name).read_text()) != json.loads(
            json.dumps(value, ensure_ascii=False)
        ):
            raise ValueError(f"Inventory stale or modified: {name}")
    return {"verified": True, **values["summary.json"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("generate", "verify"))
    args = parser.parse_args()
    print(
        json.dumps(
            generate() if args.command == "generate" else verify(),
            ensure_ascii=False,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
