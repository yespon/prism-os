import argparse,json,secrets,subprocess
from live_common import FIXTURE,HERE,STATE,expect,login,mode,policy,stats


def main():
 parser=argparse.ArgumentParser();parser.add_argument('--case',required=True);args=parser.parse_args()
 path=HERE/(args.case+'.json');assert not path.exists()
 receipt={'complete':False,'M1_exited':False,'scenario':'approved request followed by current policy deny'};clients=[]
 try:
  policy('require_approval')
  owner,requester=[login(role) for role in ['approver','requester']];clients=[owner,requester]
  suffix=secrets.token_hex(5)
  agent=expect(owner,'/api/agents',{'name':'n04-policy-'+suffix,'model':FIXTURE['model_name'],'is_shared':True,'tool_groups':[],'skill_binding_mode':'selected','skill_resources':[],'system_prompt':'This is an isolated governance test. Immediately call create_governed_incident_ticket exactly once. Do not call other tools or perform other work. Report the actual status and stop if approval is required.'},status=201)
  source=expect(owner,'/api/alert-sources',{'name':'N04 policy change '+suffix,'type':'webhook','config_json':{'ticket':{'provider':'webhook','template':{'title':'{{ incident.title }}','incident_key':'{{ incident.incident_key }}'}}},'ai_analysis_enabled':False,'diagnosis_agent_id':agent['id']},status=201)
  token=(STATE/'receiver/receiver-token').read_text().strip()
  expect(owner,'/api/alert-sources/'+source['id']+'/ticket-secret',{'webhook_url':'https://ticket-receiver:8443/tickets','headers':{'Authorization':'Bearer '+token}},status=201)
  incident=expect(owner,'/api/alerts/ingest/'+source['id'],{'alert':{'name':'N04 policy change '+suffix,'severity':'warning'},'labels':{'service':'n04-'+suffix}},status=202)['ingest_id']
  receipt['incident_id']=incident;before=stats()['request_count'];receipt['requests_before']=before
  with requester.stream('POST','/api/incidents/'+incident+'/diagnose',params={'agent_id':agent['id']},timeout=180) as response:
   assert response.status_code==200
   lines=list(response.iter_lines())
  transcript=STATE/(args.case+'-stream.txt');transcript.write_text('\n'.join(lines)+'\n');transcript.chmod(0o600)
  waiting=expect(requester,'/api/incidents/'+incident+'/governed-ticket');assert waiting['status']=='awaiting_approval'
  receipt['decision_before']=waiting
  expect(owner,'/api/approvals/'+waiting['approval_id']+'/approve',{})
  assert stats()['request_count']==before
  policy('deny')
  projected=expect(requester,'/api/incidents/'+incident+'/governed-ticket')
  assert projected['status']=='approved' and projected['can_resume'] is False
  receipt['current_policy_blocks_resume_projection']=True
  response=requester.post('/api/incidents/'+incident+'/governed-ticket/resume',json={})
  receipt['resume_http_status']=response.status_code
  receipt['resume_status']=response.json().get('status')
  receipt['requests_after']=stats()['request_count']
  assert receipt['requests_after']==before,'Old approval must not send after the current policy changes'
  assert response.status_code in [403,409] or receipt['resume_status']=='denied'
  receipt['complete']=True
 finally:
  for name in ['gateway','langgraph']:
   p=subprocess.run(['docker','logs','prismos-n04-wsl-'+name+'-1'],capture_output=True)
   log=STATE/(args.case+'-'+name+'.log');log.write_bytes(p.stdout+p.stderr);log.chmod(0o600)
  for client in clients:client.close()
  mode('ok')
  try:policy('off');receipt['canary_restored_off']=True
  finally:path.write_text(json.dumps(receipt,indent=2)+'\n')
 print(json.dumps(receipt))


if __name__=='__main__':main()
