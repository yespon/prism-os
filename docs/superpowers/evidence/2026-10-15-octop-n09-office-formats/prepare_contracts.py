from pathlib import Path
import subprocess
ROOT=Path(__file__).resolve().parents[4]
paths=['backend/packages/harness/deerflow/tools/builtins/office_common.py','backend/packages/harness/deerflow/tools/builtins/office_xlsx.py','backend/packages/harness/deerflow/tools/builtins/office_pptx.py','backend/packages/harness/deerflow/tools/builtins/office_pdf.py','backend/tests/test_office_xlsx.py','backend/tests/test_office_formats.py']
p=ROOT/'.github/workflows/octop-integration.yml'
s=p.read_text()
covered=s.split('uv run --locked ruff check',1)[1].split('      - name:',1)[0].split()
extra=[x.removeprefix('backend/') for x in paths if x.removeprefix('backend/') not in covered]
s=s.replace('uv run --locked ruff check','uv run --locked ruff check '+' '.join(extra),1)
p.write_text(s)
p=ROOT/'scripts/octop_upgrade_probe.py'
s=p.read_text().replace('        "tests/test_office_docx.py",','        "tests/test_office_xlsx.py",\n        "tests/test_office_formats.py",\n        "tests/test_office_docx.py",',1)
anchor='    contract_paths = [\n'
add=[x for x in paths+['backend/packages/harness/pyproject.toml','backend/uv.lock'] if repr(x) not in s and '"'+x+'"' not in s]
s=s.replace(anchor,anchor+''.join('        '+repr(x)+',\n' for x in add),1)
p.write_text(s)
subprocess.run([str(ROOT/'backend/.venv/bin/ruff'),'check',*paths,'backend/tests/test_office_docx.py'],cwd=ROOT,check=True)
