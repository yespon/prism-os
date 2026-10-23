from pathlib import Path
import hashlib,json,sys
HERE=Path(__file__).resolve().parent;sys.path.insert(0,str(HERE.parent/'2026-10-16-octop-office-user-task'))
from live_common import login,STATE
case=json.loads((HERE.parent/'2026-10-16-octop-office-user-task/real-docx-current.json').read_text());client=login('requester');path='/api/langgraph/threads/'+case['thread_id']
def state():
 r=client.get(path+'/state');assert r.status_code==200;return r.json()
try:
 before=state();assert before['next']==['SandboxMiddleware.after_agent'],'Continue only the confirmed pending cleanup node'
 before_sha=hashlib.sha256(json.dumps(before['values']['messages'],sort_keys=True).encode()).hexdigest()
 payload={'assistant_id':'lead_agent','input':None,'context':{'agent_name':case['agent_name'],'subagent_enabled':False},'config':{'recursion_limit':1000},'stream_mode':['updates','values']}
 with client.stream('POST',path+'/runs/stream',json=payload,timeout=120) as r:
  assert r.status_code==200;transcript='\n'.join(r.iter_lines())
 private=STATE/'office-cleanup-continuation.txt';private.write_text(transcript);private.chmod(0o600)
 after=state();assert not after['next'];after_sha=hashlib.sha256(json.dumps(after['values']['messages'],sort_keys=True).encode()).hexdigest();assert before_sha==after_sha,'No new model message or tool execution is allowed in cleanup continuation'
 runs=client.get(path+'/runs').json();assert runs[0]['status']=='success'
 receipt={'complete':True,'thread_id':case['thread_id'],'continued_node':'SandboxMiddleware.after_agent','actual_product_recursion_limit':1000,'run_status':runs[0]['status'],'messages_sha256_before':before_sha,'messages_sha256_after':after_sha,'model_and_tool_messages_unchanged':True,'artifact_regenerated':False,'prior_acceptance_correction':'Earlier file/history accepted but graph cleanup was pending at artificial probe limit 30; full task accepted only after this success and terminal-aware recheck.'}
 (HERE/'cleanup-continuation.json').write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps(receipt))
finally:client.close()
