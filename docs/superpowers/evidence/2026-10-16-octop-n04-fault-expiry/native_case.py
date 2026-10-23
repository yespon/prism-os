"""Actual authenticated incident/tool input, with stable approved payload."""
import secrets,subprocess
from live_common import FIXTURE,STATE,expect

def prepare(owner,name):
 suffix=secrets.token_hex(5)
 agent=expect(owner,'/api/agents',{'name':'n04-gate-'+suffix,'model':FIXTURE['model_name'],'is_shared':True,'tool_groups':[],'skill_binding_mode':'selected','skill_resources':[],'system_prompt':'This is an authorized isolated N04 acceptance test. Call create_governed_incident_ticket exactly once immediately. Never retry a failed tool, use other tools, or claim success without a submitted result. Report the actual result briefly and stop.'},status=201)
 source=expect(owner,'/api/alert-sources',{'name':'N04 '+name+' '+suffix,'type':'webhook','config_json':{'ticket':{'provider':'webhook','template':{'title':'{{ incident.title }}','incident_key':'{{ incident.incident_key }}'}}},'ai_analysis_enabled':False,'diagnosis_agent_id':agent['id']},status=201)
 expect(owner,'/api/alert-sources/'+source['id']+'/ticket-secret',{'webhook_url':'https://ticket-receiver:8443/tickets','headers':{'Authorization':'Bearer '+(STATE/'receiver/receiver-token').read_text().strip()}},status=201)
 incident=expect(owner,'/api/alerts/ingest/'+source['id'],{'alert':{'name':'N04 '+name+' '+suffix,'severity':'warning'},'labels':{'service':'n04-'+suffix}},status=202)['ingest_id']
 return {'incident_id':incident,'agent_id':agent['id'],'source_id':source['id']}

def diagnose(requester,case,name):
 with requester.stream('POST','/api/incidents/'+case['incident_id']+'/diagnose',params={'agent_id':case['agent_id']},timeout=180) as response:
  assert response.status_code==200,response.status_code
  lines=list(response.iter_lines())
 path=STATE/(name+'-stream.txt');path.write_text('\n'.join(lines)+'\n');path.chmod(0o600)
 return len([line for line in lines if line.startswith('data:')])

def private_logs(name):
 for service in ['gateway','langgraph']:
  result=subprocess.run(['docker','logs','prismos-n04-wsl-'+service+'-1'],capture_output=True)
  path=STATE/(name+'-'+service+'.log');path.write_bytes(result.stdout+result.stderr);path.chmod(0o600)
