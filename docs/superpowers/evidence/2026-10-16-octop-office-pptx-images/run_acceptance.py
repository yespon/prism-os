from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib,json,subprocess,sys
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
FILES=['tests/test_office_pptx_images.py','tests/test_office_docx_images.py','tests/test_office_chart_editing.py','tests/test_office_charts.py','tests/test_office_xlsx.py','tests/test_office_formats.py','tests/test_office_docx.py','tests/test_file_access_http.py']
def run(name, args, cwd='root'):
    subprocess.run([sys.executable,str(HERE/'run_validation.py'),'--cwd',cwd,name,'--',*args],cwd=ROOT,check=True)
def verify():
    for p,h in json.loads((HERE/'inputs.json').read_text())['sha256'].items():
        assert hashlib.sha256((ROOT/p).read_bytes()).hexdigest()==h,p
verify()
image=subprocess.check_output(['docker','image','inspect','prismos-office-chart-editing:test','--format','{{.Id}}'],text=True).strip()
def full():
    run('backend-full',['env','PRISMOS_SCOPED_TEST_IMAGE='+image,'.venv/bin/python','-m','pytest','tests/','-q','-o','faulthandler_timeout=120'],'backend')
def postgres():
    args=[sys.executable,'scripts/octop_skill_postgres.py','--output-dir','/tmp/prismos-office-pptx-images-pg-20261016']
    for name in FILES:args+=['--test-file',name]
    run('postgres',args)
    for src,dest in [('postgres.json','postgres.json'),('pytest.log','postgres-runtime.log')]:
        (HERE/dest).write_bytes((Path('/tmp/prismos-office-pptx-images-pg-20261016')/src).read_bytes())
def upgrade():
    args=[sys.executable,'scripts/octop_upgrade_probe.py','--previous-archive','/tmp/prismos-copy-share-upgrade/previous/upstream.tar.gz','--previous-receipt','/tmp/prismos-copy-share-upgrade/previous/manifest.json','--previous-revision','e473dd3c4a4741618ffde1a42a3492341a189e8e','--previous-release','0.3.0b5','--output',str(HERE/'upgrade.json')]
    for name in FILES:args+=['--test-file',name]
    run('upgrade',['env','PRISMOS_SCOPED_TEST_IMAGE='+image,*args])
results={}
with ThreadPoolExecutor(max_workers=2) as executor:
    futures={executor.submit(fn):name for name,fn in [('postgres',postgres),('upgrade',upgrade)]}
    for future in as_completed(futures):
        name=futures[future]
        try:future.result();results[name]=0
        except Exception as e:results[name]=str(e)
        print(json.dumps({'completed':name,'result':results[name]}),flush=True)
verify()
(HERE/'long-gates.json').write_text(json.dumps({'complete':True,'results':results,'inputs_unchanged':True},indent=2)+'\n')
assert all(result==0 for result in results.values())
