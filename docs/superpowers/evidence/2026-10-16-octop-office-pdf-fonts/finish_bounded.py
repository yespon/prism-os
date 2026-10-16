from pathlib import Path
from concurrent.futures import ThreadPoolExecutor,as_completed
import hashlib,json,shutil,subprocess,sys,time
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
def run(args):subprocess.run(args,cwd=ROOT,check=True)
def gate(name,args,cwd='root'):
 run([sys.executable,str(HERE/'run_validation.py'),'--cwd',cwd,name,'--',*args])
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
print('Waiting for actual initial full/PG/upgrade terminal results before applying combined cmap budget',flush=True)
while True:
 try:state=json.loads((HERE/'long-gates.json').read_text())
 except (FileNotFoundError,json.JSONDecodeError):time.sleep(2);continue
 assert state['complete'] and state['inputs_unchanged'] and all(v==0 for v in state['results'].values()),state
 break
print('Initial actual gates complete; applying reproduced map budget fix within same font block',flush=True)
initial=json.loads((HERE/'inputs-initial.json').read_text())
for p,h in initial['sha256'].items():assert sha(ROOT/p)==h,p
module=ROOT/'backend/packages/harness/deerflow/tools/builtins/office_fonts.py'
tests=ROOT/'backend/tests/test_office_pdf_fonts.py'
module.write_bytes((ROOT/'backend/tmp/office_fonts_bounded_candidate.py').read_bytes())
name='test_combined_character_maps_have_one_total_budget_before_native_parse'
assert name not in tests.read_text()
with tests.open('a') as stream:stream.write('\n'+(HERE/'map_budget_regression.py').read_text())
run([str(ROOT/'backend/.venv/bin/ruff'),'format','--config',str(ROOT/'backend/ruff.toml'),str(module),str(tests)])
current={p:sha(ROOT/p) for p in initial['sha256']}
assert {p for p,h in initial['sha256'].items() if current[p]!=h}=={module.relative_to(ROOT).as_posix(),tests.relative_to(ROOT).as_posix()}
(HERE/'inputs-bounded.json').write_text(json.dumps({'base_commit':'b6b886c','scope':'Final combined-map-bounded font implementation; initial evidence kept separately','sha256':current},indent=2)+'\n')
s=(HERE/'run_acceptance.py').read_text().replace("'inputs.json'","'inputs-bounded.json'").replace("'long-gates.json'","'long-gates-bounded.json'").replace("name,'--'","name+'-bounded','--'").replace('/tmp/prismos-office-pdf-fonts-pg-20261016','/tmp/prismos-office-pdf-fonts-pg-bounded-20261016').replace("('postgres.json','postgres.json'),('pytest.log','postgres-runtime.log')","('postgres.json','postgres-bounded.json'),('pytest.log','postgres-runtime-bounded.log')").replace("HERE/'upgrade.json'","HERE/'upgrade-bounded.json'")
(HERE/'run_bounded_acceptance.py').write_text(s)
s=(HERE/'run_image_runtime.py').read_text().replace("'inputs.json'","'inputs-bounded.json'").replace("'backend-image-build-result.json'","'backend-image-build-bounded-result.json'").replace('prismos-office-pdf-fonts:test','prismos-office-pdf-fonts-bounded:test').replace("'image-runtime'","'image-runtime-bounded'").replace("'image-proof.json'","'image-proof-bounded.json'")
(HERE/'run_bounded_image.py').write_text(s)
s=(HERE/'generate_demo.py').read_text().replace('demo-chinese.pdf','demo-chinese-bounded.pdf').replace('demo-chinese.png','demo-chinese-bounded.png').replace("HERE/'demo.json'","HERE/'demo-bounded.json'")
(HERE/'generate_bounded_demo.py').write_text(s)
gate('static-bounded',['.venv/bin/ruff','check','packages/harness/deerflow/tools/builtins/office_fonts.py','packages/harness/deerflow/tools/builtins/office_pdf.py','tests/test_office_pdf_fonts.py','../scripts/octop_upgrade_probe.py'],'backend')
gate('related-bounded',['env','PRISMOS_OFFICE_FONT_CHECK=/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc','.venv/bin/python','-m','pytest','tests/test_office_pdf_fonts.py','-q'],'backend')
gate('demo-bounded',[sys.executable,str(HERE/'generate_bounded_demo.py')])
for name,args in [
 ('independent-pdf-reader-bounded',['pdftotext',str(HERE/'demo-chinese-bounded.pdf'),'-']),
 ('independent-font-embedding-bounded',['pdffonts',str(HERE/'demo-chinese-bounded.pdf')]),
 ('independent-pdf-render-bounded',['pdftoppm','-scale-to','1024','-singlefile','-png',str(HERE/'demo-chinese-bounded.pdf'),str(HERE/'demo-poppler-bounded')])]:gate(name,args)
from PIL import Image
with Image.open(HERE/'demo-chinese.png') as before,Image.open(HERE/'demo-chinese-bounded.png') as after:
 assert before.size==after.size and before.tobytes()==after.tobytes()
(HERE/'visual-review.json').write_text(json.dumps({'native_pdfium_initial_viewed':True,'independent_poppler_initial_viewed':True,'four_intended_Chinese_lines_legible_without_missing_glyph_boxes':True,'final_native_pixels_equal_initial_viewed_pixels':True,'final_native_png_sha256':sha(HERE/'demo-chinese-bounded.png'),'final_poppler_png_sha256':sha(HERE/'demo-poppler-bounded.png')},indent=2)+'\n')
def image_runtime():
 gate('backend-image-build-bounded',['docker','build','--progress','plain','-f','backend/Dockerfile','-t','prismos-office-pdf-fonts-bounded:test','.'])
 run([sys.executable,str(HERE/'run_bounded_image.py')])
def long_gates():run([sys.executable,str(HERE/'run_bounded_acceptance.py')])
results={}
with ThreadPoolExecutor(max_workers=2) as executor:
 futures={executor.submit(fn):name for name,fn in [('image',image_runtime),('backend-pg-upgrade',long_gates)]}
 for future in as_completed(futures):
  name=futures[future]
  try:future.result();results[name]=0
  except Exception as error:results[name]=str(error)
  print(json.dumps({'bounded_phase_completed':name,'result':results[name]}),flush=True)
for p,h in current.items():assert sha(ROOT/p)==h,p
(HERE/'bounded-phase.json').write_text(json.dumps({'complete':True,'results':results,'all_inputs_unchanged':True},indent=2)+'\n')
assert all(value==0 for value in results.values())
print('Final bounded font gates complete; evidence/brand/commit still required',flush=True)
