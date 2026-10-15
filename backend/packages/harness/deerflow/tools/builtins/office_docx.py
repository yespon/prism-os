"""Independent DOCX operations; no excluded upstream Office source or execution."""

import hashlib
import io
import json
import zipfile
from pathlib import PurePosixPath
from xml.etree import ElementTree as ET

from langchain.tools import ToolRuntime, tool

from deerflow.runtime import current_file_access

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
REL = "http://schemas.openxmlformats.org/package/2006/relationships"
CT = "http://schemas.openxmlformats.org/package/2006/content-types"
ET.register_namespace("w", W)
ET.register_namespace("r", R)
MAX_BYTES = 16 * 1024 * 1024
MAX_EXPANDED = 32 * 1024 * 1024


def _xml(data):
    if b"<!DOCTYPE" in data.replace(b"\x00", b"").upper() or b"<!ENTITY" in data.replace(b"\x00", b"").upper():
        raise ValueError("Document XML declarations unavailable")
    return ET.fromstring(data)


def _serialize(root):
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def _parts(data):
    if len(data) > MAX_BYTES:
        raise ValueError("Document size limit exceeded")
    with zipfile.ZipFile(io.BytesIO(data)) as package:
        members = package.infolist()
        names = [member.filename for member in members]
        if len(members) > 512 or len(set(names)) != len(names) or sum(m.file_size for m in members) > MAX_EXPANDED:
            raise ValueError("Document package limit exceeded")
        for name in names:
            path = PurePosixPath(name)
            if path.is_absolute() or ".." in path.parts or "\\" in name or ":" in name:
                raise ValueError("Document package path unavailable")
            if name.lower().endswith((".bin", ".vba", ".exe")) or name.startswith(("word/embeddings/", "word/activeX/")):
                raise ValueError("Active document content unavailable")
        parts = {name: package.read(name) for name in names if not name.endswith("/")}
    for name, content in parts.items():
        if name.endswith((".xml", ".rels")):
            root = _xml(content)
            pending = [(root, 0)]
            nodes = 0
            while pending:
                node, depth = pending.pop()
                nodes += 1
                if nodes > 100_000 or depth > 100:
                    raise ValueError("Document structure limit exceeded")
                pending.extend((child, depth + 1) for child in node)
            if any(n.tag in {f"{{{W}}}instrText", f"{{{W}}}fldSimple", f"{{{W}}}object", f"{{{W}}}altChunk"} for n in root.iter()):
                raise ValueError("Active or field content unavailable")
            if name.endswith(".rels") and any(node.get("TargetMode") == "External" for node in root):
                raise ValueError("External document relationships unavailable")
    if not {"[Content_Types].xml", "_rels/.rels", "word/document.xml"}.issubset(parts):
        raise ValueError("DOCX package required")
    content_types = _xml(parts["[Content_Types].xml"])
    if not any(node.get("PartName") == "/word/document.xml" and node.get("ContentType") == "application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml" for node in content_types):
        raise ValueError("Non-DOCX document content unavailable")
    if _xml(parts["word/document.xml"]).tag != f"{{{W}}}document":
        raise ValueError("DOCX document required")
    return parts


def _package(parts):
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as package:
        for name, data in sorted(parts.items()):
            package.writestr(name, data)
    data = output.getvalue()
    _parts(data)
    return data


def _text(value):
    if not isinstance(value, str) or len(value) > 100_000:
        raise ValueError("Document text unavailable")
    # XML 1.0 controls cannot be represented by escaping.
    if any(ord(c) < 32 and c not in "\t\n\r" for c in value):
        raise ValueError("Document text contains invalid controls")
    return value


def _paragraph(parent, value):
    style = None
    if isinstance(value, dict):
        style, value = value.get("style"), value.get("text", "")
        if style not in {None, "Normal", "Title", "Heading1", "Heading2", "Heading3"}:
            raise ValueError("Document style unavailable")
    p = ET.SubElement(parent, f"{{{W}}}p")
    if style:
        properties = ET.SubElement(p, f"{{{W}}}pPr")
        ET.SubElement(properties, f"{{{W}}}pStyle", {f"{{{W}}}val": style})
    run = ET.SubElement(p, f"{{{W}}}r")
    text = ET.SubElement(run, f"{{{W}}}t", {"{http://www.w3.org/XML/1998/namespace}space": "preserve"})
    text.text = _text(value)


