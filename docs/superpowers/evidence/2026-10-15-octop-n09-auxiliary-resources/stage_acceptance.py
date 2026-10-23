from pathlib import Path
import subprocess
r=Path('/root/.codex/worktrees/octop-integration/prism-os')
d='docs/superpowers/evidence/2026-10-15-octop-n09-auxiliary-resources'
def run(*args): subprocess.run(args,cwd=r,check=True)
run('git','diff','--check')
run('git','add','-u')
run('git','add','backend/app/gateway/resource_authorization.py','backend/app/integrations/octop/auxiliary_packages.py','backend/tests/resource_test_identity.py','backend/tests/test_auxiliary_resource_runtime.py','backend/tests/test_resource_catalog_access.py',d)
logs=[p.relative_to(r).as_posix() for p in sorted((r/d/'logs').iterdir()) if p.is_file()]
run('git','add','-f',*logs,d+'/fixture-import-quarantine.tar.gz')
run(str(r/'backend/.venv/bin/python'),d+'/run_validation.py','brand-staged','--',str(r/'backend/.venv/bin/python'),'scripts/check_brand_identity.py')
run(str(r/'backend/.venv/bin/python'),d+'/finalize_evidence.py')
run('git','add',d+'/brand-staged-result.json',d+'/validation.json')
run('git','add','-f',d+'/logs/brand-staged.log')
run('git','diff','--cached','--check')
run('git','diff','--cached','--stat')
