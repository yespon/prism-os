from pathlib import Path
import hashlib,json,subprocess,sys,tempfile,uuid
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def verify():
    for p,h in json.loads((HERE/'inputs-final.json').read_text())['sha256'].items():assert sha(ROOT/p)==h,p
verify()
assert json.loads((HERE/'backend-image-build-final-result.json').read_text())['returncode']==0
image=subprocess.check_output(['docker','image','inspect','prismos-office-pdf-fonts-final:test','--format','{{.Id}}'],text=True).strip()
files=['packages/harness/deerflow/tools/builtins/office_fonts.py','tests/test_office_pdf_fonts.py','tests/fixtures/pdf-fonts/NotoMono-Regular.ttf','tests/fixtures/pdf-fonts/copyright.txt','tests/fixtures/pdf-fonts/provenance.json','packages/harness/deerflow/tools/builtins/office_xlsx.py','packages/harness/deerflow/tools/builtins/office_pptx.py','packages/harness/deerflow/tools/builtins/office_common.py','tests/test_office_charts.py','tests/test_office_xlsx.py','tests/test_office_formats.py','tests/test_office_docx.py','tests/test_file_access_http.py','uv.lock','packages/harness/pyproject.toml']
font=Path('/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc')
assert sha(font)==json.loads((HERE/'demo.json').read_text())['font']['sha256']
proof={'readonly_test_font_mount':{'sha256':sha(font),'target':'/tmp/prismos-test-font.ttc','scope':'Public system test font only; original native API reads copied owned thread upload'},'image':image,'files':{},'network':'none','default_privileges':True}
container=subprocess.check_output(['docker','create',image],text=True).strip()
try:
    with tempfile.TemporaryDirectory(prefix='prismos-chart-image-proof-') as folder:
        for index,p in enumerate(files):
            target=Path(folder)/str(index)
            subprocess.run(['docker','cp',container+':/app/backend/'+p,str(target)],check=True,capture_output=True)
            assert sha(target)==sha(ROOT/'backend'/p),p
            proof['files']['backend/'+p]={'sha256':sha(target),'matches':True}
finally:subprocess.run(['docker','rm',container],check=True,capture_output=True)
name='prismos-office-pdf-fonts-'+uuid.uuid4().hex[:12]
try:
    subprocess.run([sys.executable,str(HERE/'run_validation.py'),'image-runtime-final','--','docker','run','--rm','--network','none','--memory','1g','--cpus','2','--pids-limit','256','--name',name,'--mount','type=bind,source=/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc,target=/tmp/prismos-test-font.ttc,readonly','-e','PRISMOS_OFFICE_FONT_CHECK=/tmp/prismos-test-font.ttc',image,'sh','-c','cd /app/backend && .venv/bin/python -m pytest tests/test_office_pdf_fonts.py -q'],cwd=ROOT,check=True)
finally:
    proof['container_removed']=subprocess.run(['docker','inspect',name],capture_output=True).returncode!=0
    (HERE/'image-proof-final.json').write_text(json.dumps(proof,indent=2)+'\n')
verify()
print('Current chart image and input bytes accepted')
