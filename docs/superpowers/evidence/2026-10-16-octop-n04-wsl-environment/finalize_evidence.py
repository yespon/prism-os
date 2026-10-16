from pathlib import Path
import hashlib,json,subprocess
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
for name in ['init','up','health','receiver-tests-final','receiver-runtime-final','backup','restart','static-final','upgrade']:
 r=json.loads((HERE/(name+'-result.json')).read_text());assert r['complete'] and r['returncode']==0,name
inputs=json.loads((HERE/'inputs.json').read_text())['sha256']
for p,h in inputs.items():assert sha(ROOT/p)==h,p
up=json.loads((HERE/'upgrade.json').read_text());assert up['complete'] and not up['host_changed'] and all(v['returncode']==0 for v in up['versions'])
proof=json.loads((HERE/'deployment-proof.json').read_text());assert proof['receiver_count_survived_restart'] and proof['runtime_git_ignored']
report={'base_commit':'645fb42','complete_local_environment_block':True,'M1_exited':False,'real_model_verified':False,'N08_started':False,'remote_ci_executed':False,'frozen_inputs':len(inputs),'unchanged_historical_inputs':2045,'current_image':proof['services']['gateway']['image'],'upgrade_inputs':len(up['host_contract_sha256s']),'upgrade_results':[v['pytest'].splitlines()[-1] for v in up['versions']],'tests':(HERE/'logs/receiver-tests-final.log').read_text().splitlines()[-1],'raw_log_sha256':{p.relative_to(ROOT).as_posix():sha(p) for p in (HERE/'logs').glob('*.log')}}
# Only verify the known local runtime secret values against exported evidence; never output them.
state=ROOT/'backend/tmp/n04-wsl'
protected=[(state/'receiver/receiver-token').read_bytes().strip(),(state/'receiver/server.key').read_bytes()]
protected += [line.split(b'=',1)[1] for line in (state/'runtime.env').read_bytes().splitlines() if b'=' in line]
for p in HERE.rglob('*'):
 if p.is_file():
  data=p.read_bytes()
  assert all(secret not in data for secret in protected if secret),p.name
report['known_runtime_secret_export_check']='passed'
(HERE/'validation.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({k:v for k,v in report.items() if k!='raw_log_sha256'}))
