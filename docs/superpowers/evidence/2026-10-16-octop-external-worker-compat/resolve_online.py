from pathlib import Path
import os, subprocess
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
context=ROOT/'backend/tmp/octop-external-worker-20261016/context'
command=['/root/.local/bin/uv','--no-config','pip','compile',str(context/'requirements.in'),'--constraint',str(context/'constraints-upstream.txt'),'--python',str(ROOT/'backend/.venv/bin/python'),'--only-binary',':all:','--generate-hashes','--output-file',str(context/'requirements.lock'),'--index-url','https://pypi.org/simple']
# Explicit public-index resolution; no inherited provider keys/index credentials.
env={'PATH':os.defpath,'UV_PYTHON_DOWNLOADS':'never','UV_NO_PROGRESS':'1','UV_CACHE_DIR':'/root/.cache/uv'}
result=subprocess.run(command,cwd=ROOT,env=env)
raise SystemExit(result.returncode)
