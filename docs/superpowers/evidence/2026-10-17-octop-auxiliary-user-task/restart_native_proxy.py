"""Apply the current loopback proxy code to its exact recorded owned process."""
from pathlib import Path
import json,os,signal,subprocess,sys,time
import httpx
ROOT=Path(__file__).resolve().parents[4];sys.path.insert(0,str(ROOT/'scripts'))
from octop_wsl_native_env import NATIVE,process_identity,settled_process_identity,private
processes=json.loads((NATIVE/'processes.json').read_text());old=processes['proxy'];assert process_identity(old['pid'])=={k:old[k] for k in ['starttime','cmdline_sha256']};assert os.getpgid(old['pid'])==old['pid']
os.kill(old['pid'],signal.SIGTERM)
for _ in range(150):
 p=Path('/proc')/str(old['pid'])/'stat'
 if not p.exists() or p.read_text().split(') ',1)[1].split()[0]=='Z':break
 time.sleep(.1)
else:raise RuntimeError('Proxy shutdown unconfirmed; no new process started')
log=NATIVE/'proxy-current.log'
with log.open('wb') as stream:
 log.chmod(0o600);p=subprocess.Popen([str(ROOT/'backend/.venv/bin/python'),'-m','uvicorn','octop_wsl_native_proxy:app','--host','127.0.0.1','--port','18036'],cwd=NATIVE,env={**os.environ,'PYTHONPATH':str(ROOT/'scripts')},stdout=stream,stderr=subprocess.STDOUT,start_new_session=True)
processes['proxy']={'pid':p.pid,**settled_process_identity(p,[str(ROOT/'backend/.venv/bin/python'),'-m','uvicorn','octop_wsl_native_proxy:app','--host','127.0.0.1','--port','18036'])};private(NATIVE/'processes.json',json.dumps(processes).encode())
with httpx.Client(trust_env=False,timeout=5) as c:
 for _ in range(60):
  try:
   if c.get('http://127.0.0.1:18036/health').status_code==200 and c.get('http://127.0.0.1:18036/',follow_redirects=True).status_code==200:break
  except httpx.HTTPError:pass
  time.sleep(.5)
 else:raise RuntimeError('Current proxy not ready')
print('Current native browser proxy healthy; owned PID replaced, main stack untouched')
