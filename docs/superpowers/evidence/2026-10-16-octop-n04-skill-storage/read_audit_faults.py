"""Real read-only model Tool with actual pre-read/result Audit SQL failures."""
import json,re,subprocess
from live_common import FIXTURE,HERE,expect,login,policy,stats
from native_case import diagnose,private_logs
from runtime_read_facts import facts
name='read-audit-faults';path=HERE/(name+'.json');assert not path.exists()
original=json.loads((HERE/'live-skill-read.json').read_text());tenant=FIXTURE['tenant_id'];assert re.fullmatch(r't-[0-9a-f]+',tenant)
schema='n04_owned_read_fault';receipt={'complete':False,'M1_exited':False,'cases':[],'file_content_already_in_selected_skill_prompt':True,'scope':'Test native read Tool Audit boundary; does not claim the selected main Skill contents were previously unknown to the model'};owner=None;requester=None;installed=False

def sql(code):
 info=json.loads(subprocess.check_output(['docker','inspect','prismos-n04-wsl-postgres-1'],text=True))[0];assert info['Config']['Labels']['com.docker.compose.project']=='prismos-n04-wsl'
 result=subprocess.run(['docker','exec','-i','prismos-n04-wsl-postgres-1','psql','-X','-qAt','-v','ON_ERROR_STOP=1','-U','prismos','-d','prismos'],input=code,text=True,capture_output=True)
 assert result.returncode==0,('owned SQL',result.returncode)
 return result.stdout.strip()
try:
 policy('deny');owner,requester=[login(role) for role in ['approver','requester']]
 expect(owner,'/api/tenants/skills/'+original['skill_name'],{'expected_resource_id':original['resource_id'],'enabled':True},method='PUT')
 assert sql("SELECT count(*) FROM pg_namespace WHERE nspname='"+schema+"'")=='0'
 sql(f"""BEGIN; CREATE SCHEMA {schema}; CREATE TABLE {schema}.mode (event_type text); INSERT INTO {schema}.mode VALUES ('off'); CREATE SEQUENCE {schema}.hits;
 CREATE FUNCTION {schema}.fail_owned_audit() RETURNS trigger LANGUAGE plpgsql AS $$
 BEGIN
 IF NEW.tenant_id='{tenant}' AND NEW.action='read_file' AND NEW.event_type=(SELECT event_type FROM {schema}.mode) THEN
 PERFORM nextval('{schema}.hits'); RAISE EXCEPTION USING ERRCODE='55000', MESSAGE='N04 owned read Audit fault';
 END IF; RETURN NEW; END $$;
 CREATE TRIGGER n04_owned_read_fault BEFORE INSERT ON platform_audit_events FOR EACH ROW EXECUTE FUNCTION {schema}.fail_owned_audit(); COMMIT;""")
 installed=True
 for event in ['action.policy_evaluated','action.read_result']:
  case={'fault_event':event,'complete':False};receipt['cases'].append(case)
  baseline=facts(original['incident_id']);old_decisions={d['id'] for d in baseline['decisions']};old_audits={a['event_id'] for a in baseline['audits']};before=stats()['request_count']
  sql(f"UPDATE {schema}.mode SET event_type='{event}'; ALTER SEQUENCE {schema}.hits RESTART WITH 1;")
  case['stream_events']=diagnose(requester,original,name+'-'+event.replace('.','-'))
  hits=int(sql(f'SELECT CASE WHEN is_called THEN last_value ELSE 0 END FROM {schema}.hits;'));assert hits>0
  current=facts(original['incident_id']);decisions=[d for d in current['decisions'] if d['id'] not in old_decisions];audits=[a for a in current['audits'] if a['event_id'] not in old_audits]
  if event=='action.policy_evaluated':assert not decisions and not audits
  else:
   assert len(decisions)==1 and decisions[0]['action']=='read_file' and decisions[0]['risk_class']=='read_only'
   assert len(audits)==1 and audits[0]['event_type']=='action.policy_evaluated'
  assert stats()['request_count']==before
  case.update({'actual_trigger_hits':hits,'new_decisions':decisions,'new_audits':audits,'requests_before':before,'requests_after':stats()['request_count'],'complete':True})
  path.write_text(json.dumps(receipt,indent=2)+'\n')
  sql(f"UPDATE {schema}.mode SET event_type='off';")
 receipt['complete']=True
finally:
 private_logs(name)
 try:
  if installed:
   sql(f'DROP TRIGGER n04_owned_read_fault ON platform_audit_events; DROP FUNCTION {schema}.fail_owned_audit(); DROP TABLE {schema}.mode; DROP SEQUENCE {schema}.hits; DROP SCHEMA {schema};')
   assert sql("SELECT count(*) FROM pg_namespace WHERE nspname='"+schema+"'")=='0';receipt['triggers_and_schema_removed']=True
  if owner:expect(owner,'/api/tenants/skills/'+original['skill_name'],{'expected_resource_id':original['resource_id'],'enabled':False},method='PUT')
 finally:
  for client in [owner,requester]:
   if client:client.close()
  try:policy('off');receipt['canary_restored_off']=True
  finally:path.write_text(json.dumps(receipt,indent=2)+'\n')
print(json.dumps(receipt))
