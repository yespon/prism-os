from pathlib import Path
import gzip,hashlib,json,time
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
r=json.loads((HERE/'backend-full-result.json').read_text())
assert r['complete'] and r['returncode']==0
assert json.loads((HERE/'backend-driver.json').read_text())['all_inputs_unchanged']
p=ROOT/'backend/packages/harness/deerflow/tools/builtins/office_docx.py'
original=p.read_bytes()
assert hashlib.sha256(original).hexdigest()==json.loads((HERE/'inputs.json').read_text())['sha256'][p.relative_to(ROOT).as_posix()]
(HERE/'office_docx-pre-limits.py.gz').write_bytes(gzip.compress(original,mtime=0))
s=original.decode()
s=s.replace('            root = _xml(content)\n', '''            root = _xml(content)
            pending = [(root, 0)]
            nodes = 0
            while pending:
                node, depth = pending.pop()
                nodes += 1
                if nodes > 100_000 or depth > 100:
                    raise ValueError("Document structure limit exceeded")
                pending.extend((child, depth + 1) for child in node)
''')
s=s.replace('    matches = 0\n','    matches = 0\n    text_budget = 0\n')
s=s.replace('            for old, new in replacements.items():\n                matches += current.count(old)\n                current = current.replace(old, new)\n', '''            if len(current) > 100_000:
                raise ValueError("Document paragraph limit exceeded")
            for old, new in replacements.items():
                count = current.count(old)
                if len(current) + count * (len(new) - len(old)) > 100_000:
                    raise ValueError("Document replacement expansion limit exceeded")
                matches += count
                current = current.replace(old, new)
            text_budget += len(current)
            if text_budget > 2_000_000:
                raise ValueError("Document replacement total limit exceeded")
''')
start=s.index('def inspect_docx(data):')
end=s.index('\n\ndef edit_docx',start)
s=s[:start]+'''def _document_paragraph_text(paragraph):
    if sum(1 for _ in paragraph.iter(f"{{{W}}}p")) != 1:
        raise ValueError("Nested document paragraphs unavailable")
    value = "".join(node.text or "" for node in paragraph.iter(f"{{{W}}}t"))
    if len(value) > 100_000:
        raise ValueError("Document paragraph limit exceeded")
    return value


def inspect_docx(data):
    parts = _parts(data)
    root = _xml(parts["word/document.xml"])
    paragraphs = []
    total = 0
    for paragraph in root.iter(f"{{{W}}}p"):
        value = _document_paragraph_text(paragraph)
        total += len(value)
        if len(paragraphs) >= 2000 or total > 2_000_000:
            raise ValueError("Document inspection limit exceeded")
        paragraphs.append(value)
    tables = []
    cells = 0
    for table in root.iter(f"{{{W}}}tbl"):
        if len(tables) >= 100:
            raise ValueError("Document table limit exceeded")
        rows = []
        for row in table.findall(f"{{{W}}}tr"):
            values = []
            for cell in row.findall(f"{{{W}}}tc"):
                cells += 1
                if cells > 10_000:
                    raise ValueError("Document table limit exceeded")
                values.append("\\n".join(_document_paragraph_text(p) for p in cell.findall(f"{{{W}}}p")))
            rows.append(values)
        tables.append(rows)
    result = {"paragraphs": paragraphs, "tables": tables}
    for kind in ("header", "footer"):
        content = []
        for name in parts:
            if name.startswith("word/" + kind) and name.endswith(".xml"):
                for p in _xml(parts[name]).iter(f"{{{W}}}p"):
                    value = _document_paragraph_text(p)
                    total += len(value)
                    if total > 2_000_000:
                        raise ValueError("Document inspection limit exceeded")
                    content.append(value)
        result[kind] = "\\n".join(content)
    return result
'''+s[end:]
assert s!=original.decode()
p.write_text(s)
p=ROOT/'backend/tests/test_office_docx.py'
(HERE/'test_office_docx-pre-limits.py.gz').write_bytes(gzip.compress(p.read_bytes(),mtime=0))
s=p.read_text()+'''

@pytest.mark.parametrize("kind", ["expansion", "depth", "nodes"])
def test_document_resource_limits_reject_before_unbounded_processing(kind):
    if kind == "expansion":
        source = create_docx({"paragraphs": ["a" * 100]})
        with pytest.raises(ValueError, match="expansion limit"):
            edit_docx(source, {"a": "b" * 10_000})
        return
    with zipfile.ZipFile(io.BytesIO(create_docx(DOCUMENT))) as package:
        parts = {name: package.read(name) for name in package.namelist()}
    nested = ("<x>" * 102 + "body" + "</x>" * 102) if kind == "depth" else "<root>" + "<x/>" * 100_001 + "</root>"
    parts["docProps/custom.xml"] = nested.encode()
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as package:
        for name, data in parts.items():
            package.writestr(name, data)
    with pytest.raises(ValueError, match="structure limit"):
        inspect_docx(output.getvalue())
'''
p.write_text(s)
print('Preserved first fully tested source snapshot; added finite replacement/structure limits')
