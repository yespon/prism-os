"""Validate final receipts, unchanged inputs, production traces, and raw evidence."""
from pathlib import Path
import hashlib
import gzip
import json
import re

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
def read(name):
    return json.loads((HERE / name).read_text())
def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()
def text(name):
    return re.sub(r"\x1b\[[0-9;]*m", "", (HERE / "logs" / name).read_text())

receipts = [
    "backend-static-accepted", "frontend-uncertainty-related",
    "frontend-lint-accepted", "frontend-full-serial", "frontend-api-type-delta",
    "frontend-production-recheck", "upgrade-accepted", "image-runtime",
]
for name in receipts:
    d = read(name + "-result.json")
    assert d["complete"] and d["returncode"] == 0, name
inputs = read("inputs-accepted.json")
changed = [p for p, expected in inputs["sha256"].items() if digest(ROOT / p) != expected]
assert not changed, changed
backend = text("backend-full.log")
assert re.search(r"2005 passed, 18 skipped, 417 warnings in ", backend)
assert re.search(r"258 passed", text("frontend-full-serial.log"))
postgres = read("postgres.json")
assert postgres["passed"] and postgres["returncode"] == 0 and postgres["owned_container_removed"]
assert "92 passed" in text("postgres.log")
image = read("image-proof.json")
assert image["test_container_removed"] and all(v["matches"] for v in image["files"].values())
assert "92 passed" in text("image-runtime.log")
for name in ("upgrade.json", "upgrade-accepted.json"):
    d = read(name)
    assert d["complete"] and d["host_changed"] is False
    assert len(d["versions"]) == 3 and all(v["returncode"] == 0 for v in d["versions"])
traces = []
for path in sorted((ROOT / "frontend/.next").rglob("*.nft.json")):
    record = json.loads(path.read_text())
    missing = [p for p in record["files"] if not (path.parent / p).exists()]
    assert not missing, (str(path), missing)
    traces.append({"path": str(path.relative_to(ROOT)), "sha256": digest(path), "file_count": len(record["files"])})
assert len(traces) >= 50, len(traces)
(HERE / "frontend-build-traces.json").write_text(json.dumps({
    "build_id": (ROOT / "frontend/.next/BUILD_ID").read_text().strip(),
    "trace_count": len(traces), "missing_references": [], "traces": traces,
}, indent=2) + "\n")
source = json.loads(text("source-verify.log"))
external = json.loads(text("external-verify.log"))
inventory = json.loads(text("inventory-verify.log"))
assert source["verified"] and source["imported_files"] == 902
assert external["verified"] and external["packages"] == 4 and external["retained_artifacts"] == 7
assert inventory["verified"] and inventory["current_capabilities"] == 42 and inventory["future_capabilities"] == 12
assert "brand gate passed" in text("brand-verify.log")
archives = read("compressed-log-archives.json")["archives"]
for a in archives:
    assert digest(HERE / a["archive"]) == a["archive_sha256"]
    assert hashlib.sha256(gzip.decompress((HERE / a["archive"]).read_bytes())).hexdigest() == a["raw_sha256"]
archived_raw = {a["original"] for a in archives}
validation = {
    "compressed_log_archives": archives,
    "source_gates": {"raw_imported_members": 902, "external_packages": 4, "external_artifacts": 7, "current_capabilities": 42, "future_capabilities": 12, "brand_allowances": 526},
    "base_commit": "38073b1", "branch": "codex/octop-integration",
    "status": "copy_share_configuration_and_current_target_authority_accepted_milestone_one_pending",
    "backend": {"passed": 2005, "skipped": 18, "warnings": 417,
        "evidence": "actual final pytest summary; initial Windows/WSL wrapper did not preserve pytest exit code"},
    "related_backend": {"passed": 149, "warnings": 109},
    "postgres": {"passed": 92, "returncode": 0, "owned_container_removed": True},
    "image": {"id": image["image_id"], "matching_inputs": len(image["files"]), "passed": 92, "returncode": 0,
        "default_privileges": True, "network": "none", "owned_container_removed": True},
    "frontend": {"passed": 258, "files": 58, "returncode": 0, "production_returncode": 0,
        "coverage": "full serial 258 passed; test-only required-field repair then 6 API tests rerun; 252 unchanged tests reused",
        "trace_count": len(traces), "failed_intermediate": "original UI timing failures retained; both affected files passed isolated, full single-worker run passed with original 5s timeout"},
    "upgrade": {"retained_full_changed_block": "86 tests per b5/b6/b5 stage before final UI uncertainty patch",
        "final_host_inputs": len(read("upgrade-accepted.json")["host_contract_sha256s"]),
        "final_stages": [v["pytest"].splitlines()[-1] for v in read("upgrade-accepted.json")["versions"]],
        "complete": True, "host_changed": False, "returncodes": [0, 0, 0],
        "frontend_runtime_scope": "source switch exercises backend copy contracts; final frontend behavior separately tested, fixed frontend bytes checked"},
    "input_files_checked_unchanged": len(inputs["sha256"]),
    "boundaries": ["M1 not exited", "N04 real model/tool/ticket configuration absent",
        "N07 remote CI pending; no push", "remote/Apple all-tool integration and real SSH pending",
        "remaining non-Skill/expert/Office/external runtime and original PrismOS gates remain",
        "N08 execution/delegation not started", "no push/deployment/release"],
    "raw_log_sha256": {str(p.relative_to(HERE)): digest(p) for p in sorted((HERE / "logs").iterdir()) if p.is_file() and str(p.relative_to(HERE)) not in archived_raw},
}
(HERE / "validation.json").write_text(json.dumps(validation, indent=2) + "\n")
print(json.dumps({k: validation[k] for k in ("status", "input_files_checked_unchanged", "postgres", "image", "frontend")}))
