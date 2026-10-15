"""Default Docker forbids nested Local namespaces; validate all other changed paths."""
from pathlib import Path
import hashlib,json,subprocess,sys,uuid
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
proof=json.loads((HERE/'image-proof-final.json').read_text())
image=proof['backend_image']
name='prismos-actor-image-accepted-'+uuid.uuid4().hex[:12]
command='cd /app/backend && .venv/bin/python -m pytest tests/test_runtime_actor_status.py tests/test_file_access_http.py tests/test_diagnosis_delivery.py tests/test_langgraph_proxy.py -q -k "not account_withdrawal_stops_actual_scoped_command"'
try:
    subprocess.run([sys.executable,str(HERE/'run_validation.py'),'image-compatible-runtime','--','docker','run','--rm','--network','none','--memory','1g','--cpus','2','--pids-limit','256','--name',name,image,'sh','-c',command],cwd=ROOT,check=True)
finally:
    assert subprocess.run(['docker','container','inspect',name],capture_output=True).returncode!=0
inputs=json.loads((HERE/'backend-inputs-final.json').read_text())['sha256']
assert all(hashlib.sha256((ROOT/p).read_bytes()).hexdigest()==h for p,h in inputs.items())
(HERE/'image-compatible-scope.json').write_text(json.dumps({'image':image,'default_privileges':True,'network':'none','owned_test_container_removed':True,'excluded':'Three actual Local namespace positive tests cannot start under default Docker namespace restrictions; not passed/skipped as success. Their actual process revoke checks passed on host and isolated PostgreSQL. Earlier unfiltered image attempts retained.','production_namespace_policy':'unchanged; unavailable namespace execution fails closed; no privileged container'},indent=2)+'\n')
