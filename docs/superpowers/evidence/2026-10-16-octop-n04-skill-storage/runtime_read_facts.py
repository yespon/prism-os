import json,re,subprocess
from live_common import FIXTURE
def facts(incident):
 assert re.fullmatch(r'[a-f0-9-]{36}',incident)
 code=f'''SELECT json_build_object('decisions',COALESCE((SELECT json_agg(json_build_object('id',id,'verdict',verdict,'action',decision_json->>'action','risk_class',decision_json->>'risk_class','resource_id',decision_json->>'resource_id')) FROM platform_policy_decisions WHERE tenant_id='{FIXTURE['tenant_id']}' AND decision_json->>'resource_id'='{incident}'),'[]'::json),'audits',COALESCE((SELECT json_agg(json_build_object('event_id',id,'event_type',event_type,'action',action,'outcome',outcome,'policy_decision_id',policy_decision_id)) FROM platform_audit_events WHERE tenant_id='{FIXTURE['tenant_id']}' AND resource_id='{incident}'),'[]'::json));'''
 value=subprocess.check_output(['docker','exec','prismos-n04-wsl-postgres-1','psql','-X','-qAt','-v','ON_ERROR_STOP=1','-U','prismos','-d','prismos','-c',code],text=True)
 return json.loads(value)
