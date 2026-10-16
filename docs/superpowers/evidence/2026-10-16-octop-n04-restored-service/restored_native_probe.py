"""Original authenticated user paths inside the independently restored stack."""
from pathlib import Path
import hashlib,json,os,secrets,ssl,sys
import httpx
value=json.load(sys.stdin);fixture=value['fixture'];phase=value['phase']
base='http://nginx:2026';case_path=Path(os.environ['PRISMOS_HOME'])/'n04-restored-case.json'
clients=[]

def expect(client,path,payload=None,method=None,status=200):
 response=client.request(method or ('POST' if payload is not None else 'GET'),path,json=payload)
 assert response.status_code==status,(path,response.status_code)
 return response.json()

def login(role):
 account=fixture['users'][role]
 client=httpx.Client(base_url=base,headers={'X-Tenant-Id':fixture['other_tenant_id'] if role=='outsider' else fixture['tenant_id']},trust_env=False,timeout=60)
 response=expect(client,'/api/auth/login',{'email':account['email'],'password':account['password']})
 client.headers['Authorization']='Bearer '+response['session']['token'];clients.append(client)
 assert expect(client,'/api/auth/session')['user']['id']==account['id']
 return client

def stats():
 with httpx.Client(verify=ssl.create_default_context(cafile='/run/n04-ca-bundle.crt'),trust_env=False,timeout=10) as client:
  response=client.get('https://ticket-receiver:8443/stats',headers={'Authorization':'Bearer '+value['receiver_token']});assert response.status_code==200
  return response.json()

def save(case):
 case_path.write_text(json.dumps(case,indent=2)+'\n');case_path.chmod(0o600)

