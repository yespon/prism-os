from pathlib import Path
import hashlib,io,json
from PIL import Image,ImageDraw
import mammoth
from deerflow.tools.builtins.office_docx import create_docx,inspect_docx
from deerflow.tools.builtins.office_docx_images import add_docx_images
HERE=Path(__file__).resolve().parent
image=Image.new('RGB',(720,300),'white')
draw=ImageDraw.Draw(image)
for i,value in enumerate([120,180,240,200]):
 draw.rectangle((40+i*165,260-value,140+i*165,260),fill=(24,80+i*25,150))
 draw.text((65+i*165,270),'Q'+str(i+1),fill='black')
stream=io.BytesIO();image.save(stream,format='PNG');png=stream.getvalue()
source=create_docx({'title':'独立图文报告','paragraphs':['保留原正文与表格，图片通过当前授权读取。'],'tables':[[['季度','数据'],['第一季','120'],['第二季','180']]],'header':'PrismOS 图文文档','footer':'实际DOCX，桌面渲染仍待验收'})
result=add_docx_images(source,[{'data':png,'width_inches':5.5,'alt':'四季度数据示例'}])
html=mammoth.convert_to_html(io.BytesIO(result)).value
assert '<img' in html and '四季度数据示例' in html
assert inspect_docx(result)['tables']==inspect_docx(source)['tables']
proof={'scope':'Actual independent DOCX package and mammoth reader, not desktop rendering or model call','files':{}}
for name,data in [('demo-source.docx',source),('demo-pictured.docx',result),('demo-source.png',png)]:
 path=HERE/name;assert not path.exists();path.write_bytes(data)
 proof['files'][name]={'sha256':hashlib.sha256(data).hexdigest(),'bytes':len(data)}
(HERE/'demo.json').write_text(json.dumps(proof,indent=2)+'\n')
print(json.dumps(proof))
