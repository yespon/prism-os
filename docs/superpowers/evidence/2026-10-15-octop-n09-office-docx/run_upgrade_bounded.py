from pathlib import Path
import hashlib,json,subprocess,sys
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
hashes=json.loads((HERE/'inputs-bounded.json').read_text())['sha256']
def verify(): assert all(hashlib.sha256((ROOT/p).read_bytes()).hexdigest()==h for p,h in hashes.items())
verify()
image=subprocess.check_output(['docker','image','inspect','prismos-office-docx:test','--format','{{.Id}}'],text=True).strip()
args=[sys.executable,str(HERE/'run_validation.py'),'bounded-upgrade','--','env','PRISMOS_SCOPED_TEST_IMAGE='+image,sys.executable,'scripts/octop_upgrade_probe.py','--previous-archive','/tmp/prismos-copy-share-upgrade/previous/upstream.tar.gz','--previous-receipt','/tmp/prismos-copy-share-upgrade/previous/manifest.json','--previous-revision','e473dd3c4a4741618ffde1a42a3492341a189e8e','--previous-release','0.3.0b5','--output',str(HERE/'upgrade-bounded.json'),'--test-file','tests/test_office_docx.py','--test-file','tests/test_file_access_boundaries.py','--test-file','tests/test_file_access_http.py']
subprocess.run(args,cwd=ROOT,check=True)
verify()
print('Affected session/account upgrade and rollback accepted with immutable host inputs')
