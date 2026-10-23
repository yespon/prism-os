from pathlib import Path
import hashlib,json,subprocess,sys,tempfile,uuid
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def verify():
    for p,h in json.loads((HERE/'inputs.json').read_text())['sha256'].items():assert sha(ROOT/p)==h,p
verify()
assert json.loads((HERE/'backend-image-build-result.json').read_text())['returncode']==0
image=subprocess.check_output(['docker','image','inspect','prismos-office-pptx-images:test','--format','{{.Id}}'],text=True).strip()
files=['packages/harness/deerflow/tools/builtins/office_pptx_images.py','tests/test_office_pptx_images.py','packages/harness/deerflow/tools/builtins/office_docx_images.py','packages/harness/deerflow/tools/builtins/office_docx.py','tests/test_office_docx_images.py','tests/test_office_chart_editing.py','packages/harness/deerflow/tools/builtins/office_xlsx.py','packages/harness/deerflow/tools/builtins/office_pptx.py','packages/harness/deerflow/tools/builtins/office_common.py','tests/test_office_charts.py','tests/test_office_xlsx.py','tests/test_office_formats.py','tests/test_office_docx.py','tests/test_file_access_http.py','uv.lock','packages/harness/pyproject.toml']
proof={'image':image,'files':{},'network':'none','default_privileges':True}
container=subprocess.check_output(['docker','create',image],text=True).strip()
try:
    with tempfile.TemporaryDirectory(prefix='prismos-chart-image-proof-') as folder:
        for index,p in enumerate(files):
            target=Path(folder)/str(index)
            subprocess.run(['docker','cp',container+':/app/backend/'+p,str(target)],check=True,capture_output=True)
            assert sha(target)==sha(ROOT/'backend'/p),p
            proof['files']['backend/'+p]={'sha256':sha(target),'matches':True}
finally:subprocess.run(['docker','rm',container],check=True,capture_output=True)
name='prismos-office-charts-'+uuid.uuid4().hex[:12]
try:
    subprocess.run([sys.executable,str(HERE/'run_validation.py'),'image-runtime','--','docker','run','--rm','--network','none','--memory','1g','--cpus','2','--pids-limit','256','--name',name,image,'sh','-c','cd /app/backend && .venv/bin/python -m pytest tests/test_office_pptx_images.py tests/test_office_docx_images.py tests/test_office_chart_editing.py tests/test_office_charts.py tests/test_office_xlsx.py tests/test_office_formats.py tests/test_office_docx.py tests/test_file_access_http.py -q'],cwd=ROOT,check=True)
finally:
    proof['container_removed']=subprocess.run(['docker','inspect',name],capture_output=True).returncode!=0
    (HERE/'image-proof.json').write_text(json.dumps(proof,indent=2)+'\n')
verify()
print('Current PPTX picture image and input bytes accepted')
