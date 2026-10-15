from pathlib import Path
import subprocess,json
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
a=json.loads((HERE/'actor-related-final-result.json').read_text())['command']
a=a[:-3]+['--collect-only','-q'] if a[-3:]==['-q','-o','faulthandler_timeout=90'] else a+['--collect-only']
r=subprocess.run(a,cwd=ROOT/'backend',capture_output=True,text=True)
names=[line for line in r.stdout.splitlines() if '::test' in line]
print('\n'.join(f'{i+1}: {name}' for i,name in enumerate(names) if 69<=i<145))
