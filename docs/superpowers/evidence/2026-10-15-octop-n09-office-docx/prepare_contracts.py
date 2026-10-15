from pathlib import Path
import subprocess
ROOT=Path(__file__).resolve().parents[4]
paths=['backend/packages/harness/deerflow/tools/builtins/office_docx.py','backend/tests/test_office_docx.py','backend/packages/harness/deerflow/sandbox/file_access.py','backend/packages/harness/deerflow/tools/tools.py','backend/app/integrations/file_access.py']
p=ROOT/'.github/workflows/octop-integration.yml'
s=p.read_text()
covered=s.split('uv run --locked ruff check',1)[1].split('      - name:',1)[0].split()
extra=[x.removeprefix('backend/') for x in paths if x.removeprefix('backend/') not in covered]
s=s.replace('uv run --locked ruff check','uv run --locked ruff check '+' '.join(extra),1)
p.write_text(s)
p=ROOT/'scripts/octop_upgrade_probe.py'
s=p.read_text().replace('        "tests/test_terminal_socket_sessions.py",','        "tests/test_office_docx.py",\n        "tests/test_terminal_socket_sessions.py",',1)
anchor='    contract_paths = [\n'
s=s.replace(anchor,anchor+''.join('        '+repr(x)+',\n' for x in paths),1)
p.write_text(s)
subprocess.run([str(ROOT/'backend/.venv/bin/ruff'),'check','--fix',*paths],cwd=ROOT,check=True)
