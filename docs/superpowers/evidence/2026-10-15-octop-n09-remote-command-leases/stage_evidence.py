from pathlib import Path
import subprocess,sys
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
for p in HERE.glob('*.py'):
    p.write_text(p.read_text().rstrip()+'\n')
paths=['.github/workflows/octop-integration.yml','backend/packages/harness/deerflow/community/aio_sandbox/aio_sandbox_provider.py','backend/packages/harness/deerflow/community/aio_sandbox/backend.py','backend/packages/harness/deerflow/community/aio_sandbox/remote_backend.py','backend/packages/harness/deerflow/community/aio_sandbox/remote_command.py','backend/packages/harness/deerflow/config/sandbox_config.py','backend/tests/test_provisioner_kubeconfig.py','backend/tests/test_remote_scoped_commands.py','docker/provisioner','scripts/octop_remote_smoke.py','scripts/octop_upgrade_probe.py',str(HERE.relative_to(ROOT))]
subprocess.run(['git','add',*paths],cwd=ROOT,check=True)
subprocess.run([sys.executable,str(HERE/'run_validation.py'),'brand-staged','--',sys.executable,'scripts/check_brand_identity.py'],cwd=ROOT,check=True)
subprocess.run(['git','diff','--cached','--check'],cwd=ROOT,check=True)
print('Current functional block staged; next credential evidence remains separate; commit waits for complete backend receipt.')
