#!/bin/bash
set -euo pipefail
root=/root/.codex/worktrees/octop-integration/prism-os
candidate=$(python3 -c 'import json; print(json.load(open("/tmp/prismos-n09d-candidate.json"))["root"])')
export PATH=/root/.nvm/versions/node/v24.11.1/bin:$PATH
export COREPACK_HOME=/tmp/prismos-octop-corepack
export NEXT_TELEMETRY_DISABLED=1
export NODE_OPTIONS=--max-old-space-size=1024
export RAYON_NUM_THREADS=1
cores=$(python3 -c 'import os; print(min(os.sched_getaffinity(0)))')
cd "$root/backend"
/root/.local/bin/uv run --locked pytest tests/ -q > /tmp/prismos-n09d-final/backend-serial.log 2>&1
cd "$root/frontend"
pnpm exec vitest run --maxWorkers=2 > /tmp/prismos-n09d-final/frontend-serial.log 2>&1
cd "$root"
taskset -c "$cores" make octop-build UV=/tmp/prismos-n09b-uv-build-index PNPM=pnpm > /tmp/prismos-n09d-final/build-serial.log 2>&1
cd "$candidate"
python3 - <<'PY'
from pathlib import Path
import subprocess,json
route=Path('frontend/src/app/api/prismos-n09d-type-probe/route.ts')
route.parent.mkdir(parents=True,exist_ok=False)
route.write_text('export async function GET() { return 42; }\n')
try:
 r=subprocess.run(['pnpm','build'],cwd='frontend',capture_output=True,text=True)
 output=r.stdout+r.stderr
 Path('/tmp/prismos-n09d-final/negative-route.log').write_text(output)
 assert r.returncode != 0 and 'starting production compiler' not in output and 'prismos-n09d-type-probe' in output
 Path('/tmp/prismos-n09d-final/type-guard.json').write_text(json.dumps({'route_checked':True,'returncode':r.returncode,'compiler_started':False,'compiler_option':'default webpack'},indent=2)+'\n')
finally:
 route.unlink(missing_ok=True);route.parent.rmdir()
PY
cd frontend
pnpm exec next typegen > /tmp/prismos-n09d-final/negative-route-cleanup.log 2>&1
cd ..
taskset -c "$cores" make octop-build UV=/tmp/prismos-n09b-uv-build-index PNPM=pnpm > /tmp/prismos-n09d-final/independent-build.log 2>&1
cd frontend
pnpm exec vitest run --maxWorkers=2 > /tmp/prismos-n09d-final/independent-frontend-serial.log 2>&1
python3 - <<'PY'
from pathlib import Path
import hashlib,json
receipt=json.load(open('/tmp/prismos-n09d-candidate.json'))
root=Path(receipt['root'])
assert all(hashlib.sha256((root/p).read_bytes()).hexdigest()==digest for p,digest in receipt['code_sha256'].items())
Path('/tmp/prismos-n09d-final/serial-complete.json').write_text(json.dumps({'passed':True,'code_inputs':len(receipt['code_sha256']),'candidate_hashes_verified':True,'current_build_exit':0,'independent_build_exit':0,'compiler':'webpack','node_heap_mb':1024,'affinity_cpus':1},indent=2)+'\n')
PY
