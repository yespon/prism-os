"""Freeze current host inputs and prove unchanged frontend reuse."""
from pathlib import Path
import hashlib,json,subprocess

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
previous=ROOT/"docs/superpowers/evidence/2026-10-14-octop-n09-copy-share-access/inputs-accepted.json"
old=json.loads(previous.read_text())
paths=set(old["sha256"])
for name in subprocess.check_output(["git","ls-files","--others","--exclude-standard"],cwd=ROOT,text=True).splitlines():
    if name.startswith(("backend/","scripts/",".github/")):
        paths.add(name)
frontend={name:digest for name,digest in old["sha256"].items() if name.startswith("frontend/")}
changed_frontend=[name for name,digest in frontend.items() if hashlib.sha256((ROOT/name).read_bytes()).hexdigest()!=digest]
assert not changed_frontend,changed_frontend
hashes={name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in sorted(paths) if (ROOT/name).is_file()}
(HERE/"inputs.json").write_text(json.dumps({
    "base_commit":"0afa792","branch":"codex/octop-integration","sha256":hashes,
    "frontend_reuse":{"base_commit":"0afa792","matching_inputs":len(frontend),
        "scope":"full 258 tests plus six test-only type repair cases, strict production build, 50 complete traces; frontend unchanged",
        "sha256":frontend},
    "historical_migration_scope":old["historical_migration_scope"],
},indent=2)+"\n")
print("frozen host/source inputs",len(hashes),"unchanged frontend inputs",len(frontend))
