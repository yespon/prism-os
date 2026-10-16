"""Launch only owned snapshot clones; preserve the current stack and its databases."""
from pathlib import Path
import argparse,copy,hashlib,json,secrets,shutil,subprocess,sys
import yaml
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[3];sys.path.insert(0,str(ROOT/'scripts'))
import octop_wsl_test_snapshot as snapshot
parser=argparse.ArgumentParser();parser.add_argument('--case',default='restored-stack');parser.add_argument('--reuse-prepare');args=parser.parse_args();assert args.case.replace('-','').isalnum()
path=HERE/(args.case+'.json');assert not path.exists()
if args.reuse_prepare:
 assert args.reuse_prepare.replace('-','').isalnum()
 previous=json.loads((HERE/(args.reuse_prepare+'.json')).read_text())
 assert previous['phases'][0]['phase']=='prepare' and previous['phases'][0]['complete']
snapshot.assert_owned_services()
from live_common import stats as original_stats
original_count=original_stats()['request_count'];original_compose_sha=hashlib.sha256((snapshot.STATE/'compose.yaml').read_bytes()).hexdigest()
fixture=json.loads((snapshot.STATE/'live-fixture.json').read_text())
source=ROOT/'backend/tmp/n04-deployment-snapshot-20261016';snapshot.safe_directory(source,existing=True)
manifest=json.loads((source/'manifest.json').read_text());assert manifest['complete']
for table in manifest['databases']['prismos']['tables']:
 if 'rule' in table['table'] or 'schedul' in table['table']:assert table['rows']==0,'Restored background automation requires separate review'
reference=json.loads((HERE.parent/'2026-10-16-octop-n04-deployment-lifecycle/snapshot-restore-verify.json').read_text())
verified=Path(reference['private_restored_files']);assert verified.is_relative_to(source) and snapshot.tree_manifest(verified)==manifest['runtime_files']
suffix=secrets.token_hex(5);project='prismos-n04-restored-'+suffix
work=ROOT/'backend/tmp'/project;work.mkdir(mode=0o700)
snapshot.private_write(work/'owner',b'prismos-owned-n04-restored-service-v1\n')
runtime=work/'runtime';shutil.copytree(verified,runtime);assert snapshot.tree_manifest(runtime)==manifest['runtime_files']
# Receipt path was reserved before allocating any restored resources.
receipt={'complete':False,'M1_exited':False,'N08_started':False,'project':project,'private_runtime':str(work),'phases':[],'original_receiver_before':original_count};clones={};connected=False;network_created=False;services_started=False
compose_path=work/'compose.yaml'

def command(args):
 return subprocess.run(args,cwd=ROOT,capture_output=True,check=True).stdout

def compose(args):
 return command(['docker','compose','-p',project,'--env-file',str(runtime/'runtime.env'),'-f',str(compose_path),*args])

def store(phase):
 receipt['phase']=phase;path.write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps({'phase':phase,'project':project}),flush=True)

def probe(script,extra=None):
 payload={'fixture':fixture,'old_case':json.loads((HERE.parent/'2026-10-16-octop-n04-live/allow-counter-v2.json').read_text()),'old_skill':json.loads((HERE.parent/'2026-10-16-octop-n04-skill-storage/live-skill-read.json').read_text()),'receiver_token':(runtime/'receiver/receiver-token').read_text().strip(),'reuse_prepare':args.reuse_prepare,**(extra or {})}
 result=subprocess.run(['docker','exec','-i','-w','/app/backend',project+'-gateway-1','uv','run','--frozen','python','-c',(HERE/script).read_text()],input=json.dumps(payload).encode(),capture_output=True)
 private=work/(script+'.diagnostic');private.write_bytes(result.stdout+result.stderr);private.chmod(0o600)
 assert result.returncode==0,('Restored native probe failed',script,result.returncode)
 return json.loads(result.stdout.decode().splitlines()[-1])
