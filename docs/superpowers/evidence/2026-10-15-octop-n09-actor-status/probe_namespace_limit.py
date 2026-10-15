from pathlib import Path
import json,subprocess,uuid
HERE=Path(__file__).resolve().parent
image=subprocess.check_output(['docker','image','inspect','prismos-actor-status:test','--format','{{.Id}}'],text=True).strip()
name='prismos-actor-namespace-'+uuid.uuid4().hex[:12]
probe=subprocess.run(['docker','run','--rm','--network','none','--name',name,image,'bwrap','--unshare-user','--unshare-pid','--ro-bind','/','/','--proc','/proc','--','/bin/true'],capture_output=True,text=True)
assert probe.returncode!=0 and 'No permissions to create a new namespace' in probe.stderr,probe
assert subprocess.run(['docker','container','inspect',name],capture_output=True).returncode!=0
(HERE/'image-namespace-limit.json').write_text(json.dumps({'image':image,'returncode':probe.returncode,'stdout':probe.stdout,'stderr':probe.stderr,'default_privileges':True,'network':'none','owned_test_container_removed':True,'scope':'actual nested user/pid namespace launch under default Docker restrictions; production fails closed'},indent=2)+'\n')
print('Actual default-container nested namespace restriction confirmed; no privileges relaxed')
