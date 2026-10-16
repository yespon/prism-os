import hashlib,json,stat,subprocess
from live_common import HERE,ROOT,STATE,stats
expected=json.loads((HERE.parent/'2026-10-16-octop-n04-live/runtime-image.json').read_text())['image']
proof={'M1_exited':False,'N08_started':False,'services':{},'secrets_owner_only':True}
for name in ['gateway','langgraph','postgres','frontend','nginx','ticket-receiver']:
 data=json.loads(subprocess.check_output(['docker','inspect','prismos-n04-wsl-'+name+'-1'],text=True))[0]
 assert data['Config']['Labels']['com.docker.compose.project']=='prismos-n04-wsl'
 assert data['State']['Running']
 if name in ['gateway','langgraph','postgres']:assert data['State']['Health']['Status']=='healthy'
 if name in ['gateway','langgraph']:
  assert data['Image']==expected
  env=dict(item.split('=',1) for item in data['Config']['Env'])
  assert env['PRISMOS_GOVERNED_TICKET_ACTION']=='off'
  assert env['PRISMOS_TRUSTED_GRAPH_CONTEXT']=='off'
  proof['services'][name]={'image':data['Image'],'action':'off','trusted_graph':'off','version':env['PRISMOS_GOVERNED_TICKET_POLICY_VERSION']}
 else:proof['services'][name]={'image':data['Image'],'running':True}
 assert all(m['Destination']!='/var/run/docker.sock' for m in data['Mounts'])
 for bindings in (data['HostConfig'].get('PortBindings') or {}).values():assert all(b['HostIp']=='127.0.0.1' for b in bindings)
assert proof['services']['gateway']['version']==proof['services']['langgraph']['version']
for source,target,container in [('docker/n04-test/ticket_receiver.py','/receiver.py','ticket-receiver'),('docker/nginx/nginx.conf','/etc/nginx/nginx.conf','nginx')]:
 actual=subprocess.check_output(['docker','exec','prismos-n04-wsl-'+container+'-1','sha256sum',target],text=True).split()[0]
 assert actual==hashlib.sha256((ROOT/source).read_bytes()).hexdigest()
 proof[source]={'sha256':actual,'deployed_bytes_match':True}
head=subprocess.check_output(['docker','exec','prismos-n04-wsl-postgres-1','psql','-U','prismos','-d','prismos','-Atc','SELECT version_num FROM alembic_version'],text=True).strip();assert head=='n8h9i0j1k2l3'
proof['migration_head']=head
for name in ['config.yaml','runtime.env','receiver/server.key','receiver/receiver-token','live-fixture.json']:
 assert stat.S_IMODE((STATE/name).stat().st_mode)==0o600
 assert subprocess.run(['git','check-ignore','--quiet',str(STATE/name)],cwd=ROOT).returncode==0
assert stat.S_IMODE(STATE.stat().st_mode)==0o700
proof['receiver']=stats();assert proof['receiver']['counter_version']==2
(HERE/'final-runtime.json').write_text(json.dumps(proof,indent=2)+'\n')
print('Current application/receiver/proxy bytes, healthy owned services, off flags, persistent counter and secret file boundaries verified')
