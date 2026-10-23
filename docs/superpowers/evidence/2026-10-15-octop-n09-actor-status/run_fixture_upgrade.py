"""Record the test-data-only delta; validate its current upgrade/rollback scope."""
from pathlib import Path
import ast,hashlib,json,subprocess,sys
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
old=json.loads((HERE/'backend-inputs-final.json').read_text())['sha256']
current={p:sha(ROOT/p) for p in old}
changed=[p for p in old if current[p]!=old[p]]
assert changed==['backend/tests/test_custom_agent.py'],changed
consumers=[]
for p in (ROOT/'backend/tests').glob('*.py'):
    if p.name=='test_custom_agent.py': continue
    tree=ast.parse(p.read_text())
    if any(isinstance(n,ast.ImportFrom) and n.module=='test_custom_agent' or isinstance(n,ast.Import) and any(a.name=='test_custom_agent' for a in n.names) for n in ast.walk(tree)):
        consumers.append(p.relative_to(ROOT).as_posix())
assert not consumers,consumers
(HERE/'backend-inputs-current.json').write_text(json.dumps({'base_commit':'c496fbe','scope':'original full-suite snapshot plus isolated cross-actor test identity facts; production unchanged','sha256':current},indent=2)+'\n')
(HERE/'fixture-only-proof.json').write_text(json.dumps({'changed_paths':changed,'before_sha256':old[changed[0]],'after_sha256':current[changed[0]],'unchanged_other_inputs':len(old)-1,'test_module_import_consumers':consumers,'scope':'Only the existing synthetic CRUD authenticator now declares its own isolated User rows; original assertions and production guards unchanged. Full module rerun after correction; all other full-suite inputs byte identical.'},indent=2)+'\n')
image=json.loads((HERE/'image-proof-final.json').read_text())['backend_image']
args=[sys.executable,str(HERE/'run_validation.py'),'upgrade-fixture','--','env','PRISMOS_SCOPED_TEST_IMAGE='+image,sys.executable,'scripts/octop_upgrade_probe.py','--previous-archive','/tmp/prismos-copy-share-upgrade/previous/upstream.tar.gz','--previous-receipt','/tmp/prismos-copy-share-upgrade/previous/manifest.json','--previous-revision','e473dd3c4a4741618ffde1a42a3492341a189e8e','--previous-release','0.3.0b5','--output',str(HERE/'upgrade-fixture.json'),'--test-file','tests/test_custom_agent.py']
subprocess.run(args,cwd=ROOT,check=True)
assert all(sha(ROOT/p)==h for p,h in current.items())
print('Changed isolated CRUD fixture accepted across all three source versions; production and prior selected runtime tests unchanged')
