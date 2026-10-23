from pathlib import Path
import json,os,secrets,ssl,subprocess,time
import httpx,yaml
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
STATE=ROOT/'backend/tmp/n04-wsl'
PROJECT='prismos-n04-wsl'
FIXTURE=json.loads((STATE/'live-fixture.json').read_text())
BASE='http://127.0.0.1:18026'

def compose(args):
 return subprocess.run(['docker','compose','-p',PROJECT,'--env-file',str(STATE/'runtime.env'),'-f',str(STATE/'compose.yaml'),*args],cwd=ROOT,capture_output=True,check=True).stdout

def policy(verdict):
 assert verdict in {'off','allow','deny','require_approval'}
 path=STATE/'compose.yaml'
 backup=STATE/'compose-before-live.yaml'
 if not backup.exists():backup.write_bytes(path.read_bytes());os.chmod(backup,0o600)
 config=yaml.safe_load(path.read_text());assert config['name']==PROJECT
 for name in ['gateway','langgraph']:
  environment=config['services'][name]['environment']
  environment.update({'PRISMOS_TRUSTED_GRAPH_CONTEXT':'required' if verdict!='off' else 'off','PRISMOS_GOVERNED_TICKET_TENANT':FIXTURE['tenant_id'] if verdict!='off' else '', 'PRISMOS_GOVERNED_TICKET_ACTION':'ticket.create' if verdict!='off' else 'off','PRISMOS_GOVERNED_TICKET_VERDICT':verdict if verdict!='off' else 'deny','PRISMOS_GOVERNED_TICKET_POLICY_VERSION':'n04-'+verdict+'-'+secrets.token_hex(4),'PRISMOS_TICKET_SECRET_ADMIN_TENANT':FIXTURE['tenant_id'] if verdict!='off' else ''})
 path.write_text(yaml.safe_dump(config,sort_keys=False));os.chmod(path,0o600)
 compose(['up','-d','--no-build','--no-deps','gateway','langgraph'])
 deadline=time.monotonic()+120
 while time.monotonic()<deadline:
  states=[subprocess.check_output(['docker','inspect','--format','{{.State.Health.Status}}',PROJECT+'-'+name+'-1'],text=True).strip() for name in ['gateway','langgraph']]
  if all(s=='healthy' for s in states):return
  time.sleep(1)
 raise RuntimeError('Owned services not healthy after canary configuration')

def login(role):
 account=FIXTURE['users'][role]
 client=httpx.Client(base_url=BASE,headers={'X-Tenant-Id':FIXTURE['other_tenant_id'] if role=='outsider' else FIXTURE['tenant_id']},trust_env=False,timeout=60)
 response=client.post('/api/auth/login',json={'email':account['email'],'password':account['password']})
 assert response.status_code==200,('login',role,response.status_code)
 client.headers['Authorization']='Bearer '+response.json()['session']['token']
 session=client.get('/api/auth/session');assert session.status_code==200 and session.json()['user']['id']==account['id']
 return client

def expect(client,path,payload=None,method=None,status=200):
 response=client.request(method or ('POST' if payload is not None else 'GET'),path,json=payload)
 assert response.status_code==status,(path,response.status_code,response.text[:300])
 return response.json()

def stats():
 root=STATE/'receiver'
 with httpx.Client(verify=ssl.create_default_context(cafile=str(root/'server.crt')),trust_env=False,timeout=10) as c:
  response=c.get('https://127.0.0.1:18443/stats',headers={'Authorization':'Bearer '+(root/'receiver-token').read_text().strip()})
  assert response.status_code==200
  return response.json()

def mode(value):
 assert value in {'ok','fail','timeout'}
 (STATE/'receiver/receiver-mode').write_text(value+'\n')
