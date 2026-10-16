"""Resume the confirmed post-model checkpoint; never resubmit the original task."""
from pathlib import Path
import hashlib,json,sys
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[3];sys.path.insert(0,str(HERE.parent/'2026-10-16-octop-office-expert-task'))
from live_common import login,STATE
case=json.loads((HERE.parent/'2026-10-16-octop-office-expert-task/real-expert-task.json').read_text());pack=json.loads((HERE/'real-report-pack.json').read_text());rows=json.loads((STATE/'office-pack-f44da91eda/history-after-crash.json').read_text());prior=rows[0];assert prior['next']==['LoopDetectionMiddleware.after_model'];calls=prior['values']['messages'][-1]['tool_calls'];assert {c['name'] for c in calls}=={'office_xlsx','office_pptx','office_pdf'}
expected={c['args']['output_path'] for c in calls};assert expected=={'/mnt/user-data/outputs/brief-pack-f44da91eda.'+ext for ext in ['xlsx','pptx','pdf']};client=login('requester');graph='/api/langgraph/threads/'+case['thread_id'];proof={'complete':False,'checkpoint':prior['checkpoint'],'already_completed_docx_inspection_repeated':False}
try:
 original=client.get(case['artifact_url']);assert original.status_code==200 and hashlib.sha256(original.content).hexdigest()==case['artifact_sha256']
 for virtual in expected:assert client.get('/api/threads/'+case['thread_id']+'/artifacts'+virtual).status_code==404,'Existing output requires inspection, not blind retry'
 payload={'assistant_id':'lead_agent','input':None,'checkpoint':prior['checkpoint'],'context':{'agent_name':case['agent_name'],'subagent_enabled':False,'thinking_enabled':False,'is_plan_mode':False},'config':{'recursion_limit':1000},'stream_mode':['values','updates']}
 with client.stream('POST',graph+'/runs/stream',json=payload,timeout=240) as response:
  assert response.status_code==200;transcript='\n'.join(response.iter_lines())
 private=STATE/'office-pack-f44da91eda/resume-stream.txt';private.write_text(transcript);private.chmod(0o600)
 state=client.get(graph+'/state').json();runs=client.get(graph+'/runs').json();assert runs[0]['status']=='success' and not state.get('next')
 after=state['values']['messages'];before=prior['values']['messages'];assert after[:len(before)]==before
 old_read_ids=[c['id'] for m in before for c in m.get('tool_calls',[]) if c['name']=='office_docx'];new_read_ids=[c['id'] for m in after for c in m.get('tool_calls',[]) if c['name']=='office_docx'];assert new_read_ids==old_read_ids
 proof.update({'complete':True,'run_status':'success','previous_messages_preserved':True,'original_docx_inspection_call_ids':old_read_ids,'three_creations_resumed_after_confirming_no_outputs':True,'new_agent_task_submission':False,'checkpoint_continuation_submissions':1})
finally:
 client.close();(HERE/'report-continuation.json').write_text(json.dumps(proof,indent=2)+'\n')
print(json.dumps(proof))
