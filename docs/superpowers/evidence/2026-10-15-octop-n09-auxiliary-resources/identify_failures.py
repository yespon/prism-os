"""Identify already failed nodes from live pytest progress without re-executing tests."""
from pathlib import Path
import json,re,subprocess,sys
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
progress=(HERE/"logs/backend-full.log").read_text()
index=0
failed=[]
for line in progress.splitlines():
    match=re.fullmatch(r"([.FsxXE]+)(?:\s+\[\s*\d+%\])?",line.strip())
    if match:
        for token in match[1]:
            if token in "FE": failed.append(index)
            index+=1
result=subprocess.run([sys.executable,"-m","pytest","tests/","--collect-only","-q"],cwd=ROOT/"backend",capture_output=True,text=True)
assert result.returncode==0,result.stderr
nodes=[line for line in result.stdout.splitlines() if line.startswith("tests/") and "::" in line]
selected=[{"index":i,"node":nodes[i]} for i in failed]
(HERE/"early-failed-nodes.json").write_text(json.dumps({"processed":index,"collected":len(nodes),"failed":selected},indent=2)+"\n")
print(json.dumps(selected))
