from pathlib import Path
import hashlib,json
from deerflow.tools.builtins.office_docx import create_docx,edit_docx,inspect_docx
HERE=Path(__file__).resolve().parent
example={'title':'PrismOS 独立文档能力演示','paragraphs':[{'text':'本轮可用能力','style':'Heading1'},'这是一份由 PrismOS 独立实现生成的 DOCX 示例，不含受限上游 Office 源码。',{'text':'验收范围','style':'Heading2'},'创建、读取、表格、页眉页脚和文字替换已纳入实际测试；模型调用、Microsoft Word 界面和复杂版式渲染不据此宣称验收。'],'tables':[[['能力','范围'],['生成与编辑','原生 Office 工具'],['产物权限','原租户、成员及线程授权'],['结果未知','不覆盖、不自动重发']]],'header':'PrismOS · 独立 Office','footer':'本地功能演示 · 无外部调用'}
original=create_docx(example)
edited,count=edit_docx(original,{'本轮可用能力':'本轮已验证能力','原生 Office 工具':'原生 DOCX 工具'})
assert count==2 and inspect_docx(edited)['paragraphs'][1]=='本轮已验证能力'
proof={'scope':'pure independent document engine samples; native authorization and actual download separately tested in test_office_docx.py','files':{}}
for name,data in [('demo-original.docx',original),('demo-edited.docx',edited)]:
    p=HERE/name
    if p.exists():
        assert inspect_docx(p.read_bytes())==inspect_docx(data)
        data=p.read_bytes()
    else: p.write_bytes(data)
    proof['files'][name]={'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()}
(HERE/'demo.json').write_text(json.dumps(proof,indent=2)+'\n')
print(json.dumps(proof))
