from pathlib import Path
import hashlib,json,subprocess,sys
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
v=json.loads((HERE/'validation.json').read_text())
assert v['backend']['unresolved_failures']==0
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
print('All raw logs staged byte-for-byte:',len(v['raw_log_sha256']),flush=True)
subprocess.run(['git','diff','--cached','--stat'],cwd=ROOT,check=True)
subprocess.run(['git','commit','-m','fix: enforce current account authority across native execution'],cwd=ROOT,check=True)
for relative,h in v['raw_log_sha256'].items():
    rel=(HERE/relative).relative_to(ROOT).as_posix()
    assert hashlib.sha256(subprocess.check_output(['git','show','HEAD:'+rel],cwd=ROOT)).hexdigest()==h
print('Committed logs verified:',len(v['raw_log_sha256']),flush=True)
subprocess.run(['git','status','--short'],cwd=ROOT,check=True)
subprocess.run(['git','log','-1','--oneline'],cwd=ROOT,check=True)
