from pathlib import Path
import hashlib,json,re,subprocess,tomllib
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
BASE=HERE.parent/'2026-10-15-octop-n09-office-docx'
def read(p): return json.loads((HERE/p).read_text())
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def stats(p):
    line=[x for x in (HERE/p).read_text().splitlines() if re.search(r'\d+ passed',x)][-1]
    return {'summary':line,'passed':int(re.search(r'(\d+) passed',line)[1]),'skipped':int(re.search(r'(\d+) skipped',line)[1]) if ' skipped' in line else 0}
gates=['formats-current-authority','postgres','dependencies','source-verify','external-verify','inventory-generate','inventory-verify','distribution-verify','static','backend-image-build','image-runtime','backend-full','upgrade','brand-staged','demo']
for name in gates:
    d=read(name+'-result.json'); assert d['complete'] and d['returncode']==0,name
inputs=read('inputs.json')['sha256']; assert all(sha(ROOT/p)==h for p,h in inputs.items())
b=read('backend-driver.json'); assert b['complete'] and b['returncode']==0 and b['all_inputs_unchanged']
image=read('image-proof.json'); assert image['backend_image']==b['backend_image'] and image['owned_test_container_removed']
assert all(entry['matches'] and sha(ROOT/p)==entry['sha256'] for p,entry in image['files'].items())
pg=read('postgres.json'); assert pg['passed'] and pg['returncode']==0 and pg['owned_container_removed']
u=read('upgrade.json'); assert u['complete'] and u['host_changed'] is False and len(u['versions'])==3 and all(x['returncode']==0 for x in u['versions'])
base=json.loads((BASE/'validation.json').read_text())
previous=json.loads((BASE/'inputs-bounded.json').read_text())['sha256']
front={p:h for p,h in previous.items() if p.startswith('frontend/')}; assert all(inputs[p]==h for p,h in front.items())
service=base['service_image_reuse']; assert all(sha(ROOT/p)==h for p,h in service['sha256'].items())
old_source=base['source_distribution_inventory_reuse']['sha256']
source_changed={p:{'previous':h,'current':sha(ROOT/p)} for p,h in old_source.items() if sha(ROOT/p)!=h}
assert set(source_changed).issubset({'backend/uv.lock','docs/superpowers/evidence/2026-10-10-octop-n06-presentation/inventory/dependencies.json'}),source_changed
source={'sha256':{p:sha(ROOT/p) for p in old_source},'unchanged_sha256':{p:h for p,h in old_source.items() if p not in source_changed},'changed_inputs':source_changed,'scope':'unchanged bytes retain previous exact historical scope; current source/external/distribution/inventory gates newly run; current lock additionally verified by locked offline sync, image build and complete backend; no old lock/inventory conclusion reused'}
inventory_path='docs/superpowers/evidence/2026-10-10-octop-n06-presentation/inventory/dependencies.json'
source['sha256'][inventory_path]=sha(ROOT/inventory_path)
source['current_generated_inventory']={'path':inventory_path,'sha256':sha(ROOT/inventory_path),'scope':'derived artifact newly generated/verified from current frozen host lock and retained source; historical inventory conclusion not reused'}
old_lock=tomllib.loads(subprocess.check_output(['git','show','f7ca429:backend/uv.lock'],cwd=ROOT,text=True))
new_lock=tomllib.loads((ROOT/'backend/uv.lock').read_text())
versions=lambda value:{p['name']:p.get('version') for p in value['package']}
assert versions(old_lock)==versions(new_lock)
deps={'explicit_pins':{'openpyxl':'3.1.5','python-pptx':'1.0.2','pypdfium2':'5.3.0'},'package_versions_unchanged':True,'locked_offline_sync_passed':True,'changes':{}}
for p in ['backend/uv.lock','backend/packages/harness/pyproject.toml']:
    deps['changes'][p]={'previous':hashlib.sha256(subprocess.check_output(['git','show','f7ca429:'+p],cwd=ROOT)).hexdigest(),'current':sha(ROOT/p)}
demo=read('demo.json'); assert all(sha(HERE/p)==entry['sha256'] for p,entry in demo['files'].items())
logs=sorted((HERE/'logs').glob('*.log'))+[HERE/'postgres-runtime.log']
v={'base_commit':'f7ca429','branch':'codex/octop-integration','status':'independent_XLSX_PPTX_PDF_baselines_accepted_full_Office_M1_pending','backend':stats('logs/backend-full.log'),'related':stats('logs/formats-current-authority.log'),'postgres':stats('postgres-runtime.log')|{'actual_scope':'owned actual PostgreSQL original tenant/member/thread/Agent facts; Auth User rows in explicitly owned SQLite store; real Office binary formats and HTTP downloads, no real model/deployment','owned_container_removed':True},'image':image,'image_tests':stats('logs/image-runtime.log'),'upgrade':{'complete':True,'host_changed':False,'host_inputs':len(u['host_contract_sha256s']),'stages':[x['pytest'].splitlines()[-1] for x in u['versions']]},'input_count':len(inputs),'frontend_reuse':{'base_commit':'f7ca429','unchanged_input_count':len(front),'scope':base['frontend_reuse']},'source_distribution_inventory_reuse':source,'service_image_reuse':service,'dependency_change':deps,'demo':demo,'boundaries':['M1 not exited; N08 not started','Office baselines only: full fidelity Word/Excel/PowerPoint, pivot/chart calculation, desktop render, Unicode PDF font embedding/OCR/forms remain pending','PDF text creation rejects unsupported Unicode rather than emitting missing glyphs; no OCR/form execution or real model claim','old DOCX post-publish fixture proved generic unknown only; corrected current fixture changes and reads actual inactive membership; original historical warnings retained','real model/tool/countable ticket, real SSH/Kubernetes/Browser/Apple, generic Secret, delegated lifecycle and remote CI pending','all original N/O/F and PrismOS goals/gates retained; no push/deploy/release'],'raw_log_sha256':{p.relative_to(HERE).as_posix():sha(p) for p in logs}}
(HERE/'validation.json').write_text(json.dumps(v,indent=2)+'\n')
print(json.dumps({k:v[k] for k in ['status','backend','postgres','image_tests','upgrade','input_count','dependency_change']}))
