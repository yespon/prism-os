from pathlib import Path
import ast,copy,hashlib,json,subprocess,sys,tarfile
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
old=json.loads((HERE/'inputs-bounded.json').read_text())['sha256']
current={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in old}
module='backend/packages/harness/deerflow/tools/builtins/office_fonts.py'
tests='backend/tests/test_office_pdf_fonts.py'
assert {p for p,h in old.items() if current[p]!=h}=={module,tests}
with tarfile.open(HERE/'source-before-table-budget.tar.gz') as archive:
 before=ast.parse(archive.extractfile(module).read().decode())
 old_tests=ast.parse(archive.extractfile(tests).read().decode())
after=ast.parse((ROOT/module).read_text())
for tree in [before,after]:
 function=next(node for node in tree.body if isinstance(node,ast.FunctionDef) and node.name=='font_coverage')
 function.body=[ast.Pass()]
assert ast.dump(before)==ast.dump(after),'Only font_coverage body may change'
new_tests=ast.parse((ROOT/tests).read_text())
addition='test_aliased_font_table_payloads_cannot_amplify_copy_budget_before_native_parse'
new_tests.body=[node for node in new_tests.body if not isinstance(node,ast.FunctionDef) or node.name!=addition]
assert ast.dump(old_tests)==ast.dump(new_tests),'Existing font nodes must remain semantically unchanged'
# No non-font test supplies the optional font branch or calls its helper.
references=[]
for p in (ROOT/'backend/tests').rglob('*.py'):
 if p.name=='test_office_pdf_fonts.py':continue
 text=p.read_text()
 if any(token in text for token in ['font_bytes', 'font_path', 'font_coverage']):references.append(p.name)
assert not references,references
full=json.loads((HERE/'backend-full-bounded-result.json').read_text())
assert full['complete'] and full['returncode']==0
(HERE/'inputs-final.json').write_text(json.dumps({'base_commit':'b6b886c','scope':'Final table-copy/cmap bounded font preflight; reuse complete backend only outside optional font branch','sha256':current},indent=2)+'\n')
(HERE/'full-reuse-scope.json').write_text(json.dumps({'whole_backend_receipt':'backend-full-bounded-result.json','source_snapshot':'source-before-table-budget.tar.gz','only_app_change':'font_coverage body: total copied table bytes <= input size before copying','unchanged_other_module_ast':True,'unchanged_original_font_test_ast':True,'new_regression':addition,'non_font_tests_supplying_optional_font_branch':references,'unchanged_input_sha256':{p:h for p,h in old.items() if p not in {module,tests}},'reuse_scope':'All non-font nodes of successful complete backend; every font node and original authorization integration is revalidated against current code; not a single new whole-backend run.'},indent=2)+'\n')
s=(HERE/'generate_bounded_demo.py').read_text().replace('demo-chinese-bounded','demo-chinese-final').replace("'demo-bounded.json'","'demo-final.json'")
(HERE/'generate_final_demo.py').write_text(s)
s=(HERE/'run_bounded_image.py').read_text().replace("'inputs-bounded.json'","'inputs-final.json'").replace('backend-image-build-bounded-result','backend-image-build-final-result').replace('prismos-office-pdf-fonts-bounded:test','prismos-office-pdf-fonts-final:test').replace("'image-runtime-bounded'","'image-runtime-final'").replace("'image-proof-bounded.json'","'image-proof-final.json'")
s=s.replace('tests/test_office_pdf_fonts.py tests/test_office_charts.py tests/test_office_xlsx.py tests/test_office_formats.py tests/test_office_docx.py tests/test_file_access_http.py','tests/test_office_pdf_fonts.py')
(HERE/'run_final_image.py').write_text(s)
print('Scope verified: unchanged non-font inputs; complete current font cohort and native integration required')
