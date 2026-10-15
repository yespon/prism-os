"""Independent bounded presentations; no copied upstream Office scripts."""

import io
import json

from langchain.tools import ToolRuntime, tool
from pptx import Presentation
from pptx.enum.shapes import MSO_SHAPE_TYPE
from pptx.util import Inches, Pt

from .office_common import check_office_package, owned_office_operation

CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml"


def _text(value):
    if not isinstance(value, str) or len(value) > 100_000 or any(ord(c) < 32 and c not in "\t\n\r" for c in value):
        raise ValueError("Presentation text unavailable")
    return value


def _shapes(collection, depth=0):
    if depth > 16:
        raise ValueError("Presentation group depth exceeded")
    for shape in collection:
        yield shape
        if shape.shape_type == MSO_SHAPE_TYPE.GROUP:
            yield from _shapes(shape.shapes, depth + 1)


def _frames(slide):
    count = 0
    for shape in _shapes(slide.shapes):
        count += 1
        if count > 2000:
            raise ValueError("Presentation shape limit exceeded")
        if shape.has_text_frame:
            yield shape.text_frame
        if shape.has_table:
            for row in shape.table.rows:
                for cell in row.cells:
                    yield cell.text_frame
    if slide.has_notes_slide and slide.notes_slide.notes_text_frame is not None:
        yield slide.notes_slide.notes_text_frame


def _budget(presentation):
    if len(presentation.slides) > 100:
        raise ValueError("Presentation slide limit exceeded")
    total = 0
    for slide in presentation.slides:
        for frame in _frames(slide):
            total += len(frame.text)
            if total > 2_000_000:
                raise ValueError("Presentation text limit exceeded")


def _load(data):
    check_office_package(data, "ppt/presentation.xml", CONTENT_TYPE)
    result = Presentation(io.BytesIO(data))
    _budget(result)
    return result


def _save(presentation):
    _budget(presentation)
    stream = io.BytesIO()
    presentation.save(stream)
    data = stream.getvalue()
    check_office_package(data, "ppt/presentation.xml", CONTENT_TYPE)
    return data


def create_pptx(document):
    if not isinstance(document, dict) or set(document) != {"slides"} or len(json.dumps(document, ensure_ascii=False)) > 2_000_000:
        raise ValueError("Presentation schema unavailable")
    slides = document["slides"]
    if not isinstance(slides, list) or not 1 <= len(slides) <= 100:
        raise ValueError("Presentation slides unavailable")
    presentation = Presentation()
    # The engine default contains an unreferenced printer configuration binary.
    # Remove that relationship from new documents; arbitrary input binaries remain denied.
    for rel in list(presentation.part.rels.values()):
        if rel.reltype == "http://schemas.openxmlformats.org/officeDocument/2006/relationships/printerSettings":
            if any(rel.rId in node.attrib.values() for node in presentation._element.iter()):
                raise ValueError("Referenced printer configuration unavailable")
            presentation.part.drop_rel(rel.rId)
    presentation.slide_width, presentation.slide_height = Inches(13.333), Inches(7.5)
    for item in slides:
        if not isinstance(item, dict) or set(item) - {"title", "paragraphs", "table", "notes"} or ("table" in item and "paragraphs" in item):
            raise ValueError("Presentation slide schema unavailable")
        slide = presentation.slides.add_slide(presentation.slide_layouts[6])
        title = slide.shapes.add_textbox(Inches(0.6), Inches(0.4), Inches(12.1), Inches(0.9)).text_frame
        title.text = _text(item.get("title", ""))
        title.paragraphs[0].font.size = Pt(32)
        title.paragraphs[0].font.bold = True
        if "table" in item:
            rows = item["table"]
            if not isinstance(rows, list) or not 1 <= len(rows) <= 50 or not isinstance(rows[0], list) or not 1 <= len(rows[0]) <= 20:
                raise ValueError("Presentation table unavailable")
            columns = len(rows[0])
            if any(not isinstance(row, list) or len(row) != columns for row in rows):
                raise ValueError("Presentation rectangular table required")
            table = slide.shapes.add_table(len(rows), columns, Inches(0.7), Inches(1.6), Inches(11.9), Inches(4.8)).table
            for i, row in enumerate(rows):
                for j, value in enumerate(row):
                    table.cell(i, j).text = _text(value)
        else:
            values = item.get("paragraphs", [])
            if not isinstance(values, list) or len(values) > 100:
                raise ValueError("Presentation paragraphs unavailable")
            frame = slide.shapes.add_textbox(Inches(0.7), Inches(1.6), Inches(11.9), Inches(5.1)).text_frame
            frame.word_wrap = True
            for i, value in enumerate(values):
                paragraph = frame.paragraphs[0] if i == 0 else frame.add_paragraph()
                paragraph.text = _text(value)
                paragraph.font.size = Pt(22)
        if "notes" in item:
            slide.notes_slide.notes_text_frame.text = _text(item["notes"])
    return _save(presentation)


