from pathlib import Path
import subprocess,sys
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
for p in HERE.glob('*.py'): p.write_text(p.read_text().rstrip()+'\n')
paths=['.github/workflows/octop-integration.yml','backend/app/gateway/routers/assets.py','backend/app/services/terminal/credential_access.py','backend/app/services/terminal/session.py','backend/scripts/rotate_encrypted_secrets.py','backend/tests/test_credential_asset_access.py','backend/tests/test_remote_scoped_commands.py','docker/provisioner/app.py','scripts/octop_upgrade_probe.py','frontend/src/core/terminal-agent/assets-api.ts','frontend/src/core/terminal-agent/assets-api.test.ts','frontend/src/components/workspace/terminal/asset-sidebar.tsx','frontend/src/components/workspace/terminal/add-host-dialog.tsx','frontend/src/components/workspace/terminal/add-credential-dialog.tsx','frontend/src/components/workspace/terminal/asset-dialogs.test.tsx','frontend/src/components/workspace/terminal/persistent-terminal.tsx',HERE.relative_to(ROOT).as_posix()]
subprocess.run(['git','add',*paths],cwd=ROOT,check=True)
subprocess.run([sys.executable,str(HERE/'run_validation.py'),'brand-staged','--',sys.executable,'scripts/check_brand_identity.py'],cwd=ROOT,check=True)
subprocess.run(['git','diff','--cached','--check'],cwd=ROOT,check=True)
print('Current credential functional block staged; final complete receipts still required.')
