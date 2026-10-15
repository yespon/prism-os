from pathlib import Path
import subprocess,sys
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
paths=['.github/workflows/octop-integration.yml','scripts/octop_upgrade_probe.py','backend/app/agent/terminal_tools.py','backend/app/services/terminal/session.py','backend/app/services/terminal/socket_access.py','backend/app/gateway/routers/terminal.py','backend/tests/test_terminal_socket_sessions.py','backend/app/gateway/auth.py','backend/app/gateway/routers/auth.py','backend/app/gateway/session_authorization.py','backend/tests/test_auth_session_delivery.py',HERE.relative_to(ROOT).as_posix()]
for p in HERE.glob('*.py'): p.write_text(p.read_text().rstrip()+'\n')
subprocess.run(['git','add',*paths],cwd=ROOT,check=True)
if not (HERE/'brand-staged-result.json').exists():
    subprocess.run([sys.executable,str(HERE/'run_validation.py'),'brand-staged','--',sys.executable,'scripts/check_brand_identity.py'],cwd=ROOT,check=True)
subprocess.run(['git','diff','--cached','--check','--','.',':(exclude)**/*.log'],cwd=ROOT,check=True)
print('Frozen session feature staged; final complete gate receipts required before commit')
