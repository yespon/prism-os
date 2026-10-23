"""Actual owned artifact/config rollback, with all business Action switches off."""
import hashlib,json,os,subprocess,time
import yaml
from live_common import FIXTURE,HERE,STATE,compose,expect,login,stats
name='artifact-rollback';path=HERE/(name+'.json');assert not path.exists()
config_path=STATE/'compose.yaml';original=config_path.read_bytes();backup=STATE/'compose-before-artifact-rehearsal.yaml';assert not backup.exists();backup.write_bytes(original);backup.chmod(0o600)
current=json.loads((HERE/'runtime-image.json').read_text())['image']
previous=json.loads((HERE.parent/'2026-10-16-octop-n04-live/runtime-image.json').read_text())['image']
old_case=json.loads((HERE.parent/'2026-10-16-octop-n04-live/allow-counter-v2.json').read_text())
skill=json.loads((HERE.parent/'2026-10-16-octop-n04-skill-storage/live-skill-read.json').read_text())
receipt={'complete':False,'M1_exited':False,'N08_started':False,'phases':[],'scope':'Off-state rollback of established authenticated configuration/history/current resource reads. Previous artifact has the known selected-Skill SSE bug; new Skill diagnosis is not enabled on the previous artifact.'}

def validate_config(config):
 assert config['name']=='prismos-n04-wsl'
 for service in ['gateway','langgraph']:
  environment=config['services'][service]['environment']
  assert environment['PRISMOS_GOVERNED_TICKET_ACTION']=='off' and environment['PRISMOS_TRUSTED_GRAPH_CONTEXT']=='off'

def start():
 compose(['up','-d','--no-build','--no-deps','--wait','--wait-timeout','240','gateway','langgraph'])

def probe(stage,image):
 result={'stage':stage,'image':image,'services':{}}
 for service in ['gateway','langgraph']:
  info=json.loads(subprocess.check_output(['docker','inspect','prismos-n04-wsl-'+service+'-1'],text=True))[0]
  assert info['Config']['Labels']['com.docker.compose.project']=='prismos-n04-wsl' and info['Image']==image and info['State']['Health']['Status']=='healthy'
  env=dict(v.split('=',1) for v in info['Config']['Env']);assert env['PRISMOS_GOVERNED_TICKET_ACTION']=='off' and env['PRISMOS_TRUSTED_GRAPH_CONTEXT']=='off'
  result['services'][service]={'healthy':True,'action':'off','trusted_graph':'off','policy_version':env['PRISMOS_GOVERNED_TICKET_POLICY_VERSION']}
 assert result['services']['gateway']['policy_version']==result['services']['langgraph']['policy_version']
 owner,requester,outsider=[login(role) for role in ['approver','requester','outsider']]
 try:
  models=expect(requester,'/api/models/available')['models'];assert any(m['name']==FIXTURE['model_name'] for m in models)
  incident=expect(requester,'/api/incidents/'+old_case['incident_id']);ticket=old_case['governed_status_before_review']['ticket_id'];assert incident['ticket_id']==ticket
  timeline=expect(requester,'/api/incidents/'+old_case['incident_id']+'/timeline');assert ticket in json.dumps(timeline)
  assert outsider.get('/api/incidents/'+old_case['incident_id']).status_code==404
  detail='/api/skills/'+skill['skill_name']+'/detail?scope=tenant&resource_id='+skill['resource_id']
  resource=expect(owner,detail);assert resource['file_sha256']==skill['owned_storage_sha256'] and resource['resource_id']==skill['resource_id']
  assert outsider.get(detail).status_code in [403,404]
  result.update({'original_ticket_and_timeline_preserved':True,'configured_model_available':True,'custom_skill_identity_and_bytes_preserved':True,'outsider_rejected':True})
 finally:
  for client in [owner,requester,outsider]:client.close()
 return result

try:
 base=yaml.safe_load(original);validate_config(base)
 for image in [current,previous]:assert subprocess.check_output(['docker','image','inspect',image,'--format','{{.Id}}'],text=True).strip()==image
 before=stats()['request_count'];receipt['requests_before']=before
 receipt['phases'].append(probe('current-before',current))
 config=yaml.safe_load(original)
 for service in ['gateway','langgraph']:
  config['services'][service]['image']=previous
  config['services'][service]['environment']['PRISMOS_GOVERNED_TICKET_POLICY_VERSION']='n04-off-config-artifact-rehearsal'
 validate_config(config);config_path.write_text(yaml.safe_dump(config,sort_keys=False));config_path.chmod(0o600)
 start();receipt['phases'].append(probe('previous-artifact-and-changed-off-configuration',previous))
 config_path.write_bytes(original);config_path.chmod(0o600);start()
 receipt['phases'].append(probe('restored-current-artifact-and-original-configuration',current))
 assert config_path.read_bytes()==original
 receipt['configuration_bytes_restored']=True;receipt['original_configuration_sha256']=hashlib.sha256(original).hexdigest()
 receipt['requests_after']=stats()['request_count'];assert receipt['requests_after']==before
 receipt['complete']=True
finally:
 config_path.write_bytes(original);config_path.chmod(0o600)
 try:
  start();receipt['current_artifact_restored']=True
 finally:path.write_text(json.dumps(receipt,indent=2)+'\n')
print(json.dumps(receipt))
