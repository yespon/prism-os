from pathlib import Path
import py_compile,subprocess,sys
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
for name in ['finalize_evidence.py','render_report.py','commit_acceptance.py','complete_acceptance.py']:
    py_compile.compile(str(HERE/name),doraise=True)
subprocess.run([sys.executable,str(HERE/'run_validation.py'),'demo','--',sys.executable,str(HERE/'generate_demo.py')],cwd=ROOT,check=True)
subprocess.run([sys.executable,str(HERE/'stage_evidence.py')],cwd=ROOT,check=True)
