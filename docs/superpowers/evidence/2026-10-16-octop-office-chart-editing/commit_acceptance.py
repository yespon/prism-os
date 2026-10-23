from pathlib import Path
import hashlib,json,subprocess,sys
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
def run(args,**kwargs):return subprocess.run(args,cwd=ROOT,check=True,**kwargs)
assert subprocess.check_output(['git','rev-parse','--short','HEAD'],cwd=ROOT,text=True).strip()=='630a5f1'
run([sys.executable,str(HERE/'finalize_evidence.py')])
run([sys.executable,str(HERE/'render_report.py')])
paths=['backend/packages/harness/deerflow/tools/builtins/office_pptx.py','backend/tests/test_office_chart_editing.py','scripts/octop_upgrade_probe.py','.github/workflows/octop-integration.yml','docs/superpowers/plans/2026-10-09-octop-next-iterations.md','docs/superpowers/plans/2026-10-14-octop-functional-milestones.md',HERE.relative_to(ROOT).as_posix()]
run(['git','add',*paths])
run([sys.executable,str(HERE/'run_validation.py'),'brand-staged','--',sys.executable,'scripts/check_brand_identity.py'])
assert json.loads((HERE/'brand-staged-result.json').read_text())['returncode']==0
run([sys.executable,str(HERE/'finalize_evidence.py')])
report=json.loads((HERE/'validation.json').read_text())
raw=dict(report['raw_log_sha256'])
raw.update({(HERE/name).relative_to(ROOT).as_posix():value for name,value in report['additional_raw_sha256'].items()})
raw.update({(HERE/name).relative_to(ROOT).as_posix():value for name,value in report['demo_sha256'].items()})
run(['git','add',HERE.relative_to(ROOT).as_posix()])
run(['git','add','-f',*raw])
for path,value in raw.items():assert hashlib.sha256(subprocess.check_output(['git','show',':'+path],cwd=ROOT)).hexdigest()==value,path
run(['git','diff','--cached','--check','--','.',':(exclude)**/*.log'])
run(['git','commit','-q','-m','feat(office): support governed presentation chart data editing'])
for path,value in raw.items():assert hashlib.sha256(subprocess.check_output(['git','show','HEAD:'+path],cwd=ROOT)).hexdigest()==value,path
print('Committed:',subprocess.check_output(['git','rev-parse','--short','HEAD'],cwd=ROOT,text=True).strip(),'raw logs/demos preserved:',len(raw))
