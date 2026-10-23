from pathlib import Path
import json,subprocess,sys
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
def run(name,args):subprocess.run([sys.executable,str(HERE/'run_validation.py'),name,'--',sys.executable,*args],cwd=ROOT,check=True)
run('approval-counter-v2',[str(HERE/'run_approval_matrix.py'),'--case','approval-counter-v2'])
run('allow-counter-v2',[str(HERE/'run_case.py'),'allow','--case','allow-counter-v2'])
run('timeout-counter-v2',[str(HERE/'run_case.py'),'allow','--case','timeout-counter-v2','--provider-mode','timeout'])
(HERE/'receiver-v2-model-gates.json').write_text(json.dumps({'complete':True,'M1_exited':False},indent=2)+'\n')
