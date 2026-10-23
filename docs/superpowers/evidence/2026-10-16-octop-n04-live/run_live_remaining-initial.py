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
run('allow-current',[str(HERE/'run_case.py'),'allow','--case','allow-current'])
run('approval-matrix',[str(HERE/'run_approval_matrix.py')])
run('provider-failure-current',[str(HERE/'run_case.py'),'allow','--case','provider-failure-current','--provider-mode','fail'])
run('provider-timeout-current',[str(HERE/'run_case.py'),'allow','--case','provider-timeout-current','--provider-mode','timeout'])
verify()
(HERE/'live-gates.json').write_text(json.dumps({'complete':True,'inputs_unchanged':True,'M1_exited':False},indent=2)+'\n')
