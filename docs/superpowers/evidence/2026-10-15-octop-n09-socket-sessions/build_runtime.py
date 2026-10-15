"""Frozen account-session delivery gates; retain original dependency and source baseline."""
from pathlib import Path
import hashlib,json,subprocess,sys,tempfile,uuid
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
BASE=HERE.parent/'2026-10-15-octop-n09-session-delivery'
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def run(name,args,cwd='root'):
    subprocess.run([sys.executable,str(HERE/'run_validation.py'),'--cwd',cwd,name,'--',*args],cwd=ROOT,check=True)
old=json.loads((BASE/'inputs.json').read_text())['sha256']
paths=set(old)|{'backend/app/services/terminal/socket_access.py','backend/tests/test_terminal_socket_sessions.py'}
inputs={'base_commit':'f76e3eb','scope':'all previous host inputs plus terminal connection current-session implementation/tests','sha256':{p:sha(ROOT/p) for p in sorted(paths)}}
target=HERE/'inputs.json'
if target.exists(): assert json.loads(target.read_text())==inputs
else: target.write_text(json.dumps(inputs,indent=2)+'\n')
assert all(inputs['sha256'][p]==h for p,h in old.items() if p.startswith('frontend/'))
def verify(): assert all(sha(ROOT/p)==h for p,h in inputs['sha256'].items())
for src,dest in [('postgres.json','postgres.json'),('pytest.log','postgres-runtime.log')]:
    (HERE/dest).write_bytes((Path('/tmp/prismos-socket-current-postgres-20261015')/src).read_bytes())
run('static',[sys.executable,str(HERE/'check_static.py')])
run('backend-image-build',['docker','build','-f',str(ROOT/'backend/Dockerfile'),'-t','prismos-socket-sessions:test',str(ROOT)])
image=subprocess.check_output(['docker','image','inspect','prismos-socket-sessions:test','--format','{{.Id}}'],text=True).strip()
files=['app/services/terminal/socket_access.py','app/services/terminal/session.py','app/agent/terminal_tools.py','app/gateway/routers/terminal.py','tests/test_terminal_socket_sessions.py','app/gateway/auth.py','app/gateway/routers/auth.py','app/gateway/session_authorization.py','tests/test_auth_session_delivery.py','tests/test_auth_middleware_status.py','app/integrations/actor_authorization.py','app/integrations/file_access.py','app/runtime_adapters.py','tests/test_file_access_http.py']
proof={'backend_image':image,'files':{},'default_privileges':True,'network':'none'}
container=subprocess.check_output(['docker','create',image],text=True).strip()
try:
    with tempfile.TemporaryDirectory(prefix='prismos-session-image-proof-') as directory:
        for i,p in enumerate(files):
            target=Path(directory)/str(i)
            subprocess.run(['docker','cp',container+':/app/backend/'+p,str(target)],check=True,capture_output=True)
            h=sha(target)
            assert h==sha(ROOT/'backend'/p),p
            proof['files']['backend/'+p]={'sha256':h,'matches':True}
finally: subprocess.run(['docker','rm',container],check=True,capture_output=True)
name='prismos-socket-runtime-'+uuid.uuid4().hex[:12]
try:
    run('image-runtime',['docker','run','--rm','--network','none','--memory','1g','--cpus','2','--pids-limit','256','--name',name,image,'sh','-c','cd /app/backend && .venv/bin/python -m pytest tests/test_terminal_socket_sessions.py tests/test_auth_session_delivery.py tests/test_terminal_access_boundaries.py tests/test_auth_middleware_status.py -q'])
finally:
    proof['owned_test_container_removed']=subprocess.run(['docker','container','inspect',name],capture_output=True).returncode!=0
    (HERE/'image-proof.json').write_text(json.dumps(proof,indent=2)+'\n')
verify()
print('Final session image accepted with current immutable host inputs',flush=True)
