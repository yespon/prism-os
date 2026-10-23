from pathlib import Path
import subprocess,sys
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
paths=['.github/workflows/octop-integration.yml','scripts/octop_upgrade_probe.py','backend/uv.lock','backend/packages/harness/pyproject.toml','backend/packages/harness/deerflow/tools/builtins/office_common.py','backend/packages/harness/deerflow/tools/builtins/office_xlsx.py','backend/packages/harness/deerflow/tools/builtins/office_pptx.py','backend/packages/harness/deerflow/tools/builtins/office_pdf.py','backend/packages/harness/deerflow/tools/tools.py','backend/tests/test_office_xlsx.py','backend/tests/test_office_formats.py','backend/tests/test_office_docx.py','docs/superpowers/evidence/2026-10-10-octop-n06-presentation/inventory',HERE.relative_to(ROOT).as_posix()]
for p in HERE.glob('*.py'): p.write_text(p.read_text().rstrip()+'\n')
subprocess.run(['git','add',*paths],cwd=ROOT,check=True)
if not (HERE/'brand-staged-result.json').exists():
    subprocess.run([sys.executable,str(HERE/'run_validation.py'),'brand-staged','--',sys.executable,'scripts/check_brand_identity.py'],cwd=ROOT,check=True)
subprocess.run(['git','diff','--cached','--check','--','.',':(exclude)**/*.log'],cwd=ROOT,check=True)
print('Frozen Office formats staged; final complete gate receipts required before commit')
