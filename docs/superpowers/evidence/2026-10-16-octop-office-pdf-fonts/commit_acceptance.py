from pathlib import Path
import hashlib,json,subprocess,sys
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
def run(args):subprocess.run(args,cwd=ROOT,check=True)
assert subprocess.check_output(['git','rev-parse','--short','HEAD'],cwd=ROOT,text=True).strip()=='b6b886c'
run([sys.executable,str(HERE/'finalize_evidence.py')])
run([sys.executable,str(HERE/'render_report.py')])
paths=['.gitignore','.dockerignore','backend/packages/harness/deerflow/tools/builtins/office_fonts.py','backend/packages/harness/deerflow/tools/builtins/office_pdf.py','backend/tests/test_office_pdf_fonts.py','backend/tests/fixtures/pdf-fonts','scripts/octop_upgrade_probe.py','.github/workflows/octop-integration.yml','docs/superpowers/plans/2026-10-09-octop-next-iterations.md','docs/superpowers/plans/2026-10-14-octop-functional-milestones.md',HERE.relative_to(ROOT).as_posix()]
run(['git','add',*paths])
run([sys.executable,str(HERE/'run_validation.py'),'brand-staged','--',sys.executable,'scripts/check_brand_identity.py'])
assert json.loads((HERE/'brand-staged-result.json').read_text())['returncode']==0
run([sys.executable,str(HERE/'finalize_evidence.py')])
v=json.loads((HERE/'validation.json').read_text())
raw=dict(v['raw_log_sha256'])
raw.update({(HERE/name).relative_to(ROOT).as_posix():value for name,value in v['additional_raw_sha256'].items()})
raw.update({(HERE/name).relative_to(ROOT).as_posix():value for name,value in v['demo_sha256'].items()})
raw.update(v['source_asset_sha256'])
raw.update({(HERE/name).relative_to(ROOT).as_posix():value for name,value in v['preserved_archive_sha256'].items()})
run(['git','add',HERE.relative_to(ROOT).as_posix()])
run(['git','add','-f',*raw])
for p,h in raw.items():assert hashlib.sha256(subprocess.check_output(['git','show',':'+p],cwd=ROOT)).hexdigest()==h,p
run(['git','diff','--cached','--check','--','.',':(exclude)**/*.log'])
run(['git','commit','-q','-m','feat(office): add authorized Unicode and CJK PDF font inputs'])
for p,h in raw.items():assert hashlib.sha256(subprocess.check_output(['git','show','HEAD:'+p],cwd=ROOT)).hexdigest()==h,p
print('Committed:',subprocess.check_output(['git','rev-parse','--short','HEAD'],cwd=ROOT,text=True).strip(),'byte-identical raw receipts/assets:',len(raw))
