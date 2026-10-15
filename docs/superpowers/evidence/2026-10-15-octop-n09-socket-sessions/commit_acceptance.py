from pathlib import Path
import hashlib,json,subprocess,sys
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
v=json.loads((HERE/'validation.json').read_text())
assert subprocess.check_output(['git','branch','--show-current'],cwd=ROOT,text=True).strip()=='codex/octop-integration'
assert subprocess.check_output(['git','rev-parse','--short','HEAD'],cwd=ROOT,text=True).strip()=='f76e3eb'
assert all(hashlib.sha256((ROOT/p).read_bytes()).hexdigest()==h for p,h in json.loads((HERE/'inputs.json').read_text())['sha256'].items())
subprocess.run([sys.executable,str(HERE/'stage_evidence.py')],cwd=ROOT,check=True)
subprocess.run(['git','add','docs/superpowers/plans/2026-10-14-octop-functional-milestones.md'],cwd=ROOT,check=True)
subprocess.run(['git','diff','--cached','--check','--','.',':(exclude)**/*.log'],cwd=ROOT,check=True)
for relative,h in v['raw_log_sha256'].items():
    p=HERE/relative
    assert hashlib.sha256(p.read_bytes()).hexdigest()==h
    rel=p.relative_to(ROOT).as_posix()
    subprocess.run(['git','add','--force','--',rel],cwd=ROOT,check=True)
    assert hashlib.sha256(subprocess.check_output(['git','show',':'+rel],cwd=ROOT)).hexdigest()==h
subprocess.run(['git','commit','-q','-m','fix: enforce current sessions on terminal socket connections'],cwd=ROOT,check=True)
for relative,h in v['raw_log_sha256'].items():
    rel=(HERE/relative).relative_to(ROOT).as_posix()
    assert hashlib.sha256(subprocess.check_output(['git','show','HEAD:'+rel],cwd=ROOT)).hexdigest()==h
print('Committed raw logs verified:',len(v['raw_log_sha256']))
print(subprocess.check_output(['git','status','--short'],cwd=ROOT,text=True))
print(subprocess.check_output(['git','--no-pager','log','-1','--oneline'],cwd=ROOT,text=True))
