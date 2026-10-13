#!/bin/bash
set -euo pipefail
candidate=$(python3 -c 'import json;print(json.load(open("/tmp/prismos-n09h-candidate.json"))["root"])')
export PATH=/root/.nvm/versions/node/v24.11.1/bin:$PATH
export COREPACK_HOME=/tmp/prismos-octop-corepack
export NEXT_TELEMETRY_DISABLED=1
export NODE_OPTIONS=--max-old-space-size=1024
export RAYON_NUM_THREADS=1
cores=$(python3 -c 'import os;print(min(os.sched_getaffinity(0)))')
cd "$candidate"
taskset -c "$cores" make octop-build UV=/tmp/prismos-n09b-uv-build-index PNPM=pnpm > /tmp/prismos-n09h-final/build-independent.log 2>&1
cd frontend
pnpm exec vitest run --maxWorkers=2 > /tmp/prismos-n09h-final/frontend-independent.log 2>&1
python3 - <<'PY'
from pathlib import Path
import re,json,hashlib
base=Path('/tmp/prismos-n09h-final');r=json.load(open('/tmp/prismos-n09h-candidate.json'))
assert re.search(r'Tests\s+212 passed',(base/'frontend-independent.log').read_text())
s=(base/'build-independent.log').read_text();assert '377 passed' in s and re.search(r'Tests\s+125 passed',s) and 'Compiled successfully' in s and 'concrete_enablement_and_current_membership' in s
assert all(hashlib.sha256((Path(r['root'])/p).read_bytes()).hexdigest()==sha for p,sha in r['code_sha256'].items())
current=json.load(open(base/'current-exit.json'));assert current['current_build_exit']==0 and current['logs_verified']
sha={name:hashlib.sha256((base/name).read_bytes()).hexdigest() for name in ['backend-full.log','frontend-full.log','build-current.log','build-independent.log','frontend-independent.log']}
for name,value in current['logs_sha256'].items():assert sha[name]==value
(base/'build-exit.json').write_text(json.dumps({'current_build_exit':0,'independent_build_exit':0,'logs_verified':True,'candidate_hashes_verified':True,'code_inputs':len(r['code_sha256']),'logs_sha256':sha},indent=2)+'\n')
PY
