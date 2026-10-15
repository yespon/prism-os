from pathlib import Path
import json,re,subprocess
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
p=HERE/'full-collection.json'
if p.exists(): names=json.loads(p.read_text())
else:
    r=subprocess.run(['.venv/bin/python','-m','pytest','tests/','--collect-only','-q'],cwd=ROOT/'backend',capture_output=True,text=True,check=True)
    names=[line for line in r.stdout.splitlines() if '::test' in line]
    p.write_text(json.dumps(names,indent=2)+'\n')
s=(HERE/'logs/backend-full.log').read_text()
s=s.split('=== FAILURES')[0]
letters=''.join(line.split('[')[0].replace(' ','') for line in s.splitlines() if re.fullmatch(r'[.FsExX\s]+(?:\[\s*\d+%\])?\s*',line))
print('Collected',len(names),'finished',len(letters))
for i,c in enumerate(letters):
    if c in 'FE': print(i+1,names[i])
