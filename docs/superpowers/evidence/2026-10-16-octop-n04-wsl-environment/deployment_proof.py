from pathlib import Path
import hashlib,json,ssl,stat,subprocess,sys
import httpx
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
sys.path.insert(0,str(ROOT/'scripts'))
from octop_wsl_test_env import STATE,PROJECT,owned
owned()
containers=[json.loads(line) for line in subprocess.check_output(['docker','ps','-a','--filter','label=com.docker.compose.project='+PROJECT,'--format','json'],text=True).splitlines()]
proof={'project':PROJECT,'services':{},'secret_files_owner_only':True,'runtime_git_ignored':True,'persistent_for_user_setup':True,'real_model_verified':False,'M1_exited':False}
for c in containers:
 info=json.loads(subprocess.check_output(['docker','inspect',c['ID']],text=True))[0]
 service=info['Config']['Labels']['com.docker.compose.service']
 assert info['Config']['Labels']['com.docker.compose.project']==PROJECT
 assert all(m['Destination']!='/var/run/docker.sock' and not m['Source'].startswith('/root/.codex/auth') for m in info['Mounts'])
 for bindings in (info['HostConfig'].get('PortBindings') or {}).values():
  assert all(b['HostIp']=='127.0.0.1' for b in bindings)
 if service in ['gateway','langgraph','postgres']:assert info['State']['Health']['Status']=='healthy'
 if service=='db-init':assert info['State']['ExitCode']==0
 proof['services'][service]={'image':info['Image'],'running':info['State']['Running'],'health':info['State'].get('Health',{}).get('Status'),'no_docker_socket':True,'ports_loopback_only':True,'mounts':[{'target':m['Destination'],'read_only':not m['RW']} for m in info['Mounts']]}
for name in ['runtime.env','config.yaml','receiver/receiver-token','receiver/server.key']:
 p=STATE/name;assert stat.S_IMODE(p.stat().st_mode)==0o600
 assert subprocess.run(['git','check-ignore','--quiet',str(p)],cwd=ROOT).returncode==0
assert stat.S_IMODE(STATE.stat().st_mode)==0o700
receiver=STATE/'receiver'
with httpx.Client(verify=ssl.create_default_context(cafile=str(receiver/'server.crt')),trust_env=False,timeout=10) as client:
 response=client.get('https://127.0.0.1:18443/stats',headers={'Authorization':'Bearer '+(receiver/'receiver-token').read_text().strip()})
 assert response.status_code==200
 stats=response.json()
 before=json.loads((HERE/'receiver-runtime.json').read_text())
 assert stats['request_count']==before['requests_after']
 proof['receiver_counts_after_restart']=stats
 proof['receiver_count_survived_restart']=True
proof['public_certificate_sha256']=hashlib.sha256((receiver/'server.crt').read_bytes()).hexdigest()
proof['backend_lock_sha256']=hashlib.sha256((ROOT/'backend/uv.lock').read_bytes()).hexdigest()
(HERE/'deployment-proof.json').write_text(json.dumps(proof,indent=2)+'\n')
print(json.dumps({'services':list(proof['services']),'health_and_ownership':'passed','receiver_count_survived_restart':True,'runtime_secrets_ignored':True}))
