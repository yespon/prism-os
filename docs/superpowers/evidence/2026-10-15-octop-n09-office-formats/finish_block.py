from pathlib import Path
import json,subprocess,sys
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
long=json.loads((HERE/'long-gates.json').read_text())
assert long['complete'] and all(code==0 for code in long['returncodes'].values())
for script in ['run_short_gates.py','complete_acceptance.py']:
    subprocess.run([sys.executable,str(HERE/script)],cwd=ROOT,check=True)
