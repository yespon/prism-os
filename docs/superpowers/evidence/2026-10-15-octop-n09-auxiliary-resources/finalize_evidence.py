"""Verify final runtime receipts and exact historical reuse before block acceptance."""
from pathlib import Path
import ast,hashlib,json,re
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
def read(name): return json.loads((HERE/name).read_text())
def digest(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def stats(name):
    text=(HERE/"logs"/name).read_text()
    matches=re.findall(r"(\d+) passed(?:, (\d+) skipped)?(?:, (\d+) warnings)? in ",text)
    assert matches,name
    return {"passed":int(matches[-1][0]),"skipped":int(matches[-1][1] or 0)}
required=["backend-static-accepted","fixed-membership-regression","final-compatibility-regression","image-build-accepted","image-runtime-accepted","backend-full-accepted","upgrade-accepted","source","external","inventory"]
for name in required:
    d=read(name+"-result.json")
    assert d["complete"] and d["returncode"]==0,name
driver=read("accepted-driver.json")
assert driver["complete"] and driver["returncodes"]==[0,0] and driver["source_inputs_unchanged"]
inputs=read("inputs.json")
assert all(digest(ROOT/p)==h for p,h in inputs["sha256"].items())
initial=read("inputs-before-fixed-membership.json")
changes=[p for p,h in initial["sha256"].items() if inputs["sha256"].get(p)!=h]
allowed={".github/workflows/octop-integration.yml","scripts/octop_upgrade_probe.py","backend/tests/test_agent_skill_references.py","backend/tests/test_octop_integration.py","backend/tests/test_tenant_context_on_config_routers.py"}
assert set(changes)<=allowed,changes
pg=read("postgres.json")
assert pg["passed"] and pg["returncode"]==0 and pg["owned_container_removed"]
pg_tests=[ROOT/"backend"/name for name in pg["test_files"]]
closure=set()
while pg_tests:
    p=pg_tests.pop()
    name=p.relative_to(ROOT).as_posix()
    if name in closure: continue
    closure.add(name)
    tree=ast.parse(p.read_text())
    for node in ast.walk(tree):
        modules=[node.module] if isinstance(node,ast.ImportFrom) else [a.name for a in node.names] if isinstance(node,ast.Import) else []
        for module in modules:
            if module and (module.startswith("test_") or module=="resource_test_identity"):
                child=ROOT/"backend/tests"/(module.replace(".","/")+".py")
                if child.is_file(): pg_tests.append(child)
assert not set(changes)&closure,(changes,closure)
assert stats("postgres-runtime.log")["passed"]==120
image=read("image-proof-accepted.json")
runtime=read("accepted-runtime.json")
assert image["image_id"]==runtime["image_id"]==driver["image_id"]
assert image["test_container_removed"] and all(v["matches"] for v in image["files"].values())
assert len(image["files"])==23 and stats("image-runtime-accepted.log")["passed"]==122
for name in ["upgrade.json","upgrade-accepted.json"]:
    u=read(name)
    assert u["complete"] and u["host_changed"] is False
    assert len(u["versions"])==3 and all(v["returncode"]==0 for v in u["versions"])
assert all(digest(ROOT/p)==h for p,h in inputs["frontend_reuse"]["sha256"].items())
assert inputs["frontend_reuse"]["matching_inputs"]==501
validation={
    "base_commit":"0afa792","branch":"codex/octop-integration",
    "status":"auxiliary_resource_installation_current_access_and_local_image_scripts_accepted_milestone_one_pending",
    "backend":stats("backend-full-accepted.log")|{"returncode":0},
    "related":stats("related-current-runtime.log"),
    "fixed_membership":stats("fixed-membership-regression.log"),
    "compatibility":stats("final-compatibility-regression.log"),
    "postgres":{"passed":120,"returncode":0,"owned_container_removed":True,
        "reuse_scope":"selected original PostgreSQL tests and their test import closure plus all unchanged runtime adapters; final edits affect other fixtures and validation metadata only",
        "unchanged_test_dependency_files":sorted(closure)},
    "image":{"id":image["image_id"],"matching_inputs":23,"passed":122,"returncode":0,"default_privileges":True,"network":"none","owned_container_removed":True},
    "auxiliary":{"reference_groups":27,"scripts":4,"definitions":2,"total":33,
        "source_files_preserved":True,"actual_runtime_tests":"both original Local namespaces and configured AIO image, pinned image digest for final gates",
        "delegation_verified":False,"real_model_or_delivery_verified":False},
    "frontend_reuse":inputs["frontend_reuse"],
    "upgrade":{"complete":True,"host_changed":False,"final_image_id":runtime["image_id"],
        "initial_stages":[v["pytest"].splitlines()[-1] for v in read("upgrade.json")["versions"]],
        "final_stages":[v["pytest"].splitlines()[-1] for v in read("upgrade-accepted.json")["versions"]],
        "final_host_inputs":len(read("upgrade-accepted.json")["host_contract_sha256s"]),
        "scope":"broader resource/package stages retained; changed fixed membership/catalogue fixtures and runtime scenarios rerun under immutable accepted image"},
    "input_files":len(inputs["sha256"]),"final_changes_from_initial_freeze":changes,
    "boundaries":["M1 not exited","N04 real model/tool/ticket environment pending","N07 remote CI pending; no push",
        "remote/Apple full-tool runtime and generic Secret purposes remain","full expert behavior and actual delegation pending; N08 not started",
        "independent Office/external runtime and all original N/O/F/platform exits retained","no deployment/release"],
    "raw_log_sha256":{p.relative_to(HERE).as_posix():digest(p) for p in sorted((HERE/"logs").iterdir()) if p.is_file()},
}
(HERE/"validation.json").write_text(json.dumps(validation,indent=2)+"\n")
print(json.dumps({k:validation[k] for k in ["status","backend","postgres","image","input_files"]}))
