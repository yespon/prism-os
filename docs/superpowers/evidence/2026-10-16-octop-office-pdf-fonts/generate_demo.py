from pathlib import Path
import hashlib,io,json,subprocess
from PIL import Image
from deerflow.tools.builtins.office_fonts import font_coverage
from deerflow.tools.builtins.office_pdf import create_pdf,inspect_pdf,render_pdf_page
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
font=Path('/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc')
blob=font.read_bytes()
lines=['PrismOS 独立 PDF 中文字体','季度预算：研发 120，验证 80','使用当前有权读取的字体文件生成','缺字与复杂文字整形会明确拒绝']
assert all(font_coverage(blob)(ord(c)) for line in lines for c in line)
pdf=create_pdf({'pages':[lines]},font_bytes=blob)
text=inspect_pdf(pdf)['pages'][0]['text']
assert all(line in text for line in lines)
assert b'/FontFile2' in pdf
png=render_pdf_page(pdf,1,1.25)
with Image.open(io.BytesIO(png)) as image:
    assert image.convert('RGB').getextrema()!=((255,255),)*3
proof={'scope':'Actual font engine bytes/text/pixels; native authorization/download/revocation separately tested, not OCR or complex shaping','font':{'source':str(font),'sha256':hashlib.sha256(blob).hexdigest(),'bytes':len(blob),'package':subprocess.check_output(['dpkg-query','-W','-f=${Version}','fonts-wqy-zenhei'],text=True),'declared_license':'GPL-2 with Font embedding exception and M+ FONTS License; original source-package notice retained','implicit_runtime_font_lookup':False},'extracted_text':text,'files':{}}
for name,data in [('demo-chinese.pdf',pdf),('demo-chinese.png',png)]:
    path=HERE/name
    assert not path.exists()
    path.write_bytes(data)
    proof['files'][name]={'sha256':hashlib.sha256(data).hexdigest(),'bytes':len(data)}
(HERE/'cjk-font-copyright.txt').write_bytes(Path('/usr/share/doc/fonts-wqy-zenhei/copyright').read_bytes())
(HERE/'demo.json').write_text(json.dumps(proof,indent=2,ensure_ascii=False)+'\n')
print(json.dumps(proof,ensure_ascii=False))
