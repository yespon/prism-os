from pathlib import Path
import json,struct,sys
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[3]
from deerflow.tools.builtins.office_pdf import create_pdf,render_pdf_page
private=ROOT/'backend/tmp/n04-wsl/font-space-controls';private.mkdir(mode=0o700,exist_ok=True)
def checksum(data):
 padded=data+b'\0'*((-len(data))%4);return sum(x[0] for x in struct.iter_unpack('>I',padded))&0xffffffff
def single_face(data):
 offset=struct.unpack_from('>I',data,12)[0];count=struct.unpack_from('>H',data,offset+4)[0];tables={}
 for i in range(count):
  tag,_,start,size=struct.unpack_from('>4sIII',data,offset+12+16*i)
  if tag==b'DSIG':continue
  table=bytearray(data[start:start+size])
  if tag==b'head':struct.pack_into('>I',table,8,0)
  tables[tag]=bytes(table)
 count=len(tables);power=count.bit_length()-1;blob=bytearray(struct.pack('>IHHHH',0x00010000,count,16*(1<<power),power,count*16-16*(1<<power))+b'\0'*(16*count));head=None
 for i,(tag,table) in enumerate(sorted(tables.items())):
  start=len(blob);struct.pack_into('>4sIII',blob,12+i*16,tag,checksum(table),start,len(table));blob.extend(table);blob.extend(b'\0'*((-len(blob))%4))
  if tag==b'head':head=start
 struct.pack_into('>I',blob,head+8,(0xb1b0afba-checksum(blob))&0xffffffff);return bytes(blob)
font=Path('/mnt/c/Windows/Fonts/msyh.ttc').read_bytes();cases={'noto-ttf':(ROOT/'backend/tests/fixtures/pdf-fonts/NotoMono-Regular.ttf').read_bytes(),'msyh-ttc':font,'msyh-face-ttf':single_face(font)}
for name,data in cases.items():
 if '--fixed' in sys.argv:name+='-fixed'
 pdf=create_pdf({'pages':[['A B','Before blank','After blank']]},font_bytes=data);file=private/(name+'.pdf');file.write_bytes(pdf);file.chmod(0o600);(HERE/(name+'-spaces.png')).write_bytes(render_pdf_page(pdf,1,2))
print(json.dumps({'cases':list(cases),'private_pdfs':str(private),'font_binary_exported':False}))
