"""Real owned JSONL filesystem failure and two-process original replay; no Provider replacement."""
import concurrent.futures,hashlib,json,os,secrets,subprocess
from live_common import FIXTURE,HERE,STATE,expect,login,policy,stats
from native_case import prepare,diagnose,private_logs
name='jsonl-failure-replay';path=HERE/(name+'.json');assert not path.exists()
receipt={'complete':False,'M1_exited':False,'fault_scope':'Only the dedicated WSL project audit file; temporary path-type disk fault, not a tenant-specific filesystem policy'};clients=[];fault_active=False;backup=None;fault_identity=None
file=STATE/'home/audit/events.jsonl'
assert file.is_file() and not file.is_symlink() and file.resolve().is_relative_to((STATE/'home').resolve())

def facts(incident):
 query="SELECT COALESCE(json_agg(json_build_object('event_id',a.id,'destination',l.destination,'status',l.status,'error_category',l.error_category,'attempts',l.attempts)),'[]'::json) FROM platform_legacy_audit_deliveries l JOIN platform_audit_events a ON a.id=l.event_id WHERE a.resource_id='"+incident+"' AND a.tenant_id='"+FIXTURE['tenant_id']+"';"
 return json.loads(subprocess.check_output(['docker','exec','prismos-n04-wsl-postgres-1','psql','-X','-qAt','-U','prismos','-d','prismos','-c',query],text=True))

def restore_file():
 global fault_active
 if fault_active:
  info=file.stat();assert file.is_dir() and [info.st_dev,info.st_ino]==fault_identity
  file.rmdir();os.replace(backup,file);fault_active=False

def replay(worker,event):
 code=f'''import asyncio,json
from app.alerting.legacy_audit_delivery import LegacyAuditDeliveryService
async def main():
 service=LegacyAuditDeliveryService()
 await asyncio.gather(*[service.deliver_event({FIXTURE['tenant_id']!r},{event!r}) for _ in range(4)])
 print(json.dumps({{'worker':{worker},'completed':True,'replay_calls':4}}))
asyncio.run(main())
'''
 result=subprocess.run(['docker','exec','-i','-w','/app/backend','prismos-n04-wsl-gateway-1','uv','run','--frozen','python','-'],input=code,text=True,capture_output=True,timeout=60)
 assert result.returncode==0,('original concurrent replay worker',worker,result.returncode)
 return json.loads(result.stdout.splitlines()[-1])
try:
 policy('allow');owner,requester=[login(role) for role in ['approver','requester']];clients=[owner,requester]
 case=prepare(owner,name);receipt.update(case);before=stats()['request_count'];receipt['requests_before']=before
 backup=file.with_name('events.n04-backup-'+secrets.token_hex(6));assert not backup.exists();os.replace(file,backup)
 try:file.mkdir(mode=0o700)
 except BaseException:
  os.replace(backup,file);raise
 info=file.stat();fault_identity=[info.st_dev,info.st_ino];fault_active=True
 receipt['stream_events']=diagnose(requester,case,name)
 result=expect(requester,'/api/incidents/'+case['incident_id']+'/governed-ticket');assert result['status']=='submitted'
 receipt['governed_result']=result;assert stats()['request_count']==before+1
 during=facts(case['incident_id']);receipt['delivery_during_fault']=during
 assert any(row['destination']=='gateway_jsonl' and row['status']=='failed' and row['error_category']=='IsADirectoryError' for row in during)
 assert any(row['destination']=='incident_action' and row['status']=='delivered' for row in during)
 event=during[0]['event_id'];assert event.startswith('event_') and event.replace('_','').isalnum()
 restore_file()
 with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
  results=list(pool.map(lambda worker:replay(worker,event),[1,2]))
 assert all(result['completed'] for result in results);receipt['actual_process_workers']=results
 after=facts(case['incident_id']);assert len(after)==2 and all(row['status']=='delivered' for row in after);receipt['delivery_after_replay']=after
 events=[json.loads(line) for line in file.read_text().splitlines() if line.strip()]
 matching=[event_row for event_row in events if event_row.get('metadata',{}).get('platform_event_id')==event]
 assert len(matching)==1
 assert (STATE/'receiver/receiver-token').read_text().strip() not in file.read_text()
 receipt['jsonl_event_count_after_concurrent_replay']=len(matching)
 repeated=expect(requester,'/api/incidents/'+case['incident_id']+'/governed-ticket/resume',{});assert repeated['status']=='submitted'
 receipt['requests_after']=stats()['request_count'];assert receipt['requests_after']==before+1
 receipt['original_timeline_contains_ticket']=result['ticket_id'] in json.dumps(expect(owner,'/api/incidents/'+case['incident_id']+'/timeline'));assert receipt['original_timeline_contains_ticket']
 receipt['complete']=True
finally:
 try:
  restore_file();receipt['original_audit_file_restored']=not fault_active
  private_logs(name)
 finally:
  for client in clients:client.close()
  try:policy('off');receipt['canary_restored_off']=True
  finally:path.write_text(json.dumps(receipt,indent=2)+'\n')
print(json.dumps(receipt))
