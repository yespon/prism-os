"""Freeze and build actual account-authority runtime; preserve every terminal result."""
from pathlib import Path
import hashlib,json,subprocess,sys,tempfile,uuid
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
BASE=HERE.parent/'2026-10-15-octop-n09-credential-assets'
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def run(name,args,cwd='root'):
    subprocess.run([sys.executable,str(HERE/'run_validation.py'),'--cwd',cwd,name,'--',*args],cwd=ROOT,check=True)
base=json.loads((BASE/'inputs.json').read_text())['sha256']
paths={p for p in base if not p.startswith('frontend/')}
paths.update(['backend/app/integrations/actor_authorization.py','backend/tests/native_auth_test_identity.py','backend/tests/test_runtime_actor_status.py','backend/tests/conftest.py'])
inputs={'base_commit':'c496fbe','scope':'backend/runtime and host validation contracts','sha256':{p:sha(ROOT/p) for p in sorted(paths)}}
target=HERE/'backend-inputs.json'
if target.exists(): assert json.loads(target.read_text())==inputs
else: target.write_text(json.dumps(inputs,indent=2)+'\n')
front=json.loads((BASE/'frontend-inputs.json').read_text())
assert all(sha(ROOT/p)==h for p,h in front['sha256'].items())
(HERE/'frontend-inputs.json').write_text(json.dumps(front,indent=2)+'\n')
for filename in ['postgres.json','pytest.log']:
    (HERE/('postgres-runtime.log' if filename=='pytest.log' else filename)).write_bytes((Path('/tmp/prismos-actor-status-postgres-20261015')/filename).read_bytes())
def verify():
    assert all(sha(ROOT/p)==h for p,h in inputs['sha256'].items())
verify()
run('backend-image-build',['docker','build','-f',str(ROOT/'backend/Dockerfile'),'-t','prismos-actor-status:test',str(ROOT)])
image=subprocess.check_output(['docker','image','inspect','prismos-actor-status:test','--format','{{.Id}}'],text=True).strip()
files=['app/integrations/actor_authorization.py','app/integrations/file_access.py','app/runtime_adapters.py','app/alerting/diagnosis_authorization.py','tests/native_auth_test_identity.py','tests/test_runtime_actor_status.py','tests/conftest.py','tests/test_langgraph_proxy.py','tests/test_diagnosis_authorization.py','tests/test_file_access_http.py']
proof={'backend_image':image,'files':{},'default_privileges':True,'network':'none'}
container=subprocess.check_output(['docker','create',image],text=True).strip()
try:
    with tempfile.TemporaryDirectory(prefix='prismos-actor-image-proof-') as directory:
        for i,p in enumerate(files):
            target=Path(directory)/str(i)
            subprocess.run(['docker','cp',container+':/app/backend/'+p,str(target)],check=True,capture_output=True)
            h=sha(target)
            assert h==sha(ROOT/'backend'/p),p
            proof['files']['backend/'+p]={'sha256':h,'matches':True}
finally: subprocess.run(['docker','rm',container],check=True,capture_output=True)
name='prismos-actor-runtime-'+uuid.uuid4().hex[:12]
try:
    run('image-runtime',['docker','run','--rm','--network','none','--memory','1g','--cpus','2','--pids-limit','256','--name',name,image,'sh','-c','cd /app/backend && .venv/bin/python -m pytest tests/test_runtime_actor_status.py tests/test_file_access_http.py tests/test_diagnosis_delivery.py tests/test_langgraph_proxy.py -q'])
finally:
    proof['owned_test_container_removed']=subprocess.run(['docker','container','inspect',name],capture_output=True).returncode!=0
    (HERE/'image-proof.json').write_text(json.dumps(proof,indent=2)+'\n')
verify()
print('Fixed image built and accepted; backend full and upgrade gates remain separate',flush=True)
