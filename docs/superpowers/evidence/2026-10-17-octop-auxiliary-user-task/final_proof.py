"""Final owned native services, original stack and unchanged source boundaries."""
from pathlib import Path
import hashlib,json,stat,subprocess,sys
import httpx
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[3];sys.path.insert(0,str(ROOT/'scripts'))
from octop_wsl_native_env import STATE,NATIVE,process_identity
from live_common import stats
case=json.loads((HERE/'real-native-after-restart.json').read_text());assert case['complete'] and case['new_model_task_submissions']==0
processes=json.loads((NATIVE/'processes.json').read_text())
for name,item in processes.items():assert process_identity(item['pid'])=={k:item[k] for k in ['starttime','cmdline_sha256']},name
owned=json.loads((NATIVE/'ownership.json').read_text());assert hashlib.sha256((STATE/'compose.yaml').read_bytes()).hexdigest()==owned['main_compose_sha256']
with httpx.Client(trust_env=False,timeout=10) as c:
 assert c.get('http://127.0.0.1:18036/',follow_redirects=True).status_code==200
 assert c.get('http://127.0.0.1:18036/health').status_code==200
 assert c.get('http://127.0.0.1:18034/ok').status_code==200
 assert c.get('http://127.0.0.1:18026/',follow_redirects=True).status_code==200
 assert c.post('http://127.0.0.1:18036/api/langgraph/threads',json={}).status_code==401
for name in ['config.yaml','live-fixture.json','ownership.json','processes.json']:
 assert stat.S_IMODE((NATIVE/name).stat().st_mode)==0o600
 assert subprocess.run(['git','check-ignore','--quiet',str(NATIVE/name)]).returncode==0
assert stat.S_IMODE(NATIVE.stat().st_mode)==0o700
for name in ['gateway','langgraph']:
 info=json.loads(subprocess.check_output(['docker','inspect','prismos-n04-wsl-'+name+'-1'],text=True))[0]
 assert info['State']['Health']['Status']=='healthy' and not info['HostConfig']['Privileged']
 assert info['HostConfig']['SecurityOpt']==['no-new-privileges:true']
 assert all(m['Destination']!='/var/run/docker.sock' for m in info['Mounts'])
 assert 'PRISMOS_GOVERNED_TICKET_ACTION=off' in info['Config']['Env']
assert not subprocess.check_output(['git','diff','d52ff07','--name-only','--','backend/app','backend/packages','backend/uv.lock','backend/Dockerfile','frontend'],text=True).strip()
assert stats()['request_count']==26
proof={'complete':True,'M1_exited':False,'N08_started':False,'native_browser':'http://localhost:18036','process_identity_verified':list(processes),'main_compose_and_isolation_unchanged':True,'main_healthy':True,'receiver_count':26,'native_private_files_owner_only':True,'api_harness_production_and_frontend_inputs_unchanged_from':'d52ff07','new_model_task_submissions_during_recheck':0}
(HERE/'final-proof.json').write_text(json.dumps(proof,indent=2)+'\n')
print('Native profile identity/readiness and unchanged healthy main stack verified')
