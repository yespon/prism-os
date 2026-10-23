"""Start only owned loopback browser services; do not modify the main Compose stack."""
from pathlib import Path
import json,os,subprocess,sys,time
import httpx
ROOT=Path(__file__).resolve().parents[4];sys.path.insert(0,str(ROOT/'scripts'))
from octop_wsl_native_env import NATIVE,process_identity,private
ownership=json.loads((NATIVE/'ownership.json').read_text());processes=json.loads((NATIVE/'processes.json').read_text());assert 'frontend' not in processes and 'proxy' not in processes
node=Path('/root/.nvm/versions/node/v24.11.1/bin/node');assert node.is_file()
env={**os.environ,'NODE_ENV':'production','NEXT_TELEMETRY_DISABLED':'1','SERVER_BACKEND_URL':'http://127.0.0.1:18031','GATEWAY_URL':'http://127.0.0.1:18031','PYTHONPATH':str(ROOT/'scripts')}
commands={'frontend':[str(node),str(ROOT/'frontend/node_modules/next/dist/bin/next'),'start','-H','127.0.0.1','-p','18035'],'proxy':[str(ROOT/'backend/.venv/bin/python'),'-m','uvicorn','octop_wsl_native_proxy:app','--host','127.0.0.1','--port','18036']}
started={}
for name,command in commands.items():
 log=NATIVE/(name+'.log')
 with log.open('wb') as out:
  log.chmod(0o600);p=subprocess.Popen(command,cwd=ROOT/'frontend' if name=='frontend' else NATIVE,env=env,stdout=out,stderr=subprocess.STDOUT,start_new_session=True)
 started[name]=p.pid
 private(NATIVE/'browser-starting.json',json.dumps(started).encode())
with httpx.Client(trust_env=False,timeout=5) as c:
 deadline=time.monotonic()+90
 while time.monotonic()<deadline:
  try:
   if c.get('http://127.0.0.1:18036/health').status_code==200 and c.get('http://127.0.0.1:18036/',follow_redirects=True).status_code==200:break
  except httpx.HTTPError:pass
  time.sleep(1)
 else:raise RuntimeError('Owned native browser services not healthy; private logs retained')
 assert c.post('http://127.0.0.1:18036/api/langgraph/threads',json={}).status_code==401
for name,pid in started.items():processes[name]={'pid':pid,**process_identity(pid)}
private(NATIVE/'processes.json',json.dumps(processes).encode())
(Path(__file__).parent/'native-browser.json').write_text(json.dumps({'complete':True,'url':'http://localhost:18036','frontend_and_gateway_healthy':True,'anonymous_thread_creation_denied':True,'main_url':'http://localhost:18026','processes':processes},indent=2)+'\n')
print('Owned native browser http://localhost:18036 healthy; main http://localhost:18026 unchanged')
