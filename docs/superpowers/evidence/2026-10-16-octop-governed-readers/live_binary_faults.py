"""Actual PostgreSQL Audit failures with real model native DOCX inspection."""
import json,re,subprocess
from live_common import HERE,FIXTURE,expect,login,policy,stats
from native_case import prepare,diagnose,private_logs
from runtime_read_facts import facts
path=HERE/'real-binary-faults.json';assert not path.exists()
original=json.loads((HERE/'real-binary-task-current.json').read_text());assert original['complete']
tenant=FIXTURE['tenant_id'];assert re.fullmatch(r't-[0-9a-f]+',tenant)
schema='n04_native_binary_fault';receipt={'complete':False,'simulated_model':False,'configured_model':FIXTURE['model_name'],'cases':[]};owner=requester=None;installed=False

def sql(code):
 info=json.loads(subprocess.check_output(['docker','inspect','prismos-n04-wsl-postgres-1'],text=True))[0];assert info['Config']['Labels']['com.docker.compose.project']=='prismos-n04-wsl'
 result=subprocess.run(['docker','exec','-i','prismos-n04-wsl-postgres-1','psql','-X','-qAt','-v','ON_ERROR_STOP=1','-U','prismos','-d','prismos'],input=code,text=True,capture_output=True)
 assert result.returncode==0,('owned SQL',result.returncode)
 return result.stdout.strip()
try:
 policy('deny');owner,requester=[login(role) for role in ['approver','requester']]
 assert sql("SELECT count(*) FROM pg_namespace WHERE nspname='"+schema+"'")=='0'
 sql(f"""BEGIN; CREATE SCHEMA {schema}; CREATE TABLE {schema}.mode (event_type text); INSERT INTO {schema}.mode VALUES ('off'); CREATE SEQUENCE {schema}.hits;
 CREATE FUNCTION {schema}.fail_owned_audit() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
 IF NEW.tenant_id='{tenant}' AND NEW.action='read_file' AND NEW.event_type=(SELECT event_type FROM {schema}.mode) THEN
 PERFORM nextval('{schema}.hits'); RAISE EXCEPTION USING ERRCODE='55000', MESSAGE='N04 native binary Audit fault';
 END IF; RETURN NEW; END $$;
 CREATE TRIGGER n04_native_binary_fault BEFORE INSERT ON platform_audit_events FOR EACH ROW EXECUTE FUNCTION {schema}.fail_owned_audit(); COMMIT;""")
 installed=True
 for event in ['action.policy_evaluated','action.read_result']:
  prompt='Immediately inspect the Word file '+original['source_path']+' with office_docx action inspect exactly once. If unavailable report that and stop. Do not create outputs, use bash, read_file, other tools, tickets or delegate. Do not guess document facts.'
  case=prepare(owner,'binary-audit-fault',prompt,[{'name':original['skill_name'],'scope':'tenant','resource_id':original['resource_id']}]);case.update(fault_event=event,complete=False);receipt['cases'].append(case)
  before=stats()['request_count'];sql(f"UPDATE {schema}.mode SET event_type='{event}'; ALTER SEQUENCE {schema}.hits RESTART WITH 1;")
  case['stream_events']=diagnose(requester,case,'binary-fault-'+event.replace('.','-'))
  hits=int(sql(f'SELECT CASE WHEN is_called THEN last_value ELSE 0 END FROM {schema}.hits;'));assert hits>0
  current=facts(case['incident_id']);incident=expect(requester,'/api/incidents/'+case['incident_id']);graph='/api/langgraph/threads/'+incident['thread_id'];state=expect(requester,graph+'/state');runs=expect(requester,graph+'/runs')
  assert runs[0]['status']=='success' and not state.get('next')
  messages=state['values']['messages'];calls=[c for m in messages for c in m.get('tool_calls',[])];assert [c['name'] for c in calls]==['office_docx']
  tools=[m for m in messages if m.get('type')=='tool'];assert len(tools)==1 and 'unavailable' in str(tools[0]['content'])
  assert original['marker'] not in json.dumps(messages) and original['marker'] not in str(incident.get('diagnosis_result'))
  if event=='action.policy_evaluated':assert not current['decisions'] and not current['audits']
  else:
   assert len(current['decisions'])==1
   assert len(current['audits'])==1 and current['audits'][0]['event_type']=='action.policy_evaluated'
  assert stats()['request_count']==before
  case.update(complete=True,thread_id=incident['thread_id'],run_id=runs[0]['run_id'],run_status=runs[0]['status'],actual_trigger_hits=hits,tool_status='unavailable',binary_marker_not_returned=True,durable_facts=current,receiver_before=before,receiver_after=stats()['request_count'])
  path.write_text(json.dumps(receipt,indent=2)+'\n');sql(f"UPDATE {schema}.mode SET event_type='off';")
 receipt['complete']=True
finally:
 private_logs('binary-audit-faults')
 try:
  if installed:
   sql(f'DROP TRIGGER n04_native_binary_fault ON platform_audit_events; DROP FUNCTION {schema}.fail_owned_audit(); DROP TABLE {schema}.mode; DROP SEQUENCE {schema}.hits; DROP SCHEMA {schema};');receipt['trigger_and_schema_removed']=True
 finally:
  for client in [owner,requester]:
   if client:client.close()
  try:policy('off');receipt['canary_restored_off']=True
  finally:path.write_text(json.dumps(receipt,indent=2)+'\n')
print('Actual SQL fault real model binary reader cases complete:',receipt['complete'])
