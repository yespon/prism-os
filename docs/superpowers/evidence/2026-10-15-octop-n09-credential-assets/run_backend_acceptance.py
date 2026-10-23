"""Actual backend/image gates, independently frozen from concurrent frontend work."""
from pathlib import Path
import hashlib,json,os,subprocess,sys,tempfile,uuid
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
RUNNER=str(HERE/'run_validation.py')
def run(name,args,cwd='root'):
    subprocess.run([sys.executable,RUNNER,'--cwd',cwd,name,'--',*args],cwd=ROOT,check=True)
def verify():
    data=json.loads((HERE/'backend-inputs.json').read_text())
    assert all(hashlib.sha256((ROOT/p).read_bytes()).hexdigest()==h for p,h in data['sha256'].items())
verify()
receipt={'complete':False,'pid':os.getpid(),'scope':'backend/runtime only; frontend separately frozen and accepted'}
(HERE/'backend-driver.json').write_text(json.dumps(receipt,indent=2)+'\n')
run('static-final',[sys.executable,str(HERE/'check_static.py')])
run('backend-image-build',['docker','build','-f',str(ROOT/'backend/Dockerfile'),'-t','prismos-credential-assets:test',str(ROOT)])
image=subprocess.check_output(['docker','image','inspect','prismos-credential-assets:test','--format','{{.Id}}'],text=True).strip()
run('service-image-build',['docker','build','-t','prismos-credential-provisioner:test',str(ROOT/'docker/provisioner')])
service=subprocess.check_output(['docker','image','inspect','prismos-credential-provisioner:test','--format','{{.Id}}'],text=True).strip()
files=['app/gateway/routers/assets.py','app/services/terminal/credential_access.py','app/services/terminal/session.py','scripts/rotate_encrypted_secrets.py','tests/test_credential_asset_access.py','tests/test_remote_scoped_commands.py','tests/test_provisioner_kubeconfig.py','packages/harness/deerflow/community/aio_sandbox/remote_command.py','packages/harness/deerflow/community/aio_sandbox/aio_sandbox_provider.py']
checks=[(image,'/app/backend/'+p,'backend/'+p) for p in files]+[(service,'/app/app.py','docker/provisioner/app.py'),(service,'/app/scoped_commands.py','docker/provisioner/scoped_commands.py'),(service,'/tmp/requirements.lock','docker/provisioner/requirements.lock')]
proof={'backend_image':image,'provisioner_image':service,'files':{},'default_privileges':True,'network':'none'}
with tempfile.TemporaryDirectory(prefix='prismos-credential-image-proof-') as temp:
    for i,(source,inside,host) in enumerate(checks):
        container=subprocess.check_output(['docker','create',source],text=True).strip()
        try:
            target=Path(temp)/str(i)
            subprocess.run(['docker','cp',container+':'+inside,str(target)],check=True,capture_output=True)
            actual=hashlib.sha256(target.read_bytes()).hexdigest()
            assert actual==hashlib.sha256((ROOT/host).read_bytes()).hexdigest(),host
            proof['files'][host]={'sha256':actual,'matches':True}
        finally: subprocess.run(['docker','rm',container],check=True,capture_output=True)
name='prismos-credential-runtime-'+uuid.uuid4().hex[:12]
try:
    run('image-runtime',['docker','run','--rm','--network','none','--memory','1g','--cpus','2','--pids-limit','256','--name',name,'--mount',f'type=bind,source={ROOT}/docker/provisioner,target=/app/docker/provisioner,readonly',image,'sh','-c','cd /app/backend && .venv/bin/python -m pytest tests/test_credential_asset_access.py tests/test_terminal_access_boundaries.py tests/test_terminal_security.py tests/test_terminal_multihost.py tests/test_remote_scoped_commands.py tests/test_provisioner_kubeconfig.py -q'])
finally:
    proof['owned_test_container_removed']=subprocess.run(['docker','container','inspect',name],capture_output=True).returncode!=0
    (HERE/'image-proof.json').write_text(json.dumps(proof,indent=2)+'\n')
assert proof['owned_test_container_removed']
run('service-image-http',[sys.executable,str(HERE/'verify_service_image.py'),service])
verify()
run('backend-full',['env','PRISMOS_SCOPED_TEST_IMAGE='+image,'.venv/bin/python','-m','pytest','tests/','-q'],'backend')
verify()
receipt.update(complete=True,returncode=0,backend_image=image,provisioner_image=service,backend_inputs_unchanged=True)
(HERE/'backend-driver.json').write_text(json.dumps(receipt,indent=2)+'\n')
print('Complete backend accepted within frozen backend/runtime scope; frontend gates separate',flush=True)
