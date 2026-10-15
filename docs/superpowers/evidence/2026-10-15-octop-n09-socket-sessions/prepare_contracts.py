from pathlib import Path
import subprocess
ROOT=Path(__file__).resolve().parents[4]
paths=['backend/app/services/terminal/socket_access.py','backend/tests/test_terminal_socket_sessions.py']
p=ROOT/'.github/workflows/octop-integration.yml'
s=p.read_text()
covered=s.split('uv run --locked ruff check',1)[1].split('      - name:',1)[0].split()
extra=[x.removeprefix('backend/') for x in paths if x.removeprefix('backend/') not in covered]
s=s.replace('uv run --locked ruff check','uv run --locked ruff check '+' '.join(extra),1)
p.write_text(s)
p=ROOT/'scripts/octop_upgrade_probe.py'
s=p.read_text().replace('        "tests/test_auth_session_delivery.py",','        "tests/test_terminal_socket_sessions.py",\n        "tests/test_auth_session_delivery.py",',1)
anchor='    contract_paths = [\n'
s=s.replace(anchor,anchor+''.join('        '+repr(x)+',\n' for x in paths),1)
p.write_text(s)
subprocess.run([str(ROOT/'backend/.venv/bin/ruff'),'check','--fix',*paths],cwd=ROOT,check=True)
