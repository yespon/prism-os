from pathlib import Path
import json,os,signal,time
root=Path('/root/.codex/worktrees/octop-integration/prism-os')
here=root/'docs/superpowers/evidence/2026-10-15-octop-n09-remote-command-leases'
matched=[]
for entry in Path('/proc').iterdir():
    if not entry.name.isdigit(): continue
    try: args=(entry/'cmdline').read_bytes().split(b'\0')
    except (FileNotFoundError,PermissionError): continue
    if any(a.decode(errors='ignore')==str(here/'run_acceptance.py') for a in args):
        matched.append(int(entry.name))
assert len(matched)<=1,matched
for pid in matched: os.kill(pid,signal.SIGTERM)
(here/'driver-review-hold.json').write_text(json.dumps({'driver_pids':matched,'stopped_before_full_acceptance':not (here/'backend-full-result.json').exists(),'reason':'API object disappearance after force deletion does not prove node process termination; add finalizer and container terminal receipt. Existing build children retain their actual results.','timestamp':time.time()},indent=2)+'\n')
print('Stopped only acceptance driver:',matched)
