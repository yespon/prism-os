import ast
from pathlib import Path

PLATFORM_ROOT = Path("app/platform")
FORBIDDEN_PREFIXES = (
    "app.alerting",
    "app.agent",
    "app.services.terminal",
    "langgraph",
)


def test_platform_core_does_not_import_domain_or_runtime_private_modules() -> None:
    violations: list[str] = []
    for path in PLATFORM_ROOT.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            names: list[str] = []
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            for name in names:
                if name.startswith(FORBIDDEN_PREFIXES):
                    violations.append(f"{path}:{node.lineno}:{name}")
    assert violations == []
