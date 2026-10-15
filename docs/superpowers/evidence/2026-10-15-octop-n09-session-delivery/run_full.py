from pathlib import Path
import hashlib,json,subprocess,sys
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
hashes=json.loads((HERE/'inputs.json').read_text())['sha256']
def verify(): assert all(hashlib.sha256((ROOT/p).read_bytes()).hexdigest()==h for p,h in hashes.items())
verify()
image=subprocess.check_output(['docker','image','inspect','prismos-session-delivery:test','--format','{{.Id}}'],text=True).strip()
subprocess.run([sys.executable,str(HERE/'run_validation.py'),'--cwd','backend','backend-full','--','env','PRISMOS_SCOPED_TEST_IMAGE='+image,'.venv/bin/python','-m','pytest','tests/','-q','-o','faulthandler_timeout=120'],cwd=ROOT,check=True)
verify()
(HERE/'backend-driver.json').write_text(json.dumps({'complete':True,'returncode':0,'all_inputs_unchanged':True,'backend_image':image},indent=2)+'\n')
