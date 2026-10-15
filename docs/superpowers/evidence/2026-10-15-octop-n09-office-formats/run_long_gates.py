from pathlib import Path
from concurrent.futures import ThreadPoolExecutor,as_completed
import json,subprocess,sys
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
def run(script):
    result=subprocess.run([sys.executable,str(HERE/script)],cwd=ROOT)
    return script,result.returncode
results={}
with ThreadPoolExecutor(max_workers=2) as executor:
    for future in as_completed([executor.submit(run,name) for name in ['run_full.py','run_upgrade.py']]):
        name,code=future.result()
        results[name]=code
        print(json.dumps({'completed':name,'returncode':code}),flush=True)
(HERE/'long-gates.json').write_text(json.dumps({'complete':True,'returncodes':results},indent=2)+'\n')
raise SystemExit(0 if all(code==0 for code in results.values()) else 1)
