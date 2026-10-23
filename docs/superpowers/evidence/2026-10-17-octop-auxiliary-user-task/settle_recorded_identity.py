"""Repair a pre-exec hash only for the original PID starttime and exact launch argv."""
from pathlib import Path
import hashlib,json,os,sys
ROOT=Path(__file__).resolve().parents[4];sys.path.insert(0,str(ROOT/'scripts'))
from octop_wsl_native_env import NATIVE,process_identity,private
p=NATIVE/'processes.json';original=p.read_bytes();saved=json.loads(original);owned=json.loads((NATIVE/'ownership.json').read_text());changed=[]
for name in ['gateway','langgraph','proxy']:
 item=saved[name];actual=process_identity(item['pid'])
 if actual=={k:item[k] for k in ['starttime','cmdline_sha256']}:continue
 assert actual['starttime']==item['starttime'],'PID was reused; no repair allowed'
 command=[str(ROOT/'backend/.venv/bin/python'),str(NATIVE/'entry.py'),name,owned['nonce']] if name!='proxy' else [str(ROOT/'backend/.venv/bin/python'),'-m','uvicorn','octop_wsl_native_proxy:app','--host','127.0.0.1','--port','18036']
 argv=(Path('/proc')/str(item['pid'])/'cmdline').read_bytes();assert argv==b'\0'.join(os.fsencode(x) for x in command)+b'\0','Original launch argv does not match'
 saved[name]={**item,**actual};changed.append(name)
backup=NATIVE/'processes-before-exec-identity-settle.json';assert not backup.exists();private(backup,original);private(p,json.dumps(saved).encode())
(Path(__file__).parent/'identity-settle.json').write_text(json.dumps({'complete':True,'changed':changed,'original_pid_starttime_and_exact_launch_argv_verified':True,'processes_restarted':0},indent=2)+'\n')
print('Pre-exec identity records settled using original instance and exact launch argv')
