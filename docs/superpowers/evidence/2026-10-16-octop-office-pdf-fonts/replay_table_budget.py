from pathlib import Path
import json,struct
from deerflow.tools.builtins.office_fonts import font_coverage
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
font=(ROOT/'backend/tests/fixtures/pdf-fonts/NotoMono-Regular.ttf').read_bytes()
count=struct.unpack_from('>H',font,4)[0]
data=bytearray(font)
payload=len(data)
data.extend(b'x'*65536)
face=len(data)
header=bytearray(font[:12])
struct.pack_into('>H',header,4,count+128)
records=font[12:12+count*16]+b''.join(struct.pack('>4sIII',f'{i:04x}'.encode(),0,payload,65536) for i in range(128))
data.extend(header+records)
data[:16]=b'ttcf'+struct.pack('>III',0x10000,1,face)
import tarfile,hashlib
member='backend/packages/harness/deerflow/tools/builtins/office_fonts.py'
receipt=json.loads((HERE/'source-before-table-budget.json').read_text())['sha256']
with tarfile.open(HERE/'source-before-table-budget.tar.gz') as archive:body=archive.extractfile(member).read()
assert hashlib.sha256(body).hexdigest()==receipt[member]
namespace={}
exec(compile(body,'recorded-pre-table-budget-fonts','exec'),namespace)
assert namespace['font_coverage'](bytes(data))(ord('A'))
try:font_coverage(bytes(data))
except ValueError as error:
 assert 'total table budget' in str(error)
 rejection=str(error)
else:raise AssertionError('Current implementation did not reject table amplification')
proof={'scope':'Synthetic table metadata only; no native font parsing or exhaustion attempted','font_bytes':len(data),'aliased_table_bytes':128*65536,'recorded_snapshot_accepted':True,'current_rejected':rejection,'required_fix':'Bound total declared table bytes before copying table payloads'}
(HERE/'table-budget-snapshot-replay.json').write_text(json.dumps(proof,indent=2)+'\n')
print(json.dumps(proof))
