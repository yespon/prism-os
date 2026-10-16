"""Recheck the failed real read; reuse successful unchanged native CRUD facts."""
import json
from live_common import FIXTURE,HERE,STATE,expect,login,policy,stats
from native_case import diagnose,private_logs
from runtime_read_facts import facts
name='live-skill-read-current';path=HERE/(name+'.json');assert not path.exists()
original=json.loads((HERE/'live-skill-read.json').read_text())
receipt={'complete':False,'M1_exited':False,'N08_started':False,'reused_passed_crud':'live-skill-read.json create/edit/duplicate/current ownership/persistent bytes; diagnosis previously timed out, not reused','case':original};clients=[]
try:
 policy('deny')
 owner,requester,outsider=[login(role) for role in ['approver','requester','outsider']];clients=[owner,requester,outsider]
 detail='/api/skills/'+original['skill_name']+'/detail?scope=tenant&resource_id='+original['resource_id']
 current=expect(requester,detail)
 assert current['enabled'] and current['file_sha256']==original['owned_storage_sha256']
 assert outsider.get(detail).status_code in [403,404]
 before=stats()['request_count'];receipt['requests_before']=before
 receipt['stream_events']=diagnose(requester,original,name)
 proof=facts(original['incident_id']);receipt['native_facts']=proof
 reads=[d for d in proof['decisions'] if d['action']=='read_file'];assert len(reads)==1 and reads[0]['risk_class']=='read_only' and reads[0]['verdict']=='allow'
 results=[a for a in proof['audits'] if a['event_type']=='action.read_result'];assert len(results)==1 and results[0]['outcome']=='succeeded' and results[0]['policy_decision_id']==reads[0]['id']
 assert any(a['event_type']=='action.policy_evaluated' and a['policy_decision_id']==reads[0]['id'] for a in proof['audits'])
 marker=current['instructions'].strip();assert marker.startswith('N04_READ_CURRENT_')
 assert marker in (STATE/(name+'-stream.txt')).read_text()
 receipt['actual_model_tool_read_success']=True
 expect(owner,'/api/tenants/skills/'+original['skill_name'],{'expected_resource_id':original['resource_id'],'enabled':False},method='PUT')
 withdrawn=requester.post('/api/incidents/'+original['incident_id']+'/diagnose',params={'agent_id':original['agent_id']})
 assert withdrawn.status_code in [400,403,409]
 receipt['disabled_resource_blocks_new_diagnosis_http']=withdrawn.status_code
 receipt['requests_after']=stats()['request_count'];assert receipt['requests_after']==before
 receipt['complete']=True
finally:
 private_logs(name)
 for client in clients:client.close()
 try:policy('off');receipt['canary_restored_off']=True
 finally:path.write_text(json.dumps(receipt,indent=2)+'\n')
print(json.dumps(receipt))
