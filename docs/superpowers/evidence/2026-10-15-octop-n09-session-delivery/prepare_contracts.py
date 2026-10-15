from pathlib import Path
import subprocess
ROOT=Path(__file__).resolve().parents[4]
paths=['backend/app/gateway/auth.py','backend/app/gateway/routers/auth.py','backend/app/gateway/session_authorization.py','backend/tests/test_auth_session_delivery.py','backend/tests/test_auth_middleware_status.py']
p=ROOT/'.github/workflows/octop-integration.yml'
s=p.read_text()
covered=s.split('uv run --locked ruff check',1)[1].split('      - name:',1)[0].split()
extra=[x.removeprefix('backend/') for x in paths if x.removeprefix('backend/') not in covered]
s=s.replace('uv run --locked ruff check','uv run --locked ruff check '+' '.join(extra),1)
p.write_text(s)
p=ROOT/'scripts/octop_upgrade_probe.py'
s=p.read_text().replace('        "tests/test_runtime_actor_status.py",','        "tests/test_auth_session_delivery.py",\n        "tests/test_auth_middleware_status.py",\n        "tests/test_runtime_actor_status.py",',1)
anchor='    contract_paths = [\n'
s=s.replace(anchor,anchor+''.join('        '+repr(x)+',\n' for x in paths if ('"'+x+'"') not in s.split(anchor,1)[1]),1)
p.write_text(s)
subprocess.run([str(ROOT/'backend/.venv/bin/ruff'),'check','--fix',*paths],cwd=ROOT,check=True)