try:
 for database in snapshot.DATABASES:
  clone='prismos_restore_'+suffix+'_'+str(len(clones));snapshot.execute('postgres',['createdb','-U','prismos',clone]);clones[database]=clone
  snapshot.execute('postgres',['pg_restore','-U','prismos','-d',clone],(source/(database+'.dump')).read_bytes())
  assert snapshot.database_manifest(clone)==manifest['databases'][database]['tables']
 config=yaml.safe_load((runtime/'config.yaml').read_text());snapshot.validate_database_scope(config)
 from sqlalchemy.engine import make_url
 config['database']['url']=make_url(config['database']['url']).set(database=clones['prismos']).render_as_string(hide_password=False)
 config['database']['auth']['url']=make_url(config['database']['auth']['url']).set(database=clones['prismos_auth_db']).render_as_string(hide_password=False)
 config['checkpointer']['connection_string']=make_url(config['checkpointer']['connection_string']).set(database=clones['prismos_checkpoints']).render_as_string(hide_password=False)
 snapshot.private_write(work/'config.yaml',yaml.safe_dump(config).encode())
 base=yaml.safe_load((runtime/'compose.yaml').read_text());assert base['name']=='prismos-n04-wsl'
 services={}
 for name in ['gateway','langgraph','frontend','nginx','ticket-receiver']:
  service=copy.deepcopy(base['services'][name]);service.pop('ports',None);service.pop('depends_on',None);service['networks']=['restored']
  info=json.loads(command(['docker','inspect','prismos-n04-wsl-'+name+'-1']))[0];assert info['Config']['Labels']['com.docker.compose.project']=='prismos-n04-wsl';service['image']=info['Image']
  if name in ['gateway','langgraph']:
   service['volumes']=[str(work/'config.yaml')+':/app/config.yaml:ro',str(runtime/'home')+':/app/backend/.prismos',str(runtime/'ca-bundle.crt')+':/run/n04-ca-bundle.crt:ro',str(ROOT/'skills')+':/app/skills:ro',str(runtime/'skills-custom')+':/app/skills/custom']
   if name=='langgraph':service['volumes'].append(str(runtime/'langgraph')+':/app/backend/.langgraph_api')
   service['environment'].update({'PRISMOS_TRUSTED_GRAPH_CONTEXT':'off','PRISMOS_GOVERNED_TICKET_ACTION':'off','PRISMOS_GOVERNED_TICKET_VERDICT':'require_approval','PRISMOS_GOVERNED_TICKET_TENANT':fixture['tenant_id'],'PRISMOS_TICKET_SECRET_ADMIN_TENANT':fixture['tenant_id'],'PRISMOS_GOVERNED_TICKET_POLICY_VERSION':'n04-restored-'+suffix,'LANGGRAPH_API_URL':'http://langgraph:2024'})
  if name=='ticket-receiver':service['volumes']=[str(ROOT/'docker/n04-test/ticket_receiver.py')+':/receiver.py:ro',str(runtime/'receiver')+':/state']
  services[name]=service
 cfg={'name':project,'services':services,'networks':{'restored':{'external':True,'name':project}}}
 snapshot.private_write(compose_path,yaml.safe_dump(cfg,sort_keys=False).encode())
 command(['docker','network','create','--label','prismos.n04.restored-owner='+suffix,project]);network_created=True
 command(['docker','network','connect','--alias','postgres',project,'prismos-n04-wsl-postgres-1']);connected=True
 store('snapshot rows/files restored; starting independent services with Action off')
 services_started=True;compose(['up','-d','--no-build','--pull','never','--wait','--wait-timeout','240'])
 for service in services:
  data=json.loads(command(['docker','inspect',project+'-'+service+'-1']))[0]
  assert data['Config']['Labels']['com.docker.compose.project']==project and not data['HostConfig'].get('PortBindings')
  assert list(data['NetworkSettings']['Networks'])==[project] and not data['HostConfig']['Privileged']
  assert all(m['Destination']!='/var/run/docker.sock' for m in data['Mounts'])
 receipt['phases'].append(probe('restored_native_probe.py',{'phase':'prepare'}));store('restored native CRUD/history/roles verified; model workload prepared')
 for name in ['gateway','langgraph']:
  cfg['services'][name]['environment'].update({'PRISMOS_TRUSTED_GRAPH_CONTEXT':'required','PRISMOS_GOVERNED_TICKET_ACTION':'ticket.create'})
 compose_path.write_text(yaml.safe_dump(cfg,sort_keys=False));compose_path.chmod(0o600)
 compose(['up','-d','--no-build','--pull','never','--no-deps','--wait','--wait-timeout','240','gateway','langgraph'])
 receipt['phases'].append(probe('restored_native_probe.py',{'phase':'diagnose-approve'}));store('real restored model read and approval completed; restarting services')
 compose(['restart','gateway','langgraph']);compose(['up','-d','--no-build','--pull','never','--no-deps','--wait','--wait-timeout','240','gateway','langgraph'])
 receipt['phases'].append(probe('restored_native_probe.py',{'phase':'resume-withdraw'}));store('restored approval resumed once after restart; revocation verified')
 receipt['complete']=True
finally:
 try:
  if services_started:
   for name in ['gateway','langgraph']:
    result=subprocess.run(['docker','logs',project+'-'+name+'-1'],capture_output=True);file=work/(name+'.log');file.write_bytes(result.stdout+result.stderr);file.chmod(0o600)
   compose(['down','--remove-orphans']);receipt['owned_services_removed']=True
 finally:
  if connected:command(['docker','network','disconnect',project,'prismos-n04-wsl-postgres-1'])
  if network_created:command(['docker','network','rm',project]);receipt['owned_network_removed']=True
  for database,clone in clones.items():
   data=snapshot.execute('postgres',['pg_dump','-U','prismos','-d',clone,'-Fc']);snapshot.private_write(work/(database+'-final.dump'),data)
   snapshot.execute('postgres',['dropdb','-U','prismos',clone])
  receipt['owned_clone_databases_removed']=True
  receipt['original_receiver_after']=original_stats()['request_count']
  receipt['original_compose_unchanged']=hashlib.sha256((snapshot.STATE/'compose.yaml').read_bytes()).hexdigest()==original_compose_sha
  assert receipt['original_receiver_after']==original_count and receipt['original_compose_unchanged']
  path.write_text(json.dumps(receipt,indent=2)+'\n')
print(json.dumps(receipt))
