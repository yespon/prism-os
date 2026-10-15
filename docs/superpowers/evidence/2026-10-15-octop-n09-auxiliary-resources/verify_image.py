"""Verify the newly built image with default privileges and retained source hashes."""
from pathlib import Path
import hashlib,json,subprocess,sys,tempfile,time,uuid
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
deadline=time.monotonic()+1800
while True:
    result=subprocess.run(["docker","image","inspect","prismos-scoped-execution:test","--format","{{.Id}}"],capture_output=True,text=True)
    if result.returncode==0: break
    if time.monotonic()>deadline: raise TimeoutError("Image build not terminal within 30 minutes")
    time.sleep(5)
image=result.stdout.strip()
files=['app/gateway/resource_authorization.py', 'app/gateway/routers/agents.py', 'app/gateway/routers/skills.py', 'app/gateway/routers/agent_catalog.py', 'app/integrations/skill_imports.py', 'app/integrations/octop/auxiliary_packages.py', 'app/integrations/octop/resource_installations.py', 'app/integrations/octop/skill_packages.py', 'packages/harness/deerflow/skills/parser.py', 'packages/harness/deerflow/skills/loader.py', 'packages/harness/deerflow/database/user_config_service.py', 'tests/test_resource_catalog_access.py', 'tests/test_auxiliary_resource_runtime.py', 'tests/test_octop_skill_packages.py', 'tests/resource_test_identity.py', 'tests/test_octop_resource_installations.py', 'tests/test_custom_agent.py', 'tests/test_skill_import_recovery.py', 'tests/test_octop_integration.py', 'tests/test_skills_scope_router.py', 'Dockerfile']
container=subprocess.check_output(["docker","create",image],text=True).strip()
proof={"image_id":image,"files":{},"default_privileges":True,"network":"none"}
try:
    with tempfile.TemporaryDirectory(prefix="prismos-copy-image-proof-") as tmp:
        for i,path in enumerate(files):
            target=Path(tmp)/str(i)
            subprocess.run(["docker","cp",container+":/app/backend/"+path,str(target)],check=True,capture_output=True)
            host=hashlib.sha256((ROOT/"backend"/path).read_bytes()).hexdigest()
            actual=hashlib.sha256(target.read_bytes()).hexdigest()
            proof["files"][path]={"host_sha256":host,"image_sha256":actual,"matches":host==actual}
            assert host==actual,path
finally:
    subprocess.run(["docker","rm",container],check=True,capture_output=True)
(HERE/"image-proof.json").write_text(json.dumps(proof,indent=2)+"\n")
name="prismos-auxiliary-"+uuid.uuid4().hex[:12]
command=["docker","run","--rm","--network","none","--memory","1g","--cpus","2","--pids-limit","256","--name",name,image,"sh","-c","cd /app/backend && .venv/bin/python -m pytest tests/test_resource_catalog_access.py tests/test_octop_skill_packages.py tests/test_octop_resource_installations.py -q"]
try:
    result=subprocess.run([sys.executable,str(HERE/"run_validation.py"),"image-runtime","--",*command],cwd=ROOT)
finally:
    remaining=subprocess.run(["docker","container","inspect",name],capture_output=True)
    proof["test_container_removed"]=remaining.returncode!=0
    (HERE/"image-proof.json").write_text(json.dumps(proof,indent=2)+"\n")
if not proof["test_container_removed"]: raise RuntimeError("Owned test container remains")
sys.exit(result.returncode)
