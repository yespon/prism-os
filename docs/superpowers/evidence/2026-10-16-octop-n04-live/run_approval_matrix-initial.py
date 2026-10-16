import concurrent.futures,json,secrets,subprocess,time
from live_common import FIXTURE,HERE,STATE,compose,expect,login,mode,policy,stats


def wait_healthy():
 deadline=time.monotonic()+120
 while time.monotonic()<deadline:
  states=[subprocess.check_output(['docker','inspect','--format','{{.State.Health.Status}}','prismos-n04-wsl-'+name+'-1'],text=True).strip() for name in ['gateway','langgraph']]
  if all(s=='healthy' for s in states):return
  time.sleep(1)
 raise RuntimeError('Owned canary services did not recover')


def main():
 path=HERE/'approval-matrix.json';assert not path.exists()
 receipt={'complete':False,'M1_exited':False,'cases':[],'payload_scope':'explicit configured stable title/key template; changing an unsubmitted approved payload remains forbidden'}
 clients=[]
 try:
  policy('require_approval')
  owner,requester,outsider=[login(role) for role in ['approver','requester','outsider']];clients=[owner,requester,outsider]
  token=(STATE/'receiver/receiver-token').read_text().strip()
  for scenario in ['approve','reject','revoke_agent','withdraw_secret','rotate_secret','restart']:
   case={'scenario':scenario,'complete':False};receipt['cases'].append(case)
   suffix=secrets.token_hex(5)
   agent=expect(owner,'/api/agents',{'name':'n04-approval-'+suffix,'model':FIXTURE['model_name'],'is_shared':True,'tool_groups':[],'skill_binding_mode':'selected','skill_resources':[],'system_prompt':'Authorized isolated test: call create_governed_incident_ticket exactly once immediately for this incident, then report its actual result briefly. Do not call other tools, delegate, access files or execute commands. If approval is pending, stop and wait; never bypass approval.'},status=201)
   source=expect(owner,'/api/alert-sources',{'name':'N04 approval '+scenario+' '+suffix,'type':'webhook','config_json':{'ticket':{'provider':'webhook','template':{'title':'{{ incident.title }}','incident_key':'{{ incident.incident_key }}'}}},'ai_analysis_enabled':False,'diagnosis_agent_id':agent['id']},status=201)
   binding=expect(owner,'/api/alert-sources/'+source['id']+'/ticket-secret',{'webhook_url':'https://ticket-receiver:8443/tickets','headers':{'Authorization':'Bearer '+token}},status=201)
   event=expect(owner,'/api/alerts/ingest/'+source['id'],{'alert':{'name':'N04 approval '+scenario+' '+suffix,'severity':'warning'},'labels':{'service':'n04-'+suffix,'env':'test'}},status=202)
   incident=event['ingest_id'];case.update({'incident_id':incident,'agent_id':agent['id'],'source_id':source['id']})
   before=stats()['request_count'];case['requests_before']=before
   with requester.stream('POST','/api/incidents/'+incident+'/diagnose',params={'agent_id':agent['id']},timeout=180) as response:
    assert response.status_code==200
    lines=list(response.iter_lines())
   transcript=STATE/('approval-'+scenario+'-stream.txt');transcript.write_text('\n'.join(lines)+'\n');transcript.chmod(0o600)
   waiting=expect(requester,'/api/incidents/'+incident+'/governed-ticket');case['waiting']=waiting
   assert waiting['status']=='awaiting_approval' and stats()['request_count']==before
   assert waiting['actor_id']==FIXTURE['users']['requester']['id']
   approval=waiting['approval_id']
   assert requester.post('/api/approvals/'+approval+'/approve',json={}).status_code==403
   assert outsider.get('/api/approvals/'+approval).status_code==404
   review='reject' if scenario=='reject' else 'approve'
   decided=expect(owner,'/api/approvals/'+approval+'/'+review,{})
   assert decided['status']==('rejected' if review=='reject' else 'approved')
   if scenario=='revoke_agent':
    expect(owner,'/api/agents/'+agent['name'],{'enabled':False,'expected_agent_id':agent['id']},method='PUT')
   elif scenario=='withdraw_secret':
    disabled=expect(owner,'/api/alert-sources/'+source['id']+'/ticket-secret',method='DELETE');assert disabled['active'] is False
   elif scenario=='rotate_secret':
    def rotate(_):
     return owner.put('/api/alert-sources/'+source['id']+'/ticket-secret',json={'expected_ref_id':binding['secret_ref']['id'],'webhook_url':'https://ticket-receiver:8443/tickets','headers':{'Authorization':'Bearer '+token}})
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
     rotations=list(pool.map(rotate,range(2)))
    assert sorted(r.status_code for r in rotations)==[200,409]
    case['concurrent_rotation_statuses']=sorted(r.status_code for r in rotations)
    winner=next(r.json() for r in rotations if r.status_code==200)
    assert winner['secret_ref']['id']!=binding['secret_ref']['id']
   elif scenario=='restart':
    compose(['restart','gateway','langgraph']);wait_healthy()
    assert expect(requester,'/api/incidents/'+incident+'/governed-ticket')['status']=='approved'
   resumed=requester.post('/api/incidents/'+incident+'/governed-ticket/resume',json={})
   case['resume_http_status']=resumed.status_code
   if scenario in ['revoke_agent','withdraw_secret','rotate_secret']:
    assert resumed.status_code in [403,409],(scenario,resumed.status_code)
    assert stats()['request_count']==before
   else:
    assert resumed.status_code==200,(scenario,resumed.status_code)
    result=resumed.json();case['resumed']=result
    expected='rejected' if scenario=='reject' else 'submitted'
    assert result['status']==expected,(scenario,result['status'])
    assert stats()['request_count']==before+(0 if scenario=='reject' else 1)
    repeated=expect(requester,'/api/incidents/'+incident+'/governed-ticket/resume',{})
    assert repeated['status']==expected and stats()['request_count']==before+(0 if scenario=='reject' else 1)
   case['requests_after']=stats()['request_count'];case['complete']=True
   path.write_text(json.dumps(receipt,indent=2)+'\n')
   print(json.dumps({'completed':scenario,'requests_delta':case['requests_after']-before}),flush=True)
  receipt['complete']=True
 finally:
  for name in ['gateway','langgraph']:
   diagnostic=subprocess.run(['docker','logs','prismos-n04-wsl-'+name+'-1'],capture_output=True)
   log=STATE/('approval-matrix-'+name+'.log');log.write_bytes(diagnostic.stdout+diagnostic.stderr);log.chmod(0o600)
  for client in clients:client.close()
  mode('ok')
  try:policy('off');receipt['canary_restored_off']=True
  finally:path.write_text(json.dumps(receipt,indent=2)+'\n')
 print(json.dumps(receipt))


if __name__=='__main__':main()
