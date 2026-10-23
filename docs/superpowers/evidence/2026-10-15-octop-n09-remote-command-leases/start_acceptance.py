from pathlib import Path
import subprocess,sys
here=Path(__file__).resolve().parent
subprocess.run([sys.executable,str(here/'freeze_inputs.py')],check=True)
subprocess.run([sys.executable,str(here/'run_acceptance.py')],check=True)
