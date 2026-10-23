from pathlib import Path
import hashlib,json,re
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
for name in ['related','static','demo','backend-image-build','postgres','upgrade','image-runtime']:
 result=json.loads((HERE/(name+'-result.json')).read_text());assert result['complete'] and result['returncode']==0,name
long=json.loads((HERE/'long-gates.json').read_text());assert long['complete'] and long['inputs_unchanged'] and all(v==0 for v in long['results'].values())
inputs=json.loads((HERE/'inputs.json').read_text())['sha256']
for p,h in inputs.items():assert sha(ROOT/p)==h,p
reuse=json.loads((HERE/'historical-reuse.json').read_text())
for p,h in reuse['unchanged_inputs'].items():assert sha(ROOT/p)==h,p
up=json.loads((HERE/'upgrade.json').read_text());assert up['complete'] and not up['host_changed'] and all(v['returncode']==0 for v in up['versions'])
image=json.loads((HERE/'image-proof.json').read_text());assert image['container_removed'] and all(v['matches'] for v in image['files'].values())
report={'complete':True,'base_commit':'0ba4466','frozen_inputs':len(inputs),'historical_unchanged_inputs':len(reuse['unchanged_inputs']),'host_lock_sha256':sha(ROOT/'backend/uv.lock'),'image':image['image'],'upgrade_inputs':len(up['host_contract_sha256s']),'M1_exited':False,'N08_started':False,'remote_ci_executed':False,'whole_backend_rerun':False,'results':{},'raw_log_sha256':{p.relative_to(ROOT).as_posix():sha(p) for p in sorted((HERE/'logs').glob('*.log'))},'additional_raw_sha256':{'postgres-runtime.log':sha(HERE/'postgres-runtime.log')},'demo_sha256':{p.name:sha(p) for p in HERE.glob('demo-*') if p.suffix in {'.pptx','.png'}}}
for name,path in [('related',HERE/'logs/related.log'),('image-runtime',HERE/'logs/image-runtime.log'),('postgres',HERE/'postgres-runtime.log')]:
 report['results'][name]=next(line for line in reversed(path.read_text().splitlines()) if re.search(r'\d+ passed',line))
report['results']['upgrade']=[v['pytest'].splitlines()[-1] for v in up['versions']]
(HERE/'validation.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report['results']))
