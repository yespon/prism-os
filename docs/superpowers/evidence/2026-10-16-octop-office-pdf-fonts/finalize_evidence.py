from pathlib import Path
import hashlib,json,re,tarfile
from PIL import Image
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def accepted(name):
 item=json.loads((HERE/(name+'-result.json')).read_text())
 assert item['complete'] and item['returncode']==0,name
for name in ['static-final','related-final','collect-full-scope','collect-scope-records','demo-final','backend-image-build-final','postgres-final','upgrade-final','image-runtime-final','independent-pdf-reader-final','independent-font-embedding-final','independent-pdf-render-final','map-budget-reproduction','table-budget-reproduction','backend-full-bounded']:accepted(name)
for name,key in [('bounded-phase.json','all_inputs_unchanged'),('final-phase.json','inputs_unchanged')]:
 phase=json.loads((HERE/name).read_text())
 assert phase['complete'] and phase[key] and all(value==0 for value in phase['results'].values())
inputs=json.loads((HERE/'inputs-final.json').read_text())['sha256']
for p,h in inputs.items():assert sha(ROOT/p)==h,p
scope=json.loads((HERE/'full-reuse-scope.json').read_text())
assert scope['unchanged_other_module_ast'] and scope['unchanged_original_font_test_ast'] and not scope['non_font_tests_supplying_optional_font_branch']
for p,h in scope['unchanged_input_sha256'].items():assert sha(ROOT/p)==h,p
reuse=json.loads((HERE/'historical-reuse.json').read_text())
for p,h in reuse['unchanged_inputs'].items():assert sha(ROOT/p)==h,p
for archive_name,receipt in [('source-initial.tar.gz','source-initial.json'),('source-before-table-budget.tar.gz','source-before-table-budget.json')]:
 old=json.loads((HERE/receipt).read_text())
 with tarfile.open(HERE/archive_name) as archive:
  members=archive.getmembers()
  assert {m.name for m in members}==set(old['sha256'])
  for member in members:assert member.isfile() and hashlib.sha256(archive.extractfile(member).read()).hexdigest()==old['sha256'][member.name]
up=json.loads((HERE/'upgrade-final.json').read_text())
assert up['complete'] and not up['host_changed'] and all(v['returncode']==0 for v in up['versions'])
image=json.loads((HERE/'image-proof-final.json').read_text())
assert image['container_removed'] and all(value['matches'] for value in image['files'].values())
for before,after in [('demo-chinese.png','demo-chinese-final.png'),('demo-poppler.png','demo-poppler-final.png')]:
 with Image.open(HERE/before) as old,Image.open(HERE/after) as new:assert old.size==new.size and old.convert('RGBA').tobytes()==new.convert('RGBA').tobytes()
reader=(HERE/'logs/independent-pdf-reader-final.log').read_text()
assert 'PrismOS 独立 PDF 中文字体' in reader and '季度预算：研发 120，验证 80' in reader
embedding=(HERE/'logs/independent-font-embedding-final.log').read_text()
assert 'WenQuanYiZenHei' in embedding and re.search(r'yes\s+no\s+yes',embedding)
def summary(name):
 text=(HERE/'logs'/(name+'.log')).read_text()
 return next(line for line in reversed(text.splitlines()) if re.search(r'\d+ passed',line))
full=summary('backend-full-bounded')
old_font=summary('related-bounded')
new_font=summary('related-final')
count=lambda text:int(re.search(r'(\d+) passed',text).group(1))
skipped=int(re.search(r'(\d+) skipped',full).group(1))
collection=json.loads((HERE/'collection-scope.json').read_text())
assert collection['returncode']==0
nodes=collection['nodes']
collection_skips=len(collection['skipped_collectors'])
assert collection_skips==1 and collection['skipped_collectors'][0]['nodeid']=='tests/test_client_live.py'
font_nodes=[node for node in nodes if node.startswith('tests/test_office_pdf_fonts.py::')]
assert len(font_nodes)==count(new_font)
base=count(full)-count(old_font)
assert len(nodes)+collection_skips==base+count(new_font)+skipped
report={'complete':True,'base_commit':'b6b886c','frozen_inputs':len(inputs),'historical_unchanged_inputs':len(reuse['unchanged_inputs']),'host_lock_sha256':sha(ROOT/'backend/uv.lock'),'image':image['image'],'image_file_matches':len(image['files']),'upgrade_inputs':len(up['host_contract_sha256s']),'M1_exited':False,'N08_started':False,'real_external_calls':False,'results':{'related-final':new_font,'backend-full-before-table-budget':full,'backend-composite':f'{base} unchanged non-font passed + {count(new_font)} current font passed = {base+count(new_font)} passed, {skipped} skipped; composite, not one new whole-suite run','image-runtime-final':summary('image-runtime-final'),'upgrade-final':[v['pytest'].splitlines()[-1] for v in up['versions']]},'composite':{'unchanged_non_font_passed':base,'current_font_passed':count(new_font),'passed':base+count(new_font),'skipped':skipped,'collected_current_nodes':len(nodes),'collection_module_skips':collection_skips,'current_font_nodes':font_nodes},'raw_log_sha256':{p.relative_to(ROOT).as_posix():sha(p) for p in sorted((HERE/'logs').glob('*.log'))},'additional_raw_sha256':{p.name:sha(p) for p in HERE.glob('postgres-runtime*.log')},'demo_sha256':{p.name:sha(p) for p in HERE.glob('demo-*') if p.suffix in {'.png','.pdf'}},'source_asset_sha256':{p.relative_to(ROOT).as_posix():sha(p) for p in (ROOT/'backend/tests/fixtures/pdf-fonts').glob('*') if p.is_file()},'preserved_archive_sha256':{p.name:sha(p) for p in HERE.glob('source-*.tar.gz')},'backend_full_faulthandler_notices':(HERE/'logs/backend-full-bounded.log').read_text().count('Timeout (0:02:00)!'),'final_demo':json.loads((HERE/'demo-final.json').read_text()),'final_native_and_poppler_pixels_equal_viewed_initial':True}
text=(HERE/'postgres-runtime-final.log').read_text()
report['results']['postgres-final']=next(line for line in reversed(text.splitlines()) if re.search(r'\d+ passed',line))
(HERE/'validation.json').write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n')
print(json.dumps(report['results']))
