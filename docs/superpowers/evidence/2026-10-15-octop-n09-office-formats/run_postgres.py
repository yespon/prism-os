from pathlib import Path
import subprocess,sys
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
files=['tests/test_office_xlsx.py','tests/test_office_formats.py','tests/test_office_docx.py','tests/test_file_access_http.py']
args=[sys.executable,'scripts/octop_skill_postgres.py','--output-dir','/tmp/prismos-office-formats-postgres-20261015']
for name in files: args+=['--test-file',name]
subprocess.run([sys.executable,str(HERE/'run_validation.py'),'postgres','--',*args],cwd=ROOT,check=True)
