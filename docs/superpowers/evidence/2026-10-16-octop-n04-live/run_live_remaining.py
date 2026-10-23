from pathlib import Path
import hashlib,json,subprocess,sys
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
inputs=json.loads((HERE/'inputs.json').read_text())['sha256']
def verify():
 for p,h in inputs.items():assert hashlib.sha256((ROOT/p).read_bytes()).hexdigest()==h,p
def run(name,args):
 subprocess.run([sys.executable,str(HERE/'run_validation.py'),name,'--',sys.executable,*args],cwd=ROOT,check=True)
verify()
assert json.loads((HERE/'allow-current.json').read_text())['complete']
previous=json.loads((HERE/'approval-matrix.json').read_text())
assert {c['scenario'] for c in previous['cases'] if c['complete']}=={'approve','reject','revoke_agent'}
run('approval-remaining',[str(HERE/'run_approval_matrix.py'),'--case','approval-remaining','--scenarios','withdraw_secret','rotate_secret','restart'])
run('provider-failure-current',[str(HERE/'run_case.py'),'allow','--case','provider-failure-current','--provider-mode','fail'])
run('provider-timeout-current',[str(HERE/'run_case.py'),'allow','--case','provider-timeout-current','--provider-mode','timeout'])
verify()
(HERE/'live-gates.json').write_text(json.dumps({'complete':True,'inputs_unchanged':True,'M1_exited':False},indent=2)+'\n')
