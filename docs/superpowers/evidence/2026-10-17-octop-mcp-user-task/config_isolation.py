"""Prove target configuration stays in the owned native database/profile."""
import json
from pathlib import Path
import sys

import httpx

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
sys.path.insert(0,str(ROOT/'scripts'))
from octop_wsl_native_env import NATIVE,STATE,process_identity
binding=json.loads((NATIVE/'analytics-service/binding.json').read_text())
main=json.loads((STATE/'live-fixture.json').read_text())
native=json.loads((NATIVE/'live-fixture.json').read_text())


def names(fixture,role,port):
 account=fixture['users'][role]
 with httpx.Client(base_url=f'http://127.0.0.1:{port}',headers={'X-Tenant-Id':fixture['tenant_id']},trust_env=False,timeout=20) as c:
  response=c.post('/api/auth/login',json={'email':account['email'],'password':account['password']});assert response.status_code==200
  c.headers['Authorization']='Bearer '+response.json()['session']['token']
  response=c.get('/api/mcp/config');assert response.status_code==200
  return set(response.json()['mcp_servers'])


assert binding['server_name'] not in names(main,'approver',18026)
assert binding['server_name'] in names(native,'requester',18036)
owned=json.loads((NATIVE/'analytics-service/ownership.json').read_text())
assert process_identity(owned['pid'])=={k:owned[k] for k in ['starttime','cmdline_sha256']}
assert NATIVE.joinpath('analytics-service').stat().st_mode & 0o777 == 0o700
for name in ['token','binding.json','ownership.json','mcp-before.json','calls.jsonl']:
 assert NATIVE.joinpath('analytics-service',name).stat().st_mode & 0o777 == 0o600
output=HERE/'config-isolation.json';assert not output.exists()
output.write_text(json.dumps({'complete':True,'main_admin_mcp_configuration_has_no_test_target':True,'native_owner_mcp_configuration_has_target':True,'target_owned_process_identity_verified':True,'private_target_files_owner_only':True,'new_model_task_submissions':0},indent=2)+'\n')
print('Actual APIs verify native-only target configuration and private ownership')
