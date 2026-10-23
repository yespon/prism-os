"""Use actual owner APIs to pause execution without erasing accepted history."""
import hashlib,json
from pathlib import Path
import httpx
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[3];STATE=ROOT/'backend/tmp/n04-wsl/native-profile';case=json.loads((HERE/'real-native-auxiliary-current.json').read_text());f=json.loads((STATE/'live-fixture.json').read_text());clients=[];owner=None;paused=False;result={'complete':False}
def login(role):
 a=f['users'][role];c=httpx.Client(base_url='http://127.0.0.1:18036',headers={'X-Tenant-Id':f['other_tenant_id'] if role=='outsider' else f['tenant_id']},trust_env=False,timeout=60);r=c.post('/api/auth/login',json={'email':a['email'],'password':a['password']});assert r.status_code==200;c.headers['Authorization']='Bearer '+r.json()['session']['token'];clients.append(c);return c
try:
 owner,nonowner,outsider=[login(x) for x in ['requester','approver','outsider']];agent='/api/agents/'+case['agent_name'];g='/api/langgraph/threads/'+case['thread_id'];runs=owner.get(g+'/runs');assert runs.status_code==200;baseline=[(x['run_id'],x['status']) for x in runs.json()]
 assert nonowner.put(agent,json={'enabled':False}).status_code==404
 r=owner.put(agent,json={'enabled':False});assert r.status_code==200;paused=True
 response=owner.post(g+'/runs/stream',json={'assistant_id':'lead_agent','input':{'messages':[{'type':'human','content':'This request must be rejected before execution.'}]},'context':{'agent_name':case['agent_name']}});assert response.status_code in [400,403,409]
 after=owner.get(g+'/runs');assert [(x['run_id'],x['status']) for x in after.json()]==baseline
 file=owner.get(case['artifact_url']);assert file.status_code==200 and hashlib.sha256(file.content).hexdigest()==case['artifact_sha256']
 history=owner.post(g+'/history',json={'limit':10});assert history.status_code==200 and case['output_path'] in json.dumps(history.json())
 assert nonowner.get(case['artifact_url']).status_code==404 and outsider.get(case['artifact_url']).status_code==404
 result.update(pause_new_execution_http=response.status_code,new_run_created=False,existing_owner_report_and_history_retained=True,nonowner_and_outsider_denied=True)
finally:
 if paused:
  restored=owner.put(agent,json={'enabled':True});assert restored.status_code==200
  assert hashlib.sha256(restored.json()['system_prompt'].encode()).hexdigest()==case['stored_prompt_sha256'];assert restored.json()['skill_resources']==[case['selected_resource']]
  result.update(reenabled_current_selection_and_prompt_unchanged=True,complete=bool(result.get("existing_owner_report_and_history_retained")))
 for c in clients:c.close()
 (HERE/'pause-recovery.json').write_text(json.dumps(result,indent=2)+'\n')
print('Pause blocks new execution; owner history retained; original selection restored')
