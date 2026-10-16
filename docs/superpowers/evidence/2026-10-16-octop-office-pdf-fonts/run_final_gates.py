from pathlib import Path
from concurrent.futures import ThreadPoolExecutor,as_completed
import hashlib,json,subprocess,sys,os
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
os.environ['PRISMOS_OFFICE_FONT_CHECK']='/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc'
def run(args):subprocess.run(args,cwd=ROOT,check=True)
def gate(name,args,cwd='root'):run([sys.executable,str(HERE/'run_validation.py'),'--cwd',cwd,name,'--',*args])
def verify():
 for p,h in json.loads((HERE/'inputs-final.json').read_text())['sha256'].items():assert hashlib.sha256((ROOT/p).read_bytes()).hexdigest()==h,p
verify()
gate('static-final',['.venv/bin/ruff','check','packages/harness/deerflow/tools/builtins/office_fonts.py','packages/harness/deerflow/tools/builtins/office_pdf.py','tests/test_office_pdf_fonts.py','../scripts/octop_upgrade_probe.py'],'backend')
gate('collect-final',['.venv/bin/python','-m','pytest','tests/','--collect-only','-q'],'backend')
gate('demo-final',[sys.executable,str(HERE/'generate_final_demo.py')])
for name,args in [
 ('independent-pdf-reader-final',['pdftotext',str(HERE/'demo-chinese-final.pdf'),'-']),
 ('independent-font-embedding-final',['pdffonts',str(HERE/'demo-chinese-final.pdf')]),
 ('independent-pdf-render-final',['pdftoppm','-scale-to','1024','-singlefile','-png',str(HERE/'demo-chinese-final.pdf'),str(HERE/'demo-poppler-final')])]:gate(name,args)
def image():
 gate('backend-image-build-final',['docker','build','--progress','plain','-f','backend/Dockerfile','-t','prismos-office-pdf-fonts-final:test','.'])
 run([sys.executable,str(HERE/'run_final_image.py')])
def postgres():
 gate('postgres-final',[sys.executable,'scripts/octop_skill_postgres.py','--output-dir','/tmp/prismos-office-pdf-fonts-final-pg-20261016','--test-file','tests/test_office_pdf_fonts.py'])
 for src,dest in [('postgres.json','postgres-final.json'),('pytest.log','postgres-runtime-final.log')]:
  (HERE/dest).write_bytes((Path('/tmp/prismos-office-pdf-fonts-final-pg-20261016')/src).read_bytes())
 gate('upgrade-final',[sys.executable,'scripts/octop_upgrade_probe.py','--previous-archive','/tmp/prismos-copy-share-upgrade/previous/upstream.tar.gz','--previous-receipt','/tmp/prismos-copy-share-upgrade/previous/manifest.json','--previous-revision','e473dd3c4a4741618ffde1a42a3492341a189e8e','--previous-release','0.3.0b5','--output',str(HERE/'upgrade-final.json'),'--test-file','tests/test_office_pdf_fonts.py'])
results={}
with ThreadPoolExecutor(max_workers=2) as executor:
 futures={executor.submit(fn):name for name,fn in [('image',image),('pg-upgrade',postgres)]}
 for future in as_completed(futures):
  name=futures[future]
  try:future.result();results[name]=0
  except Exception as error:results[name]=str(error)
  print(json.dumps({'final_scope_completed':name,'result':results[name]}),flush=True)
verify()
(HERE/'final-phase.json').write_text(json.dumps({'complete':True,'results':results,'inputs_unchanged':True},indent=2)+'\n')
assert all(value==0 for value in results.values())
