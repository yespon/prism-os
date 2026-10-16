"""Actual model diagnosis reads owned DOCX, creates result, preserves history/ACL."""
import argparse,hashlib,io,json,secrets,zipfile
from pathlib import Path
from live_common import HERE,STATE,FIXTURE,expect,login,policy,stats
from native_case import prepare,diagnose,private_logs
from runtime_read_facts import facts
from deerflow.tools.builtins.office_docx import create_docx,inspect_docx

parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--resume',type=Path);parser.add_argument('--output',type=Path,default=HERE/'real-binary-task.json');args=parser.parse_args()
path=args.output;assert not path.exists()
receipt={'complete':False,'configured_model':FIXTURE['model_name'],'simulated_model':False,'M1_exited':False};owner=requester=outsider=None
try:
 policy('deny');owner,requester,outsider=[login(role) for role in ['approver','requester','outsider']]
 if args.resume is None:
  suffix=secrets.token_hex(5);name='native-reader-'+suffix;marker='BINARY_TASK_'+secrets.token_hex(12)
  thread=expect(owner,'/api/langgraph/threads',{})['thread_id'];memory=io.BytesIO()
  with zipfile.ZipFile(memory,'w') as z:
   z.writestr(name+'/SKILL.md','---\nname: '+name+'\ndescription: Governed native document task\n---\nRead report.docx for the actual facts. The report body is not in this prompt.\n')
   z.writestr(name+'/report.docx',create_docx({'paragraphs':['PrismOS governed native document',marker]}))
  response=owner.post('/api/threads/'+thread+'/uploads',files={'files':(name+'.zip',memory.getvalue(),'application/zip')});assert response.status_code==200
  uploaded=response.json()['files'][0]
  installed=expect(owner,'/api/skills/install',{'thread_id':thread,'path':uploaded['virtual_path']});assert installed['success']
  resource=expect(owner,'/api/skills/'+name+'/detail?scope=tenant')['resource_id']
  source='/mnt/skills/custom/'+FIXTURE['tenant_id']+'/'+name+'/report.docx';target='/mnt/user-data/outputs/native-reader-'+suffix+'.docx'
  prompt='This is an authorized document task in incident diagnosis. First inspect the owned Word document '+source+' with office_docx. Only on status ok, create a Word result '+target+' containing the exact report facts and original BINARY_TASK marker, then present_files. If any tool fails, report unavailable and stop immediately. Never use bash, read_file, other reading tools, delegation or ticket creation. Never invent contents.'
  case=prepare(owner,'native-binary-reader',prompt,[{'name':name,'scope':'tenant','resource_id':resource}]);case.update(skill_name=name,resource_id=resource,marker=marker,source_path=source,output_path=target)
  private=STATE/('native-reader-'+suffix);private.mkdir(mode=0o700);(private/'case.json').write_text(json.dumps(case));(private/'case.json').chmod(0o600)
  receipt.update(case,receiver_before=stats()['request_count']);path.write_text(json.dumps(receipt,indent=2)+'\n')
  receipt['stream_events']=diagnose(requester,case,'native-binary-task-'+suffix)
 else:
  case=json.loads(args.resume.read_text());receipt.update(case);marker=case['marker'];target=case['output_path'];private=STATE/('native-reader-recheck-'+secrets.token_hex(5));private.mkdir(mode=0o700);receipt['new_model_task_submissions']=0
 incident=expect(requester,'/api/incidents/'+case['incident_id']);graph='/api/langgraph/threads/'+incident['thread_id'];state=expect(requester,graph+'/state');runs=expect(requester,graph+'/runs')
 (private/'state.json').write_text(json.dumps(state));(private/'state.json').chmod(0o600)
 assert runs[0]['status']=='success' and not state.get('next'),('terminal',runs[0]['status'],state.get('next'))
 messages=state['values']['messages'];calls=[c for m in messages for c in m.get('tool_calls',[])];assert any(c['name']=='office_docx' and c['args'].get('action')=='inspect' for c in calls)
 assert any(c['name']=='present_files' for c in calls)
 url='/api/threads/'+incident['thread_id']+'/artifacts'+target+'?download=true';response=requester.get(url);assert response.status_code==200
 assert marker in str(inspect_docx(response.content));assert all(c.get(url).status_code==404 for c in [owner,outsider])
 requester.close();requester=login('requester');assert target in json.dumps(expect(requester,graph+'/history',{'limit':5}));assert requester.get(url).content==response.content
 current=facts(case['incident_id']);assert current['decisions'] and all(d['action']=='read_file' for d in current['decisions']);assert any(a['event_type']=='action.read_result' and a['outcome']=='succeeded' for a in current['audits'])
 assert stats()['request_count']==receipt['receiver_before']
 receipt.update(complete=True,thread_id=incident['thread_id'],run_id=runs[0]['run_id'],run_status=runs[0]['status'],tool_names=[c['name'] for c in calls],artifact_url=url,artifact_sha256=hashlib.sha256(response.content).hexdigest(),artifact_bytes=len(response.content),fresh_login_history=True,same_tenant_nonowner_and_other_tenant_denied=True,durable_policy_and_read_audit=current,receiver_after=stats()['request_count'])
finally:
 private_logs('native-binary-task')
 for client in [owner,requester,outsider]:
  if client:client.close()
 try:policy('off');receipt['canary_restored_off']=True
 finally:path.write_text(json.dumps(receipt,indent=2)+'\n')
print('Real model governed binary task complete:',receipt['complete'])
