"""Start the complete backend gate with an immutable scoped runtime image."""
from pathlib import Path
import hashlib,json,subprocess,sys
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
inputs=json.loads((HERE/"inputs.json").read_text())
changed=[p for p,h in inputs["sha256"].items() if hashlib.sha256((ROOT/p).read_bytes()).hexdigest()!=h]
assert not changed,changed
command=[
    sys.executable,str(HERE/"run_validation.py"),"--cwd","backend","backend-full","--",
    "/usr/bin/env","PRISMOS_SCOPED_TEST_IMAGE=sha256:509cfe2e88e78cfdb49676355ff3ca5689535ede5e2befee05e39eb4be608495",
    ".venv/bin/python","-m","pytest","tests/","-q",
]
raise SystemExit(subprocess.run(command,cwd=ROOT).returncode)
