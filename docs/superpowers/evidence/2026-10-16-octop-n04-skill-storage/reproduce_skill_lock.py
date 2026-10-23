"""Observe the deployed request/worker self-block with PostgreSQL blocking PIDs."""
import concurrent.futures,json,subprocess,time
from live_common import HERE,login,policy,stats
from native_case import private_logs
case=json.loads((HERE/'live-skill-read.json').read_text());path=HERE/'skill-lock-reproduction.json';assert not path.exists()
receipt={'complete':False,'M1_exited':False,'expected_bug':'SSE preflight retains selected Skill row lock while background diagnosis waits for that row','blocking_samples':[]}
client=None
try:
 policy('deny');client=login('requester');before=stats()['request_count']
 def request():
  try:
   with client.stream('POST','/api/incidents/'+case['incident_id']+'/diagnose',params={'agent_id':case['agent_id']},timeout=20) as response:
    assert response.status_code==200
    list(response.iter_lines())
   return 'completed'
  except Exception as error:return type(error).__name__
 with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
  future=pool.submit(request);deadline=time.monotonic()+18
  while time.monotonic()<deadline:
   sql="SELECT COALESCE(json_agg(json_build_object('pid',pid,'wait_event_type',wait_event_type,'wait_event',wait_event,'blockers',pg_blocking_pids(pid))), '[]'::json) FROM pg_stat_activity WHERE datname=current_database() AND pid<>pg_backend_pid() AND wait_event_type='Lock' AND query ILIKE '%tenant_skills%';"
   rows=json.loads(subprocess.check_output(['docker','exec','prismos-n04-wsl-postgres-1','psql','-X','-qAt','-U','prismos','-d','prismos','-c',sql],text=True))
   if rows:
    receipt['blocking_samples']=rows;break
   time.sleep(.5)
  receipt['stream_result']=future.result(timeout=30)
 assert receipt['blocking_samples'] and all(row['blockers'] for row in receipt['blocking_samples'])
 assert receipt['stream_result']=='ReadTimeout'
 receipt.update({'requests_before':before,'requests_after':stats()['request_count'],'complete':True})
 assert receipt['requests_after']==before
finally:
 private_logs('skill-lock-reproduction')
 if client:client.close()
 try:policy('off');receipt['canary_restored_off']=True
 finally:path.write_text(json.dumps(receipt,indent=2)+'\n')
print(json.dumps(receipt))
