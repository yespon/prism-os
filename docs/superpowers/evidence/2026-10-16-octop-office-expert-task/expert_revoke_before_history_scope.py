"""Revoke only the owned accepted expert, then restore via current revision."""
from pathlib import Path
import hashlib,json,sys
HERE=Path(__file__).resolve().parent;sys.path.insert(0,str(HERE.parent/'2026-10-16-octop-office-user-task'))
from live_common import login
case=json.loads((HERE/'real-expert-task.json').read_text());assert case['complete'];client=login('requester');agent='/api/agents/'+case['agent_name'];artifact=case['artifact_url'];graph='/api/langgraph/threads/'+case['thread_id'];disabled=None;result={'complete':False}
def update(enabled,revision):
 response=client.put(agent,json={'enabled':enabled,'expected_agent_id':case['agent_id'],'expected_revision':revision});assert response.status_code==200,('update',response.status_code);return response.json()
try:
 original=client.get(agent).json();assert original['enabled'];disabled=update(False,original['revision'])
 statuses={'artifact':client.get(artifact).status_code,'history':client.post(graph+'/history',json={'limit':1}).status_code,'state':client.get(graph+'/state').status_code}
 assert all(code in [403,404] for code in statuses.values()),statuses
 rejected=client.post(graph+'/runs/stream',json={'assistant_id':'lead_agent','input':{'messages':[{'type':'human','content':'Do not run: revoked expert canary'}]},'context':{'agent_name':case['agent_name']}})
 assert rejected.status_code in [403,404],('new run',rejected.status_code)
 result.update({'withdrawn_http_status':statuses,'withdrawn_run_http':rejected.status_code})
finally:
 if disabled:
  restored=update(True,disabled['revision']);assert restored['system_prompt']==original['system_prompt']
 if disabled and result.get('withdrawn_run_http'):
  r=client.get(artifact);assert r.status_code==200 and hashlib.sha256(r.content).hexdigest()==case['artifact_sha256'];assert client.post(graph+'/history',json={'limit':1}).status_code==200
  result.update({'complete':True,'restored_artifact_sha256':case['artifact_sha256'],'stored_prompt_preserved':True,'rejected_request_did_not_execute':True})
 client.close();(HERE/'expert-revoke-recover.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result))
