from pathlib import Path
import json,subprocess,sys
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
def run(name,args):subprocess.run([sys.executable,str(HERE/'run_validation.py'),name,'--',sys.executable,*args],cwd=ROOT,check=True)
run('policy-change-synchronized',[str(HERE/'run_policy_change.py'),'--case','policy-change-synchronized'])
run('approval-policy-synchronized',[str(HERE/'run_approval_matrix.py'),'--case','approval-policy-synchronized','--scenarios','approve','restart'])
run('allow-policy-synchronized',[str(HERE/'run_case.py'),'allow','--case','allow-policy-synchronized'])
run('timeout-policy-synchronized',[str(HERE/'run_case.py'),'allow','--case','timeout-policy-synchronized','--provider-mode','timeout'])
(HERE/'policy-live-gates.json').write_text(json.dumps({'complete':True,'M1_exited':False},indent=2)+'\n')
