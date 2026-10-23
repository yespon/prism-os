from pathlib import Path
import hashlib,json,subprocess
r=Path('/root/.codex/worktrees/octop-integration/prism-os')
d='docs/superpowers/evidence/2026-10-15-octop-n09-auxiliary-resources'
def run(*a): return subprocess.run(a,cwd=r,check=True,stdout=subprocess.PIPE).stdout
run('git','add',d)
run('git','diff','--cached','--check')
v=json.loads((r/d/'validation.json').read_text())
for p,h in v['raw_log_sha256'].items():
    assert hashlib.sha256(run('git','show',':'+d+'/'+p)).hexdigest()==h,p
staged=run('git','diff','--cached','--name-only').decode().splitlines()
assert not any('__pycache__' in p or p.endswith('.pyc') for p in staged)
print('Verified staged raw logs:',len(v['raw_log_sha256']), 'files:',len(staged),flush=True)
print(run('git','commit','-m','feat: integrate auxiliary resources with current scoped access').decode(),flush=True)
for p,h in v['raw_log_sha256'].items():
    assert hashlib.sha256(run('git','show','HEAD:'+d+'/'+p)).hexdigest()==h,p
print('Committed raw log hashes verified',flush=True)
print(run('git','status','--short').decode())
