from pathlib import Path
import subprocess,sys
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
for name,command in [
    ("source",["scripts/octop_sync.py","verify"]),
    ("external",["scripts/octop_external.py","verify"]),
    ("inventory",["scripts/octop_inventory.py","verify"]),
    ("brand-before-stage",["scripts/check_brand_identity.py"]),
]:
    subprocess.run([sys.executable,str(HERE/"run_validation.py"),name,"--",sys.executable,*command],cwd=ROOT,check=True)