try:
 owner,requester,outsider=[login(role) for role in ['approver','requester','outsider']]
 if phase=='prepare':
  if not value.get('reuse_prepare'):
   with httpx.Client(base_url=base,trust_env=False,timeout=30) as public:
    assert public.get('/',follow_redirects=True).status_code==200
    assert public.post('/api/langgraph/threads',json={}).status_code==401
    assert public.get('/api/auth/bootstrap-status').json()['needs_setup'] is False
   assert any(model['name']==fixture['model_name'] for model in expect(requester,'/api/models/available')['models'])
  with httpx.Client(base_url='http://langgraph:2024',trust_env=False,timeout=30) as graph:
   busy=graph.post('/threads/search',json={'status':'busy','limit':100})
   body=busy.json()
   detail={'http_status':busy.status_code,'response_type':type(body).__name__,'threads':[{'thread_id':row.get('thread_id'),'status':row.get('status')} for row in body] if isinstance(body,list) else None,'response_keys':list(body) if isinstance(body,dict) else None}
   print(json.dumps({'restored_graph_preflight':detail}),flush=True)
   assert busy.status_code==200 and isinstance(body,list)
   terminal_evidence=[]
   for thread in body:
    runs=graph.get('/threads/'+thread['thread_id']+'/runs');assert runs.status_code==200
    rows=runs.json();assert isinstance(rows,list) and rows
    assert all(row['status'] in {'success','error','timeout','interrupted'} for row in rows),'Nonterminal or unknown restored run blocks canary'
    terminal_evidence.append({'thread_id':thread['thread_id'],'thread_projection':thread['status'],'runs':[{'run_id':row['run_id'],'status':row['status']} for row in rows]})
  if not value.get('reuse_prepare'):
   old=value['old_case'];incident=expect(requester,'/api/incidents/'+old['incident_id']);assert incident['ticket_id']==old['governed_status_before_review']['ticket_id']
   assert incident['ticket_id'] in json.dumps(expect(requester,'/api/incidents/'+old['incident_id']+'/timeline'))
   assert outsider.get('/api/incidents/'+old['incident_id']).status_code==404
   previous=value['old_skill'];detail='/api/skills/'+previous['skill_name']+'/detail?scope=tenant&resource_id='+previous['resource_id']
   resource=expect(owner,detail);assert resource['resource_id']==previous['resource_id'] and resource['file_sha256']==previous['owned_storage_sha256']
   assert outsider.get(detail).status_code in [403,404]
   edited=expect(owner,'/api/tenants/skills/'+previous['skill_name'],{'expected_resource_id':previous['resource_id'],'expected_file_sha256':resource['file_sha256'],'instructions':'N04_RESTORED_EXISTING_EDIT'},method='PATCH')
   assert edited['resource_id']==previous['resource_id'] and edited['file_sha256']!=resource['file_sha256']
  suffix=secrets.token_hex(5);skill_name='n04-restored-'+suffix;marker='N04_RESTORED_FILE_'+secrets.token_hex(12)
  created=expect(owner,'/api/tenants/skills',{'name':skill_name,'description':'Restored native user-flow canary','instructions':marker},status=201)
  if not value.get('reuse_prepare'):
   assert owner.post('/api/tenants/skills',json={'name':skill_name,'description':'No overwrite'}).status_code==409
   assert requester.patch('/api/tenants/skills/'+skill_name,json={'expected_resource_id':created['resource_id'],'instructions':'FORBIDDEN'}).status_code==403
  location='/mnt/skills/custom/'+fixture['tenant_id']+'/'+skill_name+'/SKILL.md'
  prompt='Perform these exact tool calls for the restored-stack test. First call read_file with precisely this JSON: '+json.dumps({'description':'Read restored owned Skill','path':location,'start_line':None,'end_line':None})+'. Only after a successful read, call create_governed_incident_ticket with {} exactly once. Use the exact JSON file path above. On an error stop. If approval is required report that actual status and stop. Never claim a submitted ticket without a submitted tool result.'
  agent=expect(owner,'/api/agents',{'name':'n04-restored-agent-'+suffix,'model':fixture['model_name'],'is_shared':True,'tool_groups':[],'skill_binding_mode':'selected','skill_resources':[{'name':skill_name,'scope':'tenant','resource_id':created['resource_id']}],'system_prompt':prompt},status=201)
  source=expect(owner,'/api/alert-sources',{'name':'N04 restored '+suffix,'type':'webhook','config_json':{'ticket':{'provider':'webhook','template':{'title':'{{ incident.title }}','incident_key':'{{ incident.incident_key }}'}}},'ai_analysis_enabled':False,'diagnosis_agent_id':agent['id']},status=201)
  expect(owner,'/api/alert-sources/'+source['id']+'/ticket-secret',{'webhook_url':'https://ticket-receiver:8443/tickets','headers':{'Authorization':'Bearer '+value['receiver_token']}},status=201)
  incident=expect(owner,'/api/alerts/ingest/'+source['id'],{'alert':{'name':'N04 restored '+suffix,'severity':'warning'},'labels':{'service':'n04-restored-'+suffix}},status=202)['ingest_id']
  case={'incident_id':incident,'agent_id':agent['id'],'source_id':source['id'],'skill_name':skill_name,'resource_id':created['resource_id'],'marker':marker,'receiver_before':stats()['request_count'],'phase':'prepared'};save(case)
  result={'phase':phase,'complete':True,'original_auth_roles_model_and_history_restored':True,'existing_skill_identity_and_edit_preserved':True,'new_skill_create_duplicate_and_member_write_guards':True,'baseline_checks_executed':not bool(value.get('reuse_prepare')),'reused_prepare_evidence':value.get('reuse_prepare'),'busy_thread_projections':len(body),'active_or_unknown_restored_runs':0,'terminal_run_evidence':terminal_evidence,'receiver_before':case['receiver_before']}
 elif phase=='diagnose-approve':
  case=json.loads(case_path.read_text());assert stats()['request_count']==case['receiver_before']
  with requester.stream('POST','/api/incidents/'+case['incident_id']+'/diagnose',params={'agent_id':case['agent_id']},timeout=180) as response:
   assert response.status_code==200
   lines=list(response.iter_lines())
  transcript=case_path.with_name('n04-restored-stream.txt');transcript.write_text('\n'.join(lines)+'\n');transcript.chmod(0o600)
  assert case['marker'] in transcript.read_text()
  waiting=expect(requester,'/api/incidents/'+case['incident_id']+'/governed-ticket');assert waiting['status']=='awaiting_approval'
  assert waiting['tenant_id']==fixture['tenant_id'] and waiting['actor_id']==fixture['users']['requester']['id']
  assert stats()['request_count']==case['receiver_before']
  assert requester.post('/api/approvals/'+waiting['approval_id']+'/approve',json={}).status_code==403
  assert outsider.get('/api/approvals/'+waiting['approval_id']).status_code==404
  approved=expect(owner,'/api/approvals/'+waiting['approval_id']+'/approve',{});assert approved['status']=='approved'
  case.update({'waiting':waiting,'phase':'approved','approval_id':waiting['approval_id']});save(case)
  result={'phase':phase,'complete':True,'incident_id':case['incident_id'],'approval_id':waiting['approval_id'],'decision_id':waiting['decision_id'],'actual_model_read_marker_seen':True,'requester_and_other_tenant_cannot_review':True,'approved_without_submission':True,'receiver_count':stats()['request_count']}
 elif phase=='resume-withdraw':
  case=json.loads(case_path.read_text());assert case['phase']=='approved'
  approved=expect(owner,'/api/approvals/'+case['approval_id']);assert approved['status']=='approved'
  resumed=expect(requester,'/api/incidents/'+case['incident_id']+'/governed-ticket/resume',{});assert resumed['status']=='submitted'
  repeated=expect(requester,'/api/incidents/'+case['incident_id']+'/governed-ticket/resume',{});assert repeated['status']=='submitted' and repeated['ticket_id']==resumed['ticket_id']
  assert stats()['request_count']==case['receiver_before']+1
  consumed=expect(owner,'/api/approvals/'+case['approval_id']);assert consumed['status']=='consumed'
  assert resumed['ticket_id'] in json.dumps(expect(owner,'/api/incidents/'+case['incident_id']+'/timeline'))
  expect(owner,'/api/tenants/skills/'+case['skill_name'],{'expected_resource_id':case['resource_id'],'enabled':False},method='PUT')
  refused=requester.post('/api/incidents/'+case['incident_id']+'/diagnose',params={'agent_id':case['agent_id']});assert refused.status_code in [400,403,409]
  assert stats()['request_count']==case['receiver_before']+1
  case.update({'phase':'complete','submitted':resumed,'receiver_after':stats()['request_count']});save(case)
  result={'phase':phase,'complete':True,'incident_id':case['incident_id'],'submitted':resumed,'approval_status_after_restart':'consumed','repeated_resume_no_extra_request':True,'withdrawal_blocks_diagnosis_http':refused.status_code,'receiver_before':case['receiver_before'],'receiver_after':case['receiver_after']}
 else:raise ValueError('Unknown restored probe phase')
finally:
 for client in clients:client.close()
print(json.dumps(result))
