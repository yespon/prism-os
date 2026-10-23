"""Freeze only backend/runtime inputs; frontend gates own their separate snapshot."""
from pathlib import Path
import hashlib,json,subprocess,sys
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
base=json.loads((HERE.parent/'2026-10-15-octop-n09-remote-command-leases/inputs.json').read_text())
paths={p for p in base['sha256'] if not p.startswith('frontend/')}
paths.update(['backend/app/services/terminal/credential_access.py','backend/tests/test_credential_asset_access.py','backend/scripts/rotate_encrypted_secrets.py','backend/app/gateway/routers/assets.py'])
data={'base_commit':'f7aac71','scope':'backend, runtime, service and validation contracts; no frontend-source acceptance claim','sha256':{p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in sorted(paths)}}
target=HERE/'backend-inputs.json'
if target.exists(): assert json.loads(target.read_text())==data
else: target.write_text(json.dumps(data,indent=2)+'\n')
print('Frozen backend/runtime inputs:',len(paths),flush=True)
subprocess.run([sys.executable,str(HERE/'run_backend_acceptance.py')],cwd=ROOT,check=True)
