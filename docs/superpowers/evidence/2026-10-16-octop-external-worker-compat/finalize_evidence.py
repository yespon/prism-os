from pathlib import Path
import hashlib,json,subprocess
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
for name in ['resolve-public-index','build-worker','mcp-compat','related-final','ci-static-corrected','image-dependencies','upgrade-final','prepare-final']:
    result=json.loads((HERE/(name+'-result.json')).read_text())
    assert result['complete'] and result['returncode']==0,name
up=json.loads((HERE/'upgrade-final.json').read_text())
assert up['complete'] and not up['host_changed'] and all(v['returncode']==0 for v in up['versions'])
for p,h in up['host_contract_sha256s'].items():assert sha(ROOT/p)==h,p
old=json.loads((HERE/'historical-reuse.json').read_text())
for p,h in old['unchanged_inputs'].items():assert sha(ROOT/p)==h,p
mcp=json.loads((HERE/'mcp-compat.json').read_text())
assert mcp['complete'] and mcp['container_removed'] and mcp['host_lock_unchanged']
assert sha(ROOT/'backend/uv.lock')==mcp['host_lock_sha256']
inputs=json.loads((HERE/'inputs.json').read_text())
inputs['sha256']={p:sha(ROOT/p) for p in inputs['sha256']}
(HERE/'inputs.json').write_text(json.dumps(inputs,indent=2)+'\n')
report={'complete':True,'upgrade_inputs':len(up['host_contract_sha256s']),'historical_unchanged_inputs':len(old['unchanged_inputs']),'actual_remote_ci':False,'M1_exited':False,'raw_log_sha256':{p.relative_to(ROOT).as_posix():sha(p) for p in sorted((HERE/'logs').glob('*.log'))},'worker_input_sha256':{p.relative_to(ROOT).as_posix():sha(p) for p in sorted((ROOT/'docker/octop-worker-compat').glob('*')) if p.is_file()}}
(HERE/'validation.json').write_text(json.dumps(report,indent=2)+'\n')
paths=['scripts/octop_worker_compat.py','scripts/octop_worker_probe.py','scripts/octop_upgrade_probe.py','backend/tests/test_octop_worker_compat.py','docker/octop-worker-compat','.github/workflows/octop-integration.yml','docs/superpowers/plans/2026-10-09-octop-next-iterations.md','docs/superpowers/plans/2026-10-14-octop-functional-milestones.md',HERE.relative_to(ROOT).as_posix()]
subprocess.run(['git','add',*paths],cwd=ROOT,check=True)
subprocess.run(['git','add','-f',*report['raw_log_sha256']],cwd=ROOT,check=True)
for p,h in report['raw_log_sha256'].items():
    assert hashlib.sha256(subprocess.check_output(['git','show',':'+p],cwd=ROOT)).hexdigest()==h,p
subprocess.run(['git','diff','--cached','--check','--','.',':(exclude)**/*.log'],cwd=ROOT,check=True)
print(json.dumps({'accepted':True,'raw_logs_staged_byte_identical':len(report['raw_log_sha256']),'historical_inputs_verified':len(old['unchanged_inputs'])}))
