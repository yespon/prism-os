"""Real model/native HTTP through failing PostgreSQL transactions, without monkeypatches."""
import json,subprocess
from live_common import FIXTURE,HERE,expect,login,mode,policy,stats
from native_case import prepare,diagnose,private_logs
import database_faults as db
name='database-write-faults';path=HERE/(name+'.json');assert not path.exists()
receipt={'complete':False,'M1_exited':False,'fault_method':'owned PostgreSQL trigger raises SQLSTATE 55000; sequence hit survives transaction rollback','scoped_tenant':FIXTURE['tenant_id'],'cases':[]};clients=[];installed=False

def replay(event_id):
 assert event_id.startswith('event_') and event_id.replace('_','').isalnum()
 code=f'''import asyncio,json
from app.alerting.legacy_audit_delivery import LegacyAuditDeliveryService
async def main():
 service=LegacyAuditDeliveryService()
 await service.deliver_event({FIXTURE['tenant_id']!r},{event_id!r})
 await service.deliver_event({FIXTURE['tenant_id']!r},{event_id!r})
 print(json.dumps({{'original_service_replayed_twice':True}}))
asyncio.run(main())
'''
 result=subprocess.run(['docker','exec','-i','-w','/app/backend','prismos-n04-wsl-gateway-1','uv','run','--frozen','python','-'],input=code,text=True,capture_output=True,timeout=60)
 assert result.returncode==0,('original replay service',result.returncode)
 return json.loads(result.stdout.splitlines()[-1])

try:
 policy('allow');mode('ok');db.install();installed=True
 owner,requester=[login(role) for role in ['approver','requester']];clients=[owner,requester]
 for selected in ['policy','audit_policy','audit_result','legacy_action']:
  case={'scenario':selected,'complete':False};receipt['cases'].append(case)
  case.update(prepare(owner,selected));incident=case['incident_id'];before=stats()['request_count'];case['requests_before']=before
  db.select_mode(selected)
  case['stream_events']=diagnose(requester,case,name+'-'+selected)
  case['actual_trigger_hits']=db.fault_hits();assert case['actual_trigger_hits']>0,'Model must actually reach the failing write'
  case['governed']=expect(requester,'/api/incidents/'+incident+'/governed-ticket')
  case['facts_during_fault']=db.facts(incident)
  if selected in ['policy','audit_policy']:
   assert case['governed']['status'] is None
   assert case['facts_during_fault']['decisions']==case['facts_during_fault']['policy_audits']==0
   assert not case['facts_during_fault']['submissions']
   assert stats()['request_count']==before
  elif selected=='audit_result':
   assert case['governed']['status']=='unknown'
   assert case['facts_during_fault']['submitted_audits']==0
   assert [s['status'] for s in case['facts_during_fault']['submissions']]==['unknown']
   assert not case['facts_during_fault']['deliveries']
   assert stats()['request_count']==before+1
  else:
   assert case['governed']['status']=='submitted'
   assert case['facts_during_fault']['legacy_actions']==0
   deliveries=case['facts_during_fault']['deliveries'];assert len(deliveries)==2
   assert any(d['destination']=='incident_action' and d['status']=='failed' for d in deliveries)
   assert any(d['destination']=='gateway_jsonl' and d['status']=='delivered' for d in deliveries)
   assert stats()['request_count']==before+1
  db.select_mode('off')
  if selected in ['audit_result','legacy_action']:
   repeated=expect(requester,'/api/incidents/'+incident+'/governed-ticket/resume',{})
   assert repeated['status']==case['governed']['status']
   assert stats()['request_count']==before+1
   case['resume_after_fault_did_not_resend']=True
  if selected=='legacy_action':
   event=case['facts_during_fault']['deliveries'][0]['event_id'];case['replay']=replay(event)
   after=db.facts(incident);case['facts_after_recovery']=after
   assert after['legacy_actions']==1 and all(d['status']=='delivered' for d in after['deliveries'])
   assert next(d['attempts'] for d in after['deliveries'] if d['destination']=='incident_action')==2
   timeline=expect(owner,'/api/incidents/'+incident+'/timeline')
   assert case['governed']['ticket_id'] in json.dumps(timeline)
   case['original_timeline_restored']=True
  case['requests_after']=stats()['request_count'];case['complete']=True
  path.write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps(case),flush=True)
 receipt['complete']=True
finally:
 private_logs(name)
 for client in clients:client.close()
 try:
  if installed:
   db.remove();receipt['triggers_and_schema_removed']=True
 finally:
  try:policy('off');receipt['canary_restored_off']=True
  finally:path.write_text(json.dumps(receipt,indent=2)+'\n')
print(json.dumps({'complete':receipt['complete'],'cases':len(receipt['cases'])}))