def inspect_pptx(data):
    presentation = _load(data)
    slides = []
    for slide in presentation.slides:
        texts, tables = [], []
        for shape in _shapes(slide.shapes):
            if shape.has_text_frame:
                texts.append(shape.text_frame.text)
            if shape.has_table:
                tables.append([[cell.text for cell in row.cells] for row in shape.table.rows])
        slides.append({"texts": texts, "tables": tables, "notes": slide.notes_slide.notes_text_frame.text if slide.has_notes_slide and slide.notes_slide.notes_text_frame is not None else ""})
    return {"slides": slides, "size_emu": [presentation.slide_width, presentation.slide_height], "rendered": False}


def edit_pptx(data, replacements):
    if not isinstance(replacements, dict) or not replacements or len(replacements) > 100:
        raise ValueError("Presentation replacements unavailable")
    for old, new in replacements.items():
        if not _text(old):
            raise ValueError("Empty replacement unavailable")
        _text(new)
    presentation = _load(data)
    matches = total = 0
    for slide in presentation.slides:
        for frame in _frames(slide):
            for paragraph in frame.paragraphs:
                current = paragraph.text
                for old, new in replacements.items():
                    count = current.count(old)
                    if len(current) + count * (len(new) - len(old)) > 100_000:
                        raise ValueError("Presentation replacement expansion limit exceeded")
                    matches += count
                    current = current.replace(old, new)
                total += len(current)
                if total > 2_000_000:
                    raise ValueError("Presentation text limit exceeded")
                if current != paragraph.text:
                    runs = list(paragraph.runs)
                    if runs:
                        runs[0].text = current
                        for run in runs[1:]:
                            run.text = ""
                    else:
                        paragraph.text = current
    if not matches:
        raise ValueError("No presentation replacement matched")
    return _save(presentation)


@tool("office_pptx", parse_docstring=True)
def office_pptx_tool(runtime: ToolRuntime, action: str, source_path: str = "", output_path: str = "", document: dict | None = None, replacements: dict[str, str] | None = None) -> dict:
    """Create, inspect or edit an owned PPTX without rendering slides or executing content.

    Args:
        action: create, inspect or edit. Desktop rendering, animations and advanced layouts remain pending.
        source_path: Current authorized PPTX for inspect or edit.
        output_path: New /mnt/user-data/outputs/*.pptx, never overwrites; present with present_files.
        document: Create schema: slides list of title, paragraphs (strings) OR table (rectangular strings), optional notes. Uses a simple wide layout.
        replacements: Literal text replacements in slide text, tables and notes. Cross-run matches adopt the first run style; advanced roundtrip fidelity is not claimed.
    """
    return owned_office_operation(runtime, action, ".pptx", source_path, output_path, lambda: create_pptx(document), inspect_pptx, lambda data: edit_pptx(data, replacements))
