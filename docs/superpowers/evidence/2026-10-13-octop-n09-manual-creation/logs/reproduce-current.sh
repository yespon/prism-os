#!/bin/bash
set -euo pipefail
root=/root/.codex/worktrees/octop-integration/prism-os
export PATH=/root/.nvm/versions/node/v24.11.1/bin:$PATH
export COREPACK_HOME=/tmp/prismos-octop-corepack
export NEXT_TELEMETRY_DISABLED=1
export NODE_OPTIONS=--max-old-space-size=1024
export RAYON_NUM_THREADS=1
cores=$(python3 -c 'import os;print(min(os.sched_getaffinity(0)))')
cd "$root/backend"
/root/.local/bin/uv run --locked pytest tests/ -q > /tmp/prismos-n09i-final/backend-full.log 2>&1
cd "$root"
taskset -c "$cores" make octop-build UV=/tmp/prismos-n09b-uv-build-index PNPM=pnpm > /tmp/prismos-n09i-final/build-current.log 2>&1
python3 - <<'PY'
from pathlib import Path
import re,json,hashlib
base=Path('/tmp/prismos-n09i-final');root=Path('/root/.codex/worktrees/octop-integration/prism-os')
assert '1723 passed, 18 skipped' in (base/'backend-full.log').read_text()
assert re.search(r'Tests\s+227 passed',(base/'frontend-full.log').read_text())
s=(base/'build-current.log').read_text();assert '394 passed' in s and re.search(r'Tests\s+140 passed',s) and 'Compiled successfully' in s and 'manual_creation_owned_publication_configuration_and_explicit_enablement' in s
r=json.load(open('/tmp/prismos-n09i-candidate.json'));assert all(hashlib.sha256((root/p).read_bytes()).hexdigest()==sha for p,sha in r['code_sha256'].items())
(base/'current-exit.json').write_text(json.dumps({'current_build_exit':0,'full_tests_exit':0,'logs_verified':True,'code_hashes_verified':True,'logs_sha256':{name:hashlib.sha256((base/name).read_bytes()).hexdigest() for name in ['backend-full.log','frontend-full.log','build-current.log']}},indent=2)+'\n')
PY
