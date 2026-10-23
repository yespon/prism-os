from pathlib import Path
import subprocess,sys
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
commands=[('source-verify',['scripts/octop_sync.py','verify']),('external-verify',['scripts/octop_external.py','verify']),('inventory-generate',['scripts/octop_inventory.py','generate']),('inventory-verify',['scripts/octop_inventory.py','verify']),('distribution-verify',['scripts/octop_wheel_verify.py','backend/dist/prismos_octop_capabilities-0.1.0-py3-none-any.whl','--sdist','backend/dist/prismos_octop_capabilities-0.1.0.tar.gz'])]
for name,args in commands:
    subprocess.run([sys.executable,str(HERE/'run_validation.py'),name,'--',sys.executable,*args],cwd=ROOT,check=True)
print('Current dependency inventory and original retained/distributed bytes verified')
