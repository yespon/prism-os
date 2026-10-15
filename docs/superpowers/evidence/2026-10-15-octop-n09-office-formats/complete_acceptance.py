from pathlib import Path
import json,subprocess,sys,time
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
while True:
    result=json.loads((HERE/'backend-full-result.json').read_text())
    if result.get('complete'):
        assert result['returncode']==0,result
        break
    time.sleep(5)
assert json.loads((HERE/'backend-driver.json').read_text())['all_inputs_unchanged']
for script in ['stage_evidence.py','finalize_evidence.py','render_report.py','commit_acceptance.py']:
    subprocess.run([sys.executable,str(HERE/script)],cwd=ROOT,check=True)
