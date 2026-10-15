from pathlib import Path
import hashlib,io,json
from PIL import Image
from deerflow.tools.builtins.office_xlsx import create_xlsx,edit_xlsx,inspect_xlsx
from deerflow.tools.builtins.office_pptx import create_pptx,edit_pptx,inspect_pptx
from deerflow.tools.builtins.office_pdf import create_pdf,inspect_pdf,select_pdf_pages,merge_pdf,render_pdf_page
HERE=Path(__file__).resolve().parent
workbook=create_xlsx({'sheets':[{'name':'项目预算','header':True,'filter':True,'rows':[['项目','预算'],['开发',12.5],['验证',20],['总计',{'formula':'=SUM(B2:B3)'}]]}]})
workbook=edit_xlsx(workbook,[{'sheet':'项目预算','cell':'B2','value':30}])
slides=create_pptx({'slides':[{'title':'独立办公文档演示','paragraphs':['表格、演示文稿与PDF基础操作','此示例可编辑，完整高级能力仍在推进'],'notes':'本地演示资料'},{'title':'项目进度','table':[['项目','状态'],['文档基础','已接入'],['高级排版与表单','待完成']]}]})
slides=edit_pptx(slides,{'项目进度':'当前能力'})
pdf=create_pdf({'pages':[['PrismOS independent Office','Editable source files and controlled results','Basic PDF, no OCR or forms'],['Page composition demo','Select, merge and render']]})
pdf=merge_pdf([pdf,select_pdf_pages(pdf,[2])])
png=render_pdf_page(pdf,1,1)
items=[('demo-budget.xlsx',workbook,inspect_xlsx),('demo-slides.pptx',slides,inspect_pptx),('demo-report.pdf',pdf,inspect_pdf)]
proof={'scope':'pure independent format engines; original native authorization/download/revocation separately covered in tests; no real model or external call','files':{}}
for name,data,inspect in items:
    p=HERE/name
    if p.exists():
        assert inspect(p.read_bytes())==inspect(data)
        data=p.read_bytes()
    else: p.write_bytes(data)
    proof['files'][name]={'sha256':hashlib.sha256(data).hexdigest(),'bytes':len(data)}
p=HERE/'demo-page.png'
if p.exists():
    with Image.open(p) as previous,Image.open(io.BytesIO(png)) as current:
        assert previous.size==current.size and previous.tobytes()==current.tobytes()
    png=p.read_bytes()
else: p.write_bytes(png)
proof['files'][p.name]={'sha256':hashlib.sha256(png).hexdigest(),'bytes':len(png)}
assert inspect_xlsx(workbook)['sheets'][0]['rows'][1][1]==30
assert inspect_pptx(slides)['slides'][1]['texts'][0]=='当前能力'
assert len(inspect_pdf(pdf)['pages'])==3
(HERE/'demo.json').write_text(json.dumps(proof,indent=2)+'\n')
print(json.dumps(proof))
