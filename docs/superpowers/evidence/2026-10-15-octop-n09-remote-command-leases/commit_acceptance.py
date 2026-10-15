from pathlib import Path
import hashlib,json,subprocess,sys
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
d=HERE.relative_to(ROOT).as_posix()
def run(*args):return subprocess.run(args,cwd=ROOT,check=True,capture_output=True).stdout
subprocess.run([sys.executable,str(HERE/'finalize_evidence.py')],cwd=ROOT,check=True)
run('git','add',d,'docs/superpowers/plans/2026-10-14-octop-functional-milestones.md')
logs=[p.relative_to(ROOT).as_posix() for p in (HERE/'logs').iterdir() if p.is_file()]
run('git','add','-f',*logs)
run('git','diff','--cached','--check')
v=json.loads((HERE/'validation.json').read_text())
for p,h in v['raw_log_sha256'].items():assert hashlib.sha256(run('git','show',':'+d+'/'+p)).hexdigest()==h,p
paths=run('git','diff','--cached','--name-only').decode().splitlines()
assert not any('__pycache__' in p or 'credential-assets' in p for p in paths),paths
print('Verified staged raw logs:',len(v['raw_log_sha256']),'files:',len(paths),flush=True)
print(run('git','commit','-m','feat: add scoped remote command leases and verified cancellation').decode(),flush=True)
for p,h in v['raw_log_sha256'].items():assert hashlib.sha256(run('git','show','HEAD:'+d+'/'+p)).hexdigest()==h,p
print('Committed raw log hashes verified',flush=True)
print(run('git','status','--short').decode())
