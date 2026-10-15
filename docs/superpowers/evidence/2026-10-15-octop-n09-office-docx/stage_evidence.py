from pathlib import Path
import subprocess,sys
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
paths=['.github/workflows/octop-integration.yml','scripts/octop_upgrade_probe.py','backend/packages/harness/deerflow/tools/builtins/office_docx.py','backend/tests/test_office_docx.py','backend/packages/harness/deerflow/sandbox/file_access.py','backend/packages/harness/deerflow/tools/tools.py','backend/app/integrations/file_access.py',HERE.relative_to(ROOT).as_posix()]
for p in HERE.glob('*.py'): p.write_text(p.read_text().rstrip()+'\n')
subprocess.run(['git','add',*paths],cwd=ROOT,check=True)
if not (HERE/'brand-bounded-result.json').exists():
    subprocess.run([sys.executable,str(HERE/'run_validation.py'),'brand-bounded','--',sys.executable,'scripts/check_brand_identity.py'],cwd=ROOT,check=True)
subprocess.run(['git','diff','--cached','--check','--','.',':(exclude)**/*.log'],cwd=ROOT,check=True)
print('Frozen session feature staged; final complete gate receipts required before commit')
