from pathlib import Path
import hashlib,json,subprocess,sys,uuid
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
FILES=['tests/test_ticket_policy_changes.py','tests/test_runtime_worker_bootstrap.py','tests/test_database_session.py','tests/test_credential_asset_access.py','tests/test_incident_diagnosis.py','tests/test_governed_ticket.py','tests/test_ticket_secret_provider.py']
image=json.loads((HERE/'runtime-image.json').read_text())['image']
inputs=json.loads((HERE/'inputs.json').read_text())['sha256']
def verify():
 for p,h in inputs.items():assert hashlib.sha256((ROOT/p).read_bytes()).hexdigest()==h,p
def run(name,args):
 subprocess.run([sys.executable,str(HERE/'run_validation.py'),name,'--',*args],cwd=ROOT,check=True)
verify()
name='prismos-n04-acceptance-'+uuid.uuid4().hex[:10]
try:
 run('image-runtime',['docker','run','--rm','--network','none','--memory','1g','--cpus','2','--pids-limit','256','--name',name,image,'sh','-c','cd /app/backend && .venv/bin/python -m pytest '+' '.join(FILES)+' -q'])
finally:
 removed=subprocess.run(['docker','inspect',name],capture_output=True).returncode!=0
 (HERE/'image-cleanup.json').write_text(json.dumps({'container':name,'removed':removed,'network':'none','default_privileges':True},indent=2)+'\n')
args=[sys.executable,'scripts/octop_upgrade_probe.py','--previous-archive','/tmp/prismos-copy-share-upgrade/previous/upstream.tar.gz','--previous-receipt','/tmp/prismos-copy-share-upgrade/previous/manifest.json','--previous-revision','e473dd3c4a4741618ffde1a42a3492341a189e8e','--previous-release','0.3.0b5','--output',str(HERE/'upgrade.json')]
for p in FILES+['tests/test_langgraph_proxy_nginx.py','tests/test_nginx_runtime_resolution.py']:args+=['--test-file',p]
run('upgrade',args)
run('static-final',[str(ROOT/'backend/.venv/bin/ruff'),'check','backend/packages/harness/deerflow/database/session.py','backend/app/services/terminal/credential_access.py','backend/app/gateway/routers/alerts.py','backend/tests/test_incident_diagnosis.py','backend/tests/test_runtime_worker_bootstrap.py','backend/tests/test_langgraph_proxy_nginx.py','scripts/octop_wsl_test_env.py','backend/app/alerting/governed_ticket.py','backend/app/alerting/governed_ticket_tool.py','backend/tests/test_ticket_policy_changes.py'])
verify()
(HERE/'release-gates.json').write_text(json.dumps({'complete':True,'inputs_unchanged':True,'M1_exited':False},indent=2)+'\n')
