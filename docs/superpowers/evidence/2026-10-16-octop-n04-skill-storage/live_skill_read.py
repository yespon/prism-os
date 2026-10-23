"""Actual native Skill CRUD/persistence plus real model read_file Policy path."""
from pathlib import Path
import hashlib,json,re,secrets,subprocess
from live_common import FIXTURE,HERE,ROOT,STATE,expect,login,mode,policy,stats
from native_case import prepare,diagnose,private_logs
name='live-skill-read';path=HERE/(name+'.json');assert not path.exists()
receipt={'complete':False,'M1_exited':False,'N08_started':False};clients=[]

def facts(incident):
 assert re.fullmatch(r'[a-f0-9-]{36}',incident)
 code=f'''SELECT json_build_object('decisions',COALESCE((SELECT json_agg(json_build_object('id',id,'verdict',verdict,'action',decision_json->>'action','risk_class',decision_json->>'risk_class','resource_id',decision_json->>'resource_id')) FROM platform_policy_decisions WHERE tenant_id='{FIXTURE['tenant_id']}' AND decision_json->>'resource_id'='{incident}'),'[]'::json),'audits',COALESCE((SELECT json_agg(json_build_object('event_id',id,'event_type',event_type,'action',action,'outcome',outcome,'policy_decision_id',policy_decision_id)) FROM platform_audit_events WHERE tenant_id='{FIXTURE['tenant_id']}' AND resource_id='{incident}'),'[]'::json));'''
 value=subprocess.check_output(['docker','exec','prismos-n04-wsl-postgres-1','psql','-X','-qAt','-v','ON_ERROR_STOP=1','-U','prismos','-d','prismos','-c',code],text=True)
 return json.loads(value)

try:
 owner,requester,outsider=[login(role) for role in ['approver','requester','outsider']];clients=[owner,requester,outsider]
 suffix=secrets.token_hex(5);skill_name='n04-read-'+suffix
 marker='N04_READ_CURRENT_'+secrets.token_hex(12)
 created=expect(owner,'/api/tenants/skills',{'name':skill_name,'description':'Owned N04 read acceptance canary','instructions':'N04_READ_OLD_VALUE'},status=201)
 resource=created['resource_id'];receipt.update({'skill_name':skill_name,'resource_id':resource,'create_http_status':201})
 detail='/api/skills/'+skill_name+'/detail?scope=tenant&resource_id='+resource
 assert requester.get(detail).status_code==200
 assert outsider.get(detail).status_code in [403,404]
 forbidden=requester.patch('/api/tenants/skills/'+skill_name,json={'expected_resource_id':resource,'instructions':'FORBIDDEN_REPLACEMENT'});assert forbidden.status_code==403
 edited=expect(owner,'/api/tenants/skills/'+skill_name,{'expected_resource_id':resource,'expected_file_sha256':created['file_sha256'],'instructions':marker},method='PATCH')
 assert edited['resource_id']==resource and marker in edited['instructions'] and edited['file_sha256']!=created['file_sha256']
 duplicate=owner.post('/api/tenants/skills',json={'name':skill_name,'description':'Must not overwrite','instructions':'FORBIDDEN_OVERWRITE'});assert duplicate.status_code==409
 receipt['edit_and_duplicate_protection']=True
 canary=STATE/'skills-custom'/FIXTURE['tenant_id']/skill_name/'SKILL.md'
 assert canary.is_file() and hashlib.sha256(canary.read_bytes()).hexdigest()==edited['file_sha256']
 assert not (ROOT/'skills/custom'/FIXTURE['tenant_id']/skill_name).exists()
 receipt['owned_storage_sha256']=edited['file_sha256'];receipt['source_checkout_unchanged']=True
 path.write_text(json.dumps(receipt,indent=2)+'\n')
 policy('deny');mode('ok')
 persisted=expect(requester,detail);assert persisted['file_sha256']==edited['file_sha256'] and marker in persisted['instructions']
 receipt['survives_gateway_langgraph_recreation']=True
 selected={'name':skill_name,'scope':'tenant','resource_id':resource}
 file_path='/mnt/skills/custom/'+FIXTURE['tenant_id']+'/'+skill_name+'/SKILL.md'
 prompt='This is an authorized isolated file Policy acceptance. Immediately call read_file exactly once with description="Read owned test Skill" and path='+file_path+'. Do not call any other tool or create tickets. Report the exact observed marker briefly after the real tool result. Never retry failed tools.'
 case=prepare(owner,name,system_prompt=prompt,skill_resources=[selected]);receipt.update(case)
 before=stats()['request_count'];receipt['requests_before']=before
 receipt['stream_events']=diagnose(requester,case,name)
 proof=facts(case['incident_id']);receipt['native_facts']=proof
 reads=[d for d in proof['decisions'] if d['action']=='read_file'];assert len(reads)==1 and reads[0]['risk_class']=='read_only' and reads[0]['verdict']=='allow'
 results=[a for a in proof['audits'] if a['event_type']=='action.read_result'];assert len(results)==1 and results[0]['outcome']=='succeeded' and results[0]['policy_decision_id']==reads[0]['id']
 assert any(a['event_type']=='action.policy_evaluated' and a['policy_decision_id']==reads[0]['id'] for a in proof['audits'])
 assert marker in (STATE/(name+'-stream.txt')).read_text()
 receipt['actual_model_tool_read_success']=True
 expect(owner,'/api/tenants/skills/'+skill_name,{'expected_resource_id':resource,'enabled':False},method='PUT')
 withdrawn=requester.post('/api/incidents/'+case['incident_id']+'/diagnose',params={'agent_id':case['agent_id']});assert withdrawn.status_code in [400,403,409]
 receipt['disabled_resource_blocks_new_diagnosis_http']=withdrawn.status_code
 receipt['requests_after']=stats()['request_count'];assert receipt['requests_after']==before
 receipt['complete']=True
finally:
 private_logs(name)
 for client in clients:client.close()
 try:policy('off');receipt['canary_restored_off']=True
 finally:path.write_text(json.dumps(receipt,indent=2)+'\n')
print(json.dumps(receipt))