def create_docx(document):
    if not isinstance(document, dict) or set(document) - {"title", "paragraphs", "tables", "header", "footer"}:
        raise ValueError("Document schema unavailable")
    if len(json.dumps(document, ensure_ascii=False)) > 2_000_000:
        raise ValueError("Document content limit exceeded")
    paragraphs, tables = document.get("paragraphs", []), document.get("tables", [])
    if not isinstance(paragraphs, list) or not isinstance(tables, list) or len(paragraphs) > 2000 or len(tables) > 100:
        raise ValueError("Document content limit exceeded")
    root = ET.Element(f"{{{W}}}document")
    body = ET.SubElement(root, f"{{{W}}}body")
    if document.get("title"):
        _paragraph(body, {"text": document["title"], "style": "Title"})
    for paragraph in paragraphs:
        _paragraph(body, paragraph)
    cells = 0
    for rows in tables:
        if not isinstance(rows, list) or not rows or len(rows) > 1000:
            raise ValueError("Document table unavailable")
        table = ET.SubElement(body, f"{{{W}}}tbl")
        for values in rows:
            if not isinstance(values, list) or not values or len(values) > 100:
                raise ValueError("Document table row unavailable")
            cells += len(values)
            if cells > 10_000:
                raise ValueError("Document table limit exceeded")
            row = ET.SubElement(table, f"{{{W}}}tr")
            for value in values:
                _paragraph(ET.SubElement(row, f"{{{W}}}tc"), value)
    section = ET.SubElement(body, f"{{{W}}}sectPr")
    types = ET.Element(f"{{{CT}}}Types")
    ET.SubElement(types, f"{{{CT}}}Default", Extension="rels", ContentType="application/vnd.openxmlformats-package.relationships+xml")
    ET.SubElement(types, f"{{{CT}}}Default", Extension="xml", ContentType="application/xml")
    ET.SubElement(types, f"{{{CT}}}Override", PartName="/word/document.xml", ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml")
    rels = ET.Element(f"{{{REL}}}Relationships")
    ET.SubElement(rels, f"{{{REL}}}Relationship", Id="document", Type=R + "/officeDocument", Target="word/document.xml")
    document_rels = ET.Element(f"{{{REL}}}Relationships")
    parts = {}
    for kind in ("header", "footer"):
        if kind in document:
            part = ET.Element(f"{{{W}}}" + ("hdr" if kind == "header" else "ftr"))
            _paragraph(part, document[kind])
            parts[f"word/{kind}.xml"] = _serialize(part)
            section.insert(0 if kind == "header" else 1, ET.Element(f"{{{W}}}{kind}Reference", {f"{{{W}}}type": "default", f"{{{R}}}id": kind}))
            ET.SubElement(document_rels, f"{{{REL}}}Relationship", Id=kind, Type=R + "/" + kind, Target=kind + ".xml")
            ET.SubElement(types, f"{{{CT}}}Override", PartName=f"/word/{kind}.xml", ContentType=f"application/vnd.openxmlformats-officedocument.wordprocessingml.{kind}+xml")
    ET.SubElement(section, f"{{{W}}}pgSz", {f"{{{W}}}w": "11906", f"{{{W}}}h": "16838"})
    ET.SubElement(section, f"{{{W}}}pgMar", {f"{{{W}}}{k}": "1440" for k in ("top", "right", "bottom", "left")})
    styles = ET.Element(f"{{{W}}}styles")
    for name, size in (("Normal", 22), ("Title", 40), ("Heading1", 32), ("Heading2", 28), ("Heading3", 24)):
        style = ET.SubElement(styles, f"{{{W}}}style", {f"{{{W}}}type": "paragraph", f"{{{W}}}styleId": name})
        ET.SubElement(style, f"{{{W}}}name", {f"{{{W}}}val": name})
        rpr = ET.SubElement(style, f"{{{W}}}rPr")
        ET.SubElement(rpr, f"{{{W}}}sz", {f"{{{W}}}val": str(size)})
        if name.startswith("Heading"):
            ET.SubElement(rpr, f"{{{W}}}b")
            ppr = ET.SubElement(style, f"{{{W}}}pPr")
            ET.SubElement(ppr, f"{{{W}}}outlineLvl", {f"{{{W}}}val": str(int(name[-1]) - 1)})
            style.remove(ppr)
            style.insert(1, ppr)
    parts["word/styles.xml"] = _serialize(styles)
    ET.SubElement(document_rels, f"{{{REL}}}Relationship", Id="styles", Type=R + "/styles", Target="styles.xml")
    ET.SubElement(types, f"{{{CT}}}Override", PartName="/word/styles.xml", ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml")
    parts.update({"[Content_Types].xml": _serialize(types), "_rels/.rels": _serialize(rels), "word/_rels/document.xml.rels": _serialize(document_rels), "word/document.xml": _serialize(root)})
    return _package(parts)


def _document_paragraph_text(paragraph):
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
                values.append("\n".join(_document_paragraph_text(p) for p in cell.findall(f"{{{W}}}p")))
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
        result[kind] = "\n".join(content)
    return result


def edit_docx(data, replacements):
    parts = _parts(data)
    if not isinstance(replacements, dict) or not replacements or len(replacements) > 100:
        raise ValueError("Document replacements unavailable")
    for old, new in replacements.items():
        if not _text(old):
            raise ValueError("Empty replacement unavailable")
        _text(new)
    matches = 0
    text_budget = 0
    for name in list(parts):
        if not name.startswith("word/") or not name.endswith(".xml"):
            continue
        root = _xml(parts[name])
        changed = False
        for paragraph in root.iter(f"{{{W}}}p"):
            nodes = list(paragraph.iter(f"{{{W}}}t"))
            original = "".join(n.text or "" for n in nodes)
            current = original
            if len(current) > 100_000:
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
            if current != original and nodes:
                # Keep paragraphs/tables/relationships; replacements spanning runs
                # adopt the first run's character style. Rich tracked edits remain pending.
                nodes[0].text = current
                nodes[0].set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
                for node in nodes[1:]:
                    node.text = ""
                changed = True
        if changed:
            parts[name] = _serialize(root)
    if not matches:
        raise ValueError("No document replacement matched")
    return _package(parts), matches


@tool("office_docx", parse_docstring=True)
def office_docx_tool(runtime: ToolRuntime, action: str, source_path: str = "", output_path: str = "", document: dict | None = None, replacements: dict[str, str] | None = None) -> dict:
    """Create, inspect or edit an owned DOCX without executing document content.

    Args:
        action: create, inspect or replace. Advanced layout, tracked changes and rendering are pending.
        source_path: Existing owned uploads/workspace/outputs DOCX for inspect or replace.
        output_path: New /mnt/user-data/outputs/*.docx; never overwrites. Use present_files afterward.
        document: Create schema: title, paragraphs (text or text/style objects), tables (rows of strings), header, footer. Styles: Normal, Title, Heading1..3.
        replacements: Literal text replacements across paragraphs, table cells and headers/footers. Cross-run matches adopt the first run character style.
    """
    try:
        if action not in {"create", "inspect", "replace"}:
            raise ValueError("Document action unavailable")
        data = None
        if action != "create":
            if not source_path.lower().endswith(".docx"):
                raise ValueError("DOCX source required")
            data = current_file_access(runtime, "read_bytes", source_path)
            if data is None:
                raise PermissionError("Current file authority required")
        if action == "inspect":
            result = inspect_docx(data)
            # Parsing may take time: reauthorize before returning private content.
            current_file_access(runtime, "read_bytes", source_path)
            return {"status": "ok", "document": result}
        if not output_path.startswith("/mnt/user-data/outputs/") or not output_path.lower().endswith(".docx"):
            raise ValueError("Owned output DOCX required")
        if source_path and output_path == source_path:
            raise ValueError("New output required")
        if action == "create":
            data = create_docx(document)
            matches = None
        else:
            data, matches = edit_docx(data, replacements)
            current_file_access(runtime, "read_bytes", source_path)
        if current_file_access(runtime, ("create", data), output_path) != "OK":
            raise PermissionError("Current file authority required")
        current_file_access(runtime, "present", output_path)
        return {"status": "ok", "file": output_path, "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data), "replacements": matches}
    except Exception:
        # A write may have completed before a final authorization failure.
        # A stable new output name plus exclusive creation prevents blind replay.
        return {"status": "unavailable", "inspection_required": True, "retry": False}
