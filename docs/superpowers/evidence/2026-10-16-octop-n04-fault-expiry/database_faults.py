"""Real PostgreSQL write failures in the owned compose project/fixture tenant only."""
import json,re,subprocess
from live_common import FIXTURE
TENANT=FIXTURE['tenant_id'];assert re.fullmatch(r't-[a-f0-9]+',TENANT)
SCHEMA='n04_owned_write_fault'
TABLES=['platform_policy_decisions','platform_audit_events','incident_actions']
MODES={'policy','audit_policy','audit_result','legacy_action','off'}

def sql(statement):
 info=json.loads(subprocess.check_output(['docker','inspect','prismos-n04-wsl-postgres-1'],text=True))[0]
 assert info['Config']['Labels']['com.docker.compose.project']=='prismos-n04-wsl'
 result=subprocess.run(['docker','exec','-i','prismos-n04-wsl-postgres-1','psql','-X','-qAt','-v','ON_ERROR_STOP=1','-U','prismos','-d','prismos'],input=statement,text=True,capture_output=True)
 if result.returncode:raise RuntimeError('Owned SQL failed: '+result.stderr[:500])
 return result.stdout.strip()

def install():
 assert sql("SELECT count(*) FROM pg_namespace WHERE nspname='"+SCHEMA+"'")=='0','Previous owned fault schema must be reviewed before reusing it'
 sql(f"""BEGIN;
 CREATE SCHEMA {SCHEMA};
 CREATE TABLE {SCHEMA}.mode (name text NOT NULL);
 INSERT INTO {SCHEMA}.mode VALUES ('off');
 CREATE SEQUENCE {SCHEMA}.hits;
 CREATE FUNCTION {SCHEMA}.fail_owned_write() RETURNS trigger LANGUAGE plpgsql AS $$
 DECLARE selected text;
 BEGIN
  IF NEW.tenant_id <> '{TENANT}' THEN RETURN NEW; END IF;
  SELECT name INTO selected FROM {SCHEMA}.mode;
  IF (TG_TABLE_NAME='platform_policy_decisions' AND selected='policy') OR
     (TG_TABLE_NAME='platform_audit_events' AND selected='audit_policy' AND to_jsonb(NEW)->>'event_type'='action.policy_evaluated') OR
     (TG_TABLE_NAME='platform_audit_events' AND selected='audit_result' AND to_jsonb(NEW)->>'event_type'='action.submitted') OR
     (TG_TABLE_NAME='incident_actions' AND selected='legacy_action' AND to_jsonb(NEW)->>'action_type'='ticket_created') THEN
   PERFORM nextval('{SCHEMA}.hits');
   RAISE EXCEPTION USING ERRCODE='55000', MESSAGE='N04 owned test write fault';
  END IF;
  RETURN NEW;
 END $$;
 """+'\n'.join(f'CREATE TRIGGER n04_owned_fault BEFORE INSERT ON {table} FOR EACH ROW EXECUTE FUNCTION {SCHEMA}.fail_owned_write();' for table in TABLES)+'\nCOMMIT;')
 assert sql("SELECT count(*) FROM pg_trigger WHERE tgname='n04_owned_fault'")=='3'

def select_mode(value):
 assert value in MODES
 sql(f"UPDATE {SCHEMA}.mode SET name='{value}'; ALTER SEQUENCE {SCHEMA}.hits RESTART WITH 1;")

def fault_hits():
 return int(sql(f'SELECT CASE WHEN is_called THEN last_value ELSE 0 END FROM {SCHEMA}.hits;'))

def remove():
 sql('BEGIN;'+''.join(f'DROP TRIGGER n04_owned_fault ON {table};' for table in TABLES)+f'DROP FUNCTION {SCHEMA}.fail_owned_write(); DROP TABLE {SCHEMA}.mode; DROP SEQUENCE {SCHEMA}.hits; DROP SCHEMA {SCHEMA}; COMMIT;')
 assert sql("SELECT count(*) FROM pg_trigger WHERE tgname='n04_owned_fault'")=='0'
 assert sql("SELECT count(*) FROM pg_namespace WHERE nspname='"+SCHEMA+"'")=='0'

def facts(incident):
 assert re.fullmatch(r'[a-f0-9-]{36}',incident)
 t="tenant_id='"+TENANT+"'"
 value=sql(f"""SELECT json_build_object(
 'decisions',(SELECT count(*) FROM platform_policy_decisions WHERE {t} AND decision_json->>'resource_id'='{incident}'),
 'policy_audits',(SELECT count(*) FROM platform_audit_events WHERE {t} AND resource_id='{incident}' AND event_type='action.policy_evaluated'),
 'submitted_audits',(SELECT count(*) FROM platform_audit_events WHERE {t} AND resource_id='{incident}' AND event_type='action.submitted'),
 'submissions',COALESCE((SELECT json_agg(json_build_object('status',s.status,'decision_id',s.decision_id,'ticket_id',s.ticket_id)) FROM platform_action_submissions s JOIN platform_policy_decisions d ON d.id=s.decision_id WHERE s.tenant_id='{TENANT}' AND d.decision_json->>'resource_id'='{incident}'),'[]'::json),
 'deliveries',COALESCE((SELECT json_agg(json_build_object('status',l.status,'destination',l.destination,'attempts',l.attempts,'error_category',l.error_category,'event_id',l.event_id)) FROM platform_legacy_audit_deliveries l JOIN platform_audit_events a ON a.id=l.event_id WHERE l.tenant_id='{TENANT}' AND a.resource_id='{incident}'),'[]'::json),
 'legacy_actions',(SELECT count(*) FROM incident_actions WHERE {t} AND incident_id='{incident}' AND action_type='ticket_created'));
 """)
 return json.loads(value)
