from pathlib import Path
import json,subprocess,sys
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
def run(name,args):subprocess.run([sys.executable,str(HERE/'run_validation.py'),name,'--',sys.executable,*args],cwd=ROOT,check=True)
run('policy-change-current',[str(HERE/'run_policy_change.py'),'--case','policy-change-current'])
run('approval-policy-current',[str(HERE/'run_approval_matrix.py'),'--case','approval-policy-current','--scenarios','approve','restart'])
run('allow-policy-current',[str(HERE/'run_case.py'),'allow','--case','allow-policy-current'])
run('timeout-policy-current',[str(HERE/'run_case.py'),'allow','--case','timeout-policy-current','--provider-mode','timeout'])
(HERE/'policy-live-gates.json').write_text(json.dumps({'complete':True,'M1_exited':False},indent=2)+'\n')
