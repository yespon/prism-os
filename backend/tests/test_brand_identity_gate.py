import importlib.util
import sys
from pathlib import Path


SCRIPT = Path(__file__).parents[2] / "scripts" / "check_brand_identity.py"
SPEC = importlib.util.spec_from_file_location("brand_gate", SCRIPT)
assert SPEC and SPEC.loader
brand_gate = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = brand_gate
SPEC.loader.exec_module(brand_gate)


def test_unlisted_legacy_match_fails(tmp_path: Path) -> None:
    source = tmp_path / "ui.ts"
    source.write_text('const key = "opsintech.old";\n', encoding="utf-8")
    matches = brand_gate.scan_paths(tmp_path, ["ui.ts"])
    errors = brand_gate.validate_matches(matches, {"entries": []}, repo_root=tmp_path)
    assert errors == ["ui.ts:1: unallowlisted legacy token: opsintech"]


def test_exact_allowlist_enforces_match_ceiling(tmp_path: Path) -> None:
    source = tmp_path / "legacy.py"
    source.write_text('OLD = "OPSINTECH_HOME"\n', encoding="utf-8")
    allowlist = {
        "entries": [{
            "path": "legacy.py",
            "classification": "compatibility-code",
            "reason": "Reads the 0.2.x deployment input",
            "owner": "runtime-config",
            "remove_by": "0.3.0",
            "max_matches": 1,
        }]
    }
    assert brand_gate.validate_matches(
        brand_gate.scan_paths(tmp_path, ["legacy.py"]), allowlist, repo_root=tmp_path
    ) == []
    source.write_text('A = "OPSINTECH_HOME"\nB = ".opsintech"\n', encoding="utf-8")
    errors = brand_gate.validate_matches(
        brand_gate.scan_paths(tmp_path, ["legacy.py"]), allowlist, repo_root=tmp_path
    )
    assert errors == ["legacy.py: legacy matches 2 exceed allowed maximum 1"]


def test_allowlist_rejects_wildcards_and_missing_metadata() -> None:
    errors = brand_gate.validate_allowlist({"entries": [{"path": "docs/**"}]})
    assert "allowlist entry 1 path must be exact" in errors
    assert "allowlist entry 1 missing classification" in errors


def test_historical_file_requires_banner(tmp_path: Path) -> None:
    source = tmp_path / "history.md"
    source.write_text("OpsinTech release notes\n", encoding="utf-8")
    allowlist = {"entries": [{
        "path": "history.md",
        "classification": "historical-document",
        "reason": "Preserves release history",
        "owner": "documentation",
        "remove_by": "never-historical",
        "max_matches": 1,
    }]}
    errors = brand_gate.validate_matches(
        brand_gate.scan_paths(tmp_path, ["history.md"]), allowlist, repo_root=tmp_path
    )
    assert errors == ["history.md: historical document is missing 'Legacy / Historical' banner"]


def test_historical_banner_may_be_below_title(tmp_path: Path) -> None:
    source = tmp_path / "history.md"
    source.write_text(
        "# Old release\n\n> **Legacy / Historical:** superseded\n\nOpsinTech notes\n",
        encoding="utf-8",
    )
    allowlist = {"entries": [{
        "path": "history.md",
        "classification": "historical-document",
        "reason": "Preserves release history",
        "owner": "documentation",
        "remove_by": "never-historical",
        "max_matches": 1,
    }]}
    assert brand_gate.validate_matches(
        brand_gate.scan_paths(tmp_path, ["history.md"]), allowlist, repo_root=tmp_path
    ) == []
