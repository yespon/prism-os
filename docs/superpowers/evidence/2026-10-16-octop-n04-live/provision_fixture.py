"""Provision explicitly named test users/tenants via original local operator services.

This is deployment fixture setup; subsequent acceptance must use real HTTP login.
No user's existing browser session, password or CLI credential is accessed.
"""
from pathlib import Path
import json,os,secrets,subprocess
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
STATE=ROOT/'backend/tmp/n04-wsl'
path=STATE/'live-fixture.json'
assert not path.exists(),'Existing fixture must be reused, never overwritten'
value={'model_name':'gpt-5.6-luna','users':{}}
suffix=secrets.token_hex(5)
for role in ['requester','approver','outsider']:
 value['users'][role]={'email':f'n04-{role}-{suffix}@example.invalid','password':secrets.token_urlsafe(24)}
pending=STATE/'live-fixture-pending.json'
assert not pending.exists()
pending.write_text(json.dumps(value));os.chmod(pending,0o600)
code='''import asyncio,json,sys,logging
logging.disable(logging.CRITICAL)
from app.gateway.auth_repository import AuthUserRepository
from deerflow.database.tenant_service import create_tenant,add_tenant_member
from deerflow.database.user_config_service import assign_platform_model_to_tenant
async def main():
 value=json.load(sys.stdin)
 repository=AuthUserRepository()
 for role,account in value['users'].items():
  user=repository.create_user(account['email'],'N04 test '+role,account['password'],must_change_password=False)
  account['id']=user['id']
 tenant=await create_tenant('N04 acceptance',value['users']['approver']['id'])
 other=await create_tenant('N04 cross-tenant acceptance',value['users']['outsider']['id'])
 await add_tenant_member(tenant.id,value['users']['requester']['id'],role='member')
 await assign_platform_model_to_tenant(tenant.id,value['model_name'])
 value['tenant_id']=tenant.id
 value['other_tenant_id']=other.id
 print(json.dumps(value))
asyncio.run(main())
'''
p=subprocess.run(['docker','exec','-i','-w','/app/backend','prismos-n04-wsl-gateway-1','uv','run','--frozen','python','-c',code],input=json.dumps(value).encode(),capture_output=True,timeout=90)
assert p.returncode==0,'Fixture operator setup failed; protected pending input retained'
value=json.loads(p.stdout.decode().splitlines()[-1])
path.write_text(json.dumps(value,indent=2)+'\n');os.chmod(path,0o600)
receipt={'tenant_id':value['tenant_id'],'other_tenant_id':value['other_tenant_id'],'model_name':value['model_name'],'users':{role:{'id':account['id'],'scope':'owned test account'} for role,account in value['users'].items()},'private_fixture_reference':'backend/tmp/n04-wsl/live-fixture.json','provisioning':'original local operator repositories/services; not counted as HTTP authentication acceptance'}
(HERE/'fixture.json').write_text(json.dumps(receipt,indent=2)+'\n')
print(json.dumps(receipt))
