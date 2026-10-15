from pathlib import Path
import subprocess,sys
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
subprocess.run([sys.executable,str(HERE/'run_validation.py'),'postgres','--',sys.executable,'scripts/octop_skill_postgres.py','--output-dir','/tmp/prismos-office-docx-postgres-20261015','--test-file','tests/test_office_docx.py','--test-file','tests/test_file_access_boundaries.py','--test-file','tests/test_file_access_http.py'],cwd=ROOT,check=True)
