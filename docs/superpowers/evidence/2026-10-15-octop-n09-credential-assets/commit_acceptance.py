from pathlib import Path
import hashlib,json,subprocess,sys
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
d=HERE.relative_to(ROOT).as_posix()
def run(*a):return subprocess.run(a,cwd=ROOT,check=True,capture_output=True).stdout
for p in HERE.glob('*.py'):p.write_text(p.read_text().rstrip()+'\n')
run('git','add','-u')
run('git','add',d,'backend/app/services/terminal/credential_access.py','backend/tests/test_credential_asset_access.py','frontend/src/core/terminal-agent/assets-api.ts','frontend/src/core/terminal-agent/assets-api.test.ts','frontend/src/components/workspace/terminal/asset-dialogs.test.tsx')
logs=[p.relative_to(ROOT).as_posix() for p in (HERE/'logs').iterdir() if p.is_file()]
run('git','add','-f',*logs)
subprocess.run([sys.executable,str(HERE/'run_validation.py'),'brand-final','--',sys.executable,'scripts/check_brand_identity.py'],cwd=ROOT,check=True)
subprocess.run([sys.executable,str(HERE/'finalize_evidence.py')],cwd=ROOT,check=True)
run('git','add',d)
run('git','add','-f',d+'/logs/brand-final.log')
run('git','diff','--cached','--check')
v=json.loads((HERE/'validation.json').read_text())
for p,h in v['raw_log_sha256'].items():assert hashlib.sha256(run('git','show',':'+d+'/'+p)).hexdigest()==h,p
paths=run('git','diff','--cached','--name-only').decode().splitlines()
assert not any('__pycache__' in p or p.endswith('.pyc') for p in paths)
print('Verified staged raw logs:',len(v['raw_log_sha256']),'staged files:',len(paths),flush=True)
print(run('git','commit','-m','feat: secure asset credentials and current identity workflows').decode(),flush=True)
for p,h in v['raw_log_sha256'].items():assert hashlib.sha256(run('git','show','HEAD:'+d+'/'+p)).hexdigest()==h,p
print('Committed evidence hashes verified',flush=True)
print(run('git','status','--short').decode())
