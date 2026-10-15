from pathlib import Path
import hashlib,json,subprocess,sys
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
base=json.loads((HERE.parent/'2026-10-15-octop-n09-auxiliary-resources/inputs.json').read_text())
paths=set(base['sha256'])
paths.update(['docker/provisioner/requirements.lock','docker/provisioner/app.py','docker/provisioner/scoped_commands.py','docker/provisioner/Dockerfile','backend/tests/test_provisioner_kubeconfig.py','backend/tests/test_remote_scoped_commands.py','backend/packages/harness/deerflow/community/aio_sandbox/remote_command.py','backend/packages/harness/deerflow/community/aio_sandbox/remote_backend.py','backend/packages/harness/deerflow/community/aio_sandbox/backend.py','backend/packages/harness/deerflow/config/sandbox_config.py','scripts/octop_remote_smoke.py'])
hashes={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in sorted(paths)}
frontend=base['frontend_reuse']
assert all(hashes[p]==h for p,h in frontend['sha256'].items())
(HERE/'inputs.json').write_text(json.dumps({'base_commit':'c20fdd9','sha256':hashes,'frontend_reuse':frontend},indent=2)+'\n')
print('Frozen',len(hashes),'inputs; frontend unchanged:',len(frontend['sha256']))
