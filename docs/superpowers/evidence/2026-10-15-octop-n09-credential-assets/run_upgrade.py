from pathlib import Path
import hashlib,json,subprocess,sys
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
backend=json.loads((HERE/'backend-inputs.json').read_text())['sha256']
frontend=json.loads((HERE/'frontend-inputs.json').read_text())['sha256']
hashes=backend|frontend
assert all(hashlib.sha256((ROOT/p).read_bytes()).hexdigest()==h for p,h in hashes.items())
image=json.loads((HERE/'image-proof.json').read_text())['backend_image']
args=[sys.executable,str(HERE/'run_validation.py'),'upgrade','--','env','PRISMOS_SCOPED_TEST_IMAGE='+image,sys.executable,'scripts/octop_upgrade_probe.py','--previous-archive','/tmp/prismos-copy-share-upgrade/previous/upstream.tar.gz','--previous-receipt','/tmp/prismos-copy-share-upgrade/previous/manifest.json','--previous-revision','e473dd3c4a4741618ffde1a42a3492341a189e8e','--previous-release','0.3.0b5','--output',str(HERE/'upgrade.json'),'--test-file','tests/test_credential_asset_access.py','--test-file','tests/test_terminal_access_boundaries.py','--test-file','tests/test_remote_scoped_commands.py','--test-file','tests/test_secrets_crypto.py']
subprocess.run(args,cwd=ROOT,check=True)
assert all(hashlib.sha256((ROOT/p).read_bytes()).hexdigest()==h for p,h in hashes.items())
print('Affected upgrade/rollback completed with unchanged final backend/frontend inputs')
