#!/bin/bash
set -euo pipefail
root=/root/.codex/worktrees/octop-integration/prism-os
candidate=$(python3 -c 'import json; print(json.load(open("/tmp/prismos-n09e-candidate.json"))["root"])')
export PATH=/root/.nvm/versions/node/v24.11.1/bin:$PATH
export COREPACK_HOME=/tmp/prismos-octop-corepack
export NEXT_TELEMETRY_DISABLED=1
export NODE_OPTIONS=--max-old-space-size=1024
export RAYON_NUM_THREADS=1
cores=$(python3 -c 'import os; print(min(os.sched_getaffinity(0)))')
cd "$root/backend"
/root/.local/bin/uv run --locked pytest tests/ -q > /tmp/prismos-n09e-final/backend-full.log 2>&1
cd ../frontend
pnpm exec vitest run --maxWorkers=2 > /tmp/prismos-n09e-final/frontend-full.log 2>&1
cd "$root"
taskset -c "$cores" make octop-build UV=/tmp/prismos-n09b-uv-build-index PNPM=pnpm > /tmp/prismos-n09e-final/build-current.log 2>&1
cd "$candidate"
taskset -c "$cores" make octop-build UV=/tmp/prismos-n09b-uv-build-index PNPM=pnpm > /tmp/prismos-n09e-final/build-independent.log 2>&1
cd frontend
pnpm exec vitest run --maxWorkers=2 > /tmp/prismos-n09e-final/frontend-independent.log 2>&1
python3 - <<'PY'
from pathlib import Path
import re,json,hashlib
base=Path('/tmp/prismos-n09e-final')
for name in ['build-current.log','build-independent.log']:
 text=(base/name).read_text()
 assert '335 passed' in text and re.search(r'Tests\s+98 passed',text) and 'Compiled successfully' in text and 'scoped_receipt_pagination_and_retention' in text
for name in ['frontend-full.log','frontend-independent.log']:assert re.search(r'Tests\s+185 passed',(base/name).read_text())
assert '1664 passed, 18 skipped' in (base/'backend-full.log').read_text()
r=json.load(open('/tmp/prismos-n09e-candidate.json'))
assert all(hashlib.sha256((Path(r['root'])/p).read_bytes()).hexdigest()==sha for p,sha in r['code_sha256'].items())
(base/'build-exit.json').write_text(json.dumps({'current_build_exit':0,'independent_build_exit':0,'logs_verified':True,'code_inputs':len(r['code_sha256']),'candidate_hashes_verified':True,'logs_sha256':{name:hashlib.sha256((base/name).read_bytes()).hexdigest() for name in ['build-current.log','build-independent.log','backend-full.log','frontend-full.log','frontend-independent.log']}},indent=2)+'\n')
PY
