"""Freeze frontend inputs and run its own full tests, strict build and traces."""
from pathlib import Path
import hashlib,json,subprocess,sys
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
base=json.loads((HERE.parent/'2026-10-15-octop-n09-remote-command-leases/inputs.json').read_text())
paths={p for p in base['sha256'] if p.startswith('frontend/')}
paths.update(['frontend/src/core/terminal-agent/assets-api.ts','frontend/src/core/terminal-agent/assets-api.test.ts','frontend/src/components/workspace/terminal/asset-dialogs.test.tsx'])
data={'base_commit':'f7aac71','sha256':{p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in sorted(paths)}}
target=HERE/'frontend-inputs.json'
if target.exists(): assert json.loads(target.read_text())==data
else: target.write_text(json.dumps(data,indent=2)+'\n')
def verify(): assert all(hashlib.sha256((ROOT/p).read_bytes()).hexdigest()==h for p,h in data['sha256'].items())
def run(name,args):
    subprocess.run([sys.executable,str(HERE/'run_validation.py'),name,'--',sys.executable,str(HERE/'frontend_command.py'),*args],cwd=ROOT,check=True)
verify()
run('frontend-full',['test:unit','--maxWorkers=1'])
run('frontend-build',['build'])
verify()
traces={}
for p in sorted((ROOT/'frontend/.next').rglob('*.nft.json')):
    value=json.loads(p.read_text())
    missing=[name for name in value['files'] if not (p.parent/name).exists()]
    traces[p.relative_to(ROOT/'frontend/.next').as_posix()]={'files':len(value['files']),'missing':missing,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
assert traces and not any(v['missing'] for v in traces.values())
(HERE/'frontend-build-proof.json').write_text(json.dumps({'complete':True,'returncode':0,'inputs_unchanged':True,'input_count':len(paths),'strict_typecheck_and_generated_routes':True,'build_id':(ROOT/'frontend/.next/BUILD_ID').read_text().strip(),'traces':traces},indent=2)+'\n')
print('Frontend full tests, strict build and complete traces accepted:',len(traces),flush=True)
