"""Wait real persisted five-minute TTL; never alter clocks, TTL or database facts."""
from datetime import datetime,timezone
import json,time
from live_common import HERE,expect,login,mode,policy,stats
from native_case import prepare,diagnose,private_logs
name='wall-clock-expiry';path=HERE/(name+'.json');assert not path.exists()
receipt={'complete':False,'M1_exited':False,'clock_or_TTL_overridden':False,'database_expiry_modified':False};clients=[]
try:
 policy('require_approval');mode('ok')
 owner,requester=[login(role) for role in ['approver','requester']];clients=[owner,requester]
 case=prepare(owner,name);receipt.update(case);before=stats()['request_count'];receipt['requests_before']=before
 receipt['stream_events']=diagnose(requester,case,name)
 waiting=expect(requester,'/api/incidents/'+case['incident_id']+'/governed-ticket');assert waiting['status']=='awaiting_approval'
 approval=expect(owner,'/api/approvals/'+waiting['approval_id']);assert approval['status']=='pending'
 created=datetime.fromisoformat(approval['created_at'].replace('Z','+00:00'));expires=datetime.fromisoformat(approval['expires_at'].replace('Z','+00:00'))
 assert (expires-created).total_seconds()==300
 receipt.update({'approval_id':approval['approval_id'],'created_at':approval['created_at'],'expires_at':approval['expires_at'],'phase':'waiting for actual five-minute approval expiry'})
 path.write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps(receipt),flush=True)
 started=time.monotonic()
 while datetime.now(timezone.utc)<=expires:
  time.sleep(min(10,max(.1,(expires-datetime.now(timezone.utc)).total_seconds()+.2)))
 receipt['actual_wait_seconds']=round(time.monotonic()-started,3)
 projected=expect(requester,'/api/incidents/'+case['incident_id']+'/governed-ticket');assert projected['status']=='expired' and projected['can_resume'] is False
 current=expect(owner,'/api/approvals/'+approval['approval_id']);assert current['status']=='expired'
 review=owner.post('/api/approvals/'+approval['approval_id']+'/approve',json={});assert review.status_code==409
 resume=requester.post('/api/incidents/'+case['incident_id']+'/governed-ticket/resume',json={});assert resume.status_code==200 and resume.json()['status']=='expired'
 repeat=requester.post('/api/incidents/'+case['incident_id']+'/governed-ticket/resume',json={});assert repeat.status_code==200 and repeat.json()['status']=='expired'
 receipt.update({'final_approval_status':current['status'],'late_review_http_status':review.status_code,'resume_status':resume.json()['status'],'requests_after':stats()['request_count'],'complete':True,'phase':'complete'})
 assert receipt['requests_after']==before
finally:
 private_logs(name)
 for client in clients:client.close()
 try:policy('off');receipt['canary_restored_off']=True
 finally:path.write_text(json.dumps(receipt,indent=2)+'\n')
print(json.dumps(receipt))
