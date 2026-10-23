"""Run final immutable-image acceptance after all compatibility repairs."""
from pathlib import Path
import hashlib,json,subprocess,sys
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
RUNNER=str(HERE/"run_validation.py")
def verify_inputs():
    changed=[p for p,h in json.loads((HERE/"inputs.json").read_text())["sha256"].items() if hashlib.sha256((ROOT/p).read_bytes()).hexdigest()!=h]
    assert not changed,changed
def run(name,cwd,command):
    subprocess.run([sys.executable,RUNNER,"--cwd",cwd,name,"--",*command],cwd=ROOT,check=True)
verify_inputs()
for name in ["fixed-membership-regression","final-compatibility-regression","backend-static-accepted"]:
    receipt=json.loads((HERE/(name+"-result.json")).read_text())
    assert receipt["complete"] and receipt["returncode"]==0,name
run("image-build-accepted","root",["docker","build","-f",str(ROOT/"backend/Dockerfile"),"-t","prismos-auxiliary-accepted:test",str(ROOT)])
image=subprocess.check_output(["docker","image","inspect","prismos-auxiliary-accepted:test","--format","{{.Id}}"],text=True).strip()
(HERE/"accepted-runtime.json").write_text(json.dumps({"image_id":image,"mutable_tag_not_used_for_final_tests":True},indent=2)+"\n")
source=(HERE/"verify_image.py").read_text()
source=source.replace("prismos-scoped-execution:test","prismos-auxiliary-accepted:test")
source=source.replace("files=[","files=['tests/test_agent_skill_references.py', 'tests/test_tenant_context_on_config_routers.py',",1)
source=source.replace('"image-proof.json"','"image-proof-accepted.json"')
source=source.replace('"image-runtime"','"image-runtime-accepted"')
(HERE/"verify_image_accepted.py").write_text(source)
subprocess.run([sys.executable,str(HERE/"verify_image_accepted.py")],cwd=ROOT,check=True)
verify_inputs()
full=[sys.executable,RUNNER,"--cwd","backend","backend-full-accepted","--","env","PRISMOS_SCOPED_TEST_IMAGE="+image,".venv/bin/python","-m","pytest","tests/","-q"]
upgrade=[sys.executable,RUNNER,"upgrade-accepted","--","env","PRISMOS_SCOPED_TEST_IMAGE="+image,sys.executable,str(ROOT/"scripts/octop_upgrade_probe.py"),
"--previous-archive","/tmp/prismos-copy-share-upgrade/previous/upstream.tar.gz","--previous-receipt","/tmp/prismos-copy-share-upgrade/previous/manifest.json",
"--previous-revision","e473dd3c4a4741618ffde1a42a3492341a189e8e","--previous-release","0.3.0b5","--output",str(HERE/"upgrade-accepted.json"),
"--test-file","tests/test_auxiliary_resource_runtime.py","--test-file","tests/test_octop_integration.py",
"--test-file","tests/test_octop_presentation.py","--test-file","tests/test_octop_resources.py","--test-file","tests/test_tenant_context_on_config_routers.py"]
processes=[subprocess.Popen(command,cwd=ROOT) for command in [full,upgrade]]
codes=[process.wait() for process in processes]
verify_inputs()
(HERE/"accepted-driver.json").write_text(json.dumps({"complete":True,"returncodes":codes,"source_inputs_unchanged":True,"image_id":image},indent=2)+"\n")
if any(codes): raise SystemExit(1)
print("Final backend, image and source upgrade gates passed",flush=True)
