"""Run immutable image and complete integration gates for remote command leases."""
from pathlib import Path
import hashlib,json,subprocess,sys,tempfile,uuid
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
RUNNER=str(HERE/'run_validation.py')
def run(name,cwd,args):
    name = name + '-final'
    subprocess.run([sys.executable,RUNNER,'--cwd',cwd,name,'--',*args],cwd=ROOT,check=True)
def verify():
    data=json.loads((HERE/'inputs.json').read_text())
    assert all(hashlib.sha256((ROOT/p).read_bytes()).hexdigest()==h for p,h in data['sha256'].items())
verify()
run('static','root',[sys.executable,str(HERE/'check_static.py')])
run('backend-image-build','root',['docker','build','-f',str(ROOT/'backend/Dockerfile'),'-t','prismos-remote-command:test',str(ROOT)])
image=subprocess.check_output(['docker','image','inspect','prismos-remote-command:test','--format','{{.Id}}'],text=True).strip()
run('provisioner-image-build','root',['docker','build','-t','prismos-command-provisioner:test',str(ROOT/'docker/provisioner')])
service=subprocess.check_output(['docker','image','inspect','prismos-command-provisioner:test','--format','{{.Id}}'],text=True).strip()
proof={'backend_image':image,'provisioner_image':service,'files':{},'default_privileges':True,'network':'none'}
checks=[(image,'/app/backend/packages/harness/deerflow/community/aio_sandbox/remote_command.py','backend/packages/harness/deerflow/community/aio_sandbox/remote_command.py'),(image,'/app/backend/packages/harness/deerflow/community/aio_sandbox/aio_sandbox_provider.py','backend/packages/harness/deerflow/community/aio_sandbox/aio_sandbox_provider.py'),(image,'/app/backend/packages/harness/deerflow/config/sandbox_config.py','backend/packages/harness/deerflow/config/sandbox_config.py'),(image,'/app/backend/tests/test_remote_scoped_commands.py','backend/tests/test_remote_scoped_commands.py'),(image,'/app/backend/tests/test_provisioner_kubeconfig.py','backend/tests/test_provisioner_kubeconfig.py'),(service,'/tmp/requirements.lock','docker/provisioner/requirements.lock'),(service,'/app/app.py','docker/provisioner/app.py'),(service,'/app/scoped_commands.py','docker/provisioner/scoped_commands.py')]
with tempfile.TemporaryDirectory(prefix='prismos-remote-image-proof-') as tmp:
    for i,(source,path,hostpath) in enumerate(checks):
        container=subprocess.check_output(['docker','create',source],text=True).strip()
        try:
            target=Path(tmp)/str(i)
            subprocess.run(['docker','cp',container+':'+path,str(target)],check=True,capture_output=True)
            actual=hashlib.sha256(target.read_bytes()).hexdigest()
            expected=hashlib.sha256((ROOT/hostpath).read_bytes()).hexdigest()
            assert actual==expected,hostpath
            proof['files'][hostpath]={'sha256':actual,'matches':True}
        finally:
            subprocess.run(['docker','rm',container],check=True,capture_output=True)
name='prismos-remote-protocol-'+uuid.uuid4().hex[:12]
try:
    run('image-protocol','root',['docker','run','--rm','--network','none','--memory','1g','--cpus','2','--pids-limit','256','--name',name,'--mount',f'type=bind,source={ROOT}/docker/provisioner,target=/app/docker/provisioner,readonly',image,'sh','-c','cd /app/backend && .venv/bin/python -m pytest tests/test_remote_scoped_commands.py tests/test_provisioner_kubeconfig.py tests/test_aio_sandbox_isolation.py tests/test_runtime_adapters.py -q'])
finally:
    proof['owned_test_container_removed']=subprocess.run(['docker','container','inspect',name],capture_output=True).returncode!=0
run('service-image-http','root',[sys.executable,str(HERE/'verify_service_image.py'),service])
(HERE/'image-proof-final.json').write_text(json.dumps(proof,indent=2)+'\n')
assert proof['owned_test_container_removed']
verify()
full=[sys.executable,RUNNER,'--cwd','backend','backend-full-final','--','env','PRISMOS_SCOPED_TEST_IMAGE='+image,'.venv/bin/python','-m','pytest','tests/','-q']
upgrade=[sys.executable,RUNNER,'upgrade-final','--','env','PRISMOS_SCOPED_TEST_IMAGE='+image,sys.executable,str(ROOT/'scripts/octop_upgrade_probe.py'),'--previous-archive','/tmp/prismos-copy-share-upgrade/previous/upstream.tar.gz','--previous-receipt','/tmp/prismos-copy-share-upgrade/previous/manifest.json','--previous-revision','e473dd3c4a4741618ffde1a42a3492341a189e8e','--previous-release','0.3.0b5','--output',str(HERE/'upgrade-final.json'),'--test-file','tests/test_remote_scoped_commands.py','--test-file','tests/test_provisioner_kubeconfig.py','--test-file','tests/test_aio_sandbox_isolation.py','--test-file','tests/test_runtime_adapters.py']
processes=[subprocess.Popen(args,cwd=ROOT) for args in [full,upgrade]]
codes=[p.wait() for p in processes]
verify()
(HERE/'acceptance-driver-final.json').write_text(json.dumps({'complete':True,'returncodes':codes,'source_inputs_unchanged':True,'backend_image':image,'provisioner_image':service},indent=2)+'\n')
if any(codes): raise SystemExit(1)
print('Full backend, images and affected upgrade/rollback passed; real cluster remains pending',flush=True)
