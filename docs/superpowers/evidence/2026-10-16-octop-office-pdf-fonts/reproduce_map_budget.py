from pathlib import Path
import importlib.util,json,struct
from deerflow.tools.builtins.office_fonts import font_coverage
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
font=bytearray((ROOT/'backend/tests/fixtures/pdf-fonts/NotoMono-Regular.ttf').read_bytes())
count=struct.unpack_from('>H',font,4)[0]
entries={struct.unpack_from('>4s',font,12+i*16)[0]:12+i*16 for i in range(count)}
groups=60000
payload=struct.pack('>HHIII',12,0,16+12*groups,0,groups)+b''.join(struct.pack('>III',2*i,2*i,1) for i in range(groups))
offset=4+8*2
cmap=struct.pack('>HH',0,2)+struct.pack('>HHI',3,10,offset)+struct.pack('>HHI',0,4,offset+len(payload))+payload+payload
struct.pack_into('>II',font,entries[b'cmap']+8,len(font),len(cmap))
font.extend(cmap)
original=font_coverage(bytes(font))
assert original(100) and not original(101)
spec=importlib.util.spec_from_file_location('bounded_candidate',ROOT/'backend/tmp/office_fonts_bounded_candidate.py')
module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
try:module.font_coverage(bytes(font))
except ValueError as e:
 assert 'total character map limit' in str(e)
 rejection=str(e)
else:raise AssertionError('Candidate did not enforce combined map budget')
proof={'scope':'Synthetic valid-range cmap metadata; no native font parse, memory exhaustion or external operation attempted','entries_in_two_maps':groups*2,'initial_validator_accepted':True,'bounded_candidate_rejected':rejection,'font_bytes':len(font)}
(HERE/'map-budget-reproduction.json').write_text(json.dumps(proof,indent=2)+'\n')
print(json.dumps(proof))
