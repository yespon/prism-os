from pathlib import Path
import argparse,json,secrets,subprocess,time
from live_common import FIXTURE,HERE,STATE,expect,login,mode,policy,stats


def main():
 parser=argparse.ArgumentParser();parser.add_argument('verdict',choices=['deny','allow','require_approval']);parser.add_argument('--case',required=True);parser.add_argument('--provider-mode',choices=['ok','fail','timeout'],default='ok')
 args=parser.parse_args();receipt_path=HERE/(args.case+'.json');assert not receipt_path.exists()
 receipt={'case':args.case,'verdict':args.verdict,'complete':False,'real_model_configured':True,'provider_mode':args.provider_mode,'M1_exited':False}
 clients=[]
 try:
  policy(args.verdict)
  owner,requester,outsider=[login(role) for role in ['approver','requester','outsider']];clients=[owner,requester,outsider]
  receipt['actual_logins']=3
  model=expect(requester,'/api/models/available')['models']
  assert any(m['name']==FIXTURE['model_name'] for m in model)
  suffix=secrets.token_hex(5)
  agent=expect(owner,'/api/agents',{'name':'n04-ticket-'+suffix,'model':FIXTURE['model_name'],'is_shared':True,'tool_groups':[],'skill_binding_mode':'selected','skill_resources':[],'system_prompt':'This is an authorized isolated N04 test. Immediately call create_governed_incident_ticket exactly once for this incident. Do not call any other tool, delegate, execute commands or access files. After receiving the actual tool result, report its status briefly. Never claim success without a submitted result.'},status=201)
  source=expect(owner,'/api/alert-sources',{'name':'N04 '+args.case+' '+suffix,'type':'webhook','config_json':{'ticket':{'provider':'webhook'}},'ai_analysis_enabled':False,'diagnosis_agent_id':agent['id']},status=201)
  receipt.update({'agent_id':agent['id'],'source_id':source['id']})
  token=(STATE/'receiver/receiver-token').read_text().strip()
  secret=expect(owner,'/api/alert-sources/'+source['id']+'/ticket-secret',{'webhook_url':'https://ticket-receiver:8443/tickets','headers':{'Authorization':'Bearer '+token}},status=201)
  receipt['secret_ref_id']=secret['secret_ref']['id']
  ingested=expect(owner,'/api/alerts/ingest/'+source['id'],{'alert':{'name':'N04 '+args.case+' '+suffix,'severity':'warning'},'labels':{'service':'n04-'+suffix,'env':'test'}},status=202)
  incident=ingested['ingest_id'];assert incident
  receipt['incident_id']=incident
  assert outsider.get('/api/incidents/'+incident).status_code==404
  mode(args.provider_mode)
  before=stats()['request_count'];receipt['requests_before']=before
  with requester.stream('POST','/api/incidents/'+incident+'/diagnose',params={'agent_id':agent['id']},timeout=180) as response:
   assert response.status_code==200,('diagnose',response.status_code)
   lines=list(response.iter_lines())
  # Generated test transcripts stay protected; exported evidence contains only factual status.
  transcript=STATE/(args.case+'-stream.txt');transcript.write_text('\n'.join(lines)+'\n');transcript.chmod(0o600)
  receipt['stream_events']=len([line for line in lines if line.startswith('data:')])
  result=expect(requester,'/api/incidents/'+incident+'/governed-ticket')
  receipt['governed_status_before_review']=result
  assert result['actor_id']==FIXTURE['users']['requester']['id']
  assert result['tenant_id']==FIXTURE['tenant_id']
  if args.verdict=='deny':
   assert result['status']=='denied'
   assert stats()['request_count']==before
  elif args.verdict=='allow':
   expected='submitted' if args.provider_mode=='ok' else 'unknown'
   assert result['status']==expected
   assert stats()['request_count']==before+1
   repeated=expect(requester,'/api/incidents/'+incident+'/governed-ticket/resume',{})
   assert repeated['status']==expected and stats()['request_count']==before+1
   receipt['duplicate_resume_no_extra_request']=True
  else:
   assert result['status']=='awaiting_approval' and stats()['request_count']==before
   approval=result['approval_id'];assert approval
   assert requester.post('/api/approvals/'+approval+'/approve',json={}).status_code==403
   assert outsider.get('/api/approvals/'+approval).status_code==404
   reviewed=expect(owner,'/api/approvals/'+approval+'/approve',{})
   assert reviewed['status']=='approved'
   resumed=expect(requester,'/api/incidents/'+incident+'/governed-ticket/resume',{})
   receipt['resumed']=resumed
   assert resumed['status']=='submitted' and stats()['request_count']==before+1
  receipt['requests_after']=stats()['request_count'];receipt['complete']=True
 finally:
  for name in ['gateway','langgraph']:
   diagnostic=subprocess.run(['docker','logs','prismos-n04-wsl-'+name+'-1'],capture_output=True)
   log=STATE/(args.case+'-'+name+'.log');log.write_bytes(diagnostic.stdout+diagnostic.stderr);log.chmod(0o600)
  receipt['private_diagnostic_reference']='backend/tmp/n04-wsl/'+args.case+'-{gateway,langgraph}.log'
  for c in clients:c.close()
  mode('ok')
  try:policy('off');receipt['canary_restored_off']=True
  finally:receipt_path.write_text(json.dumps(receipt,indent=2)+'\n')
 print(json.dumps(receipt))


if __name__=='__main__':main()
