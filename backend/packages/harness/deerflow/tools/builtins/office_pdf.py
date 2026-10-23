"""Independent PDF extraction, page composition and bounded page rendering."""

import ctypes
import hashlib
import io
import json
import math
import struct
import threading
import unicodedata

import pypdfium2 as pdfium
import pypdfium2.raw as raw
from langchain.tools import ToolRuntime, tool

from deerflow.runtime import current_file_access

from .office_common import MAX_BYTES, owned_office_operation
from .office_fonts import font_character_map

PDF_LOCK = threading.RLock()  # PDFium is not thread-safe across documents.


def _load(data):
    if not isinstance(data, bytes) or len(data) > MAX_BYTES or not data.startswith(b"%PDF-"):
        raise ValueError("PDF input unavailable")
    document = pdfium.PdfDocument(data)
    if not 1 <= len(document) <= 100:
        document.close()
        raise ValueError("PDF page limit exceeded")
    return document


def _save(document):
    stream = io.BytesIO()
    document.save(stream)
    result = stream.getvalue()
    if len(result) > MAX_BYTES:
        raise ValueError("PDF output size exceeded")
    return result


def _line_text(line, coverage):
    if not isinstance(line, str) or len(line) > 200 or any(ord(c) < 32 or 127 <= ord(c) < 160 or unicodedata.category(c) in {"Cf", "Cs"} for c in line):
        raise ValueError("PDF text unavailable")
    if coverage is None:
        if any(ord(c) > 255 for c in line):
            raise ValueError("Basic PDF font requires printable Latin-1; an authorized Unicode font is required")
    elif any(unicodedata.combining(c) or unicodedata.bidirectional(c) in {"R", "AL", "AN"} or not coverage(ord(c)) for c in line):
        raise ValueError("PDF font glyph coverage or complex shaping unavailable")


def _unicode_font(document, data, glyphs, characters):
    """Keep one CID per Unicode character, including aliases sharing one glyph.

    PDFium's automatic mapping can lose U+0020 when a font maps both space and
    no-break space to the same glyph. Explicit maps preserve both text and ink.
    """
    if len(characters) > 65535:
        raise ValueError("PDF Unicode character limit exceeded")
    glyph_map = bytearray(2 * (len(characters) + 1))
    entries = []
    for cid, code in enumerate(characters, 1):
        struct.pack_into(">H", glyph_map, cid * 2, glyphs(code))
        entries.append(f"<{cid:04X}> <{chr(code).encode('utf-16-be').hex().upper()}>")
    sections = [
        "/CIDInit /ProcSet findresource begin",
        "12 dict begin",
        "begincmap",
        "/CIDSystemInfo << /Registry (Adobe) /Ordering (UCS) /Supplement 0 >> def",
        "/CMapName /PrismOS-Unicode def",
        "/CMapType 2 def",
        "1 begincodespacerange",
        "<0000> <FFFF>",
        "endcodespacerange",
    ]
    for start in range(0, len(entries), 100):
        block = entries[start : start + 100]
        sections.extend([f"{len(block)} beginbfchar", *block, "endbfchar"])
    sections.extend(["endcmap", "CMapName currentdict /CMap defineresource pop", "end", "end"])
    cmap = "\n".join(sections).encode("ascii")
    font_data = (ctypes.c_ubyte * len(data)).from_buffer_copy(data)
    cid_data = (ctypes.c_ubyte * len(glyph_map)).from_buffer_copy(glyph_map)
    font = raw.FPDFText_LoadCidType2Font(document, font_data, len(data), cmap, cid_data, len(glyph_map))
    if not font:
        raise ValueError("PDF Unicode font could not be loaded")
    return font


def create_pdf(spec, *, font_bytes=None):
    if not isinstance(spec, dict) or set(spec) != {"pages"} or len(json.dumps(spec)) > 2_000_000:
        raise ValueError("PDF schema unavailable")
    pages = spec["pages"]
    if not isinstance(pages, list) or not 1 <= len(pages) <= 100:
        raise ValueError("PDF pages unavailable")
    glyphs = font_character_map(font_bytes) if font_bytes is not None else None
    coverage = (lambda code: bool(glyphs(code))) if glyphs else None
    characters = set()
    for lines in pages:
        if not isinstance(lines, list) or len(lines) > 42:
            raise ValueError("PDF line limit exceeded")
        for line in lines:
            _line_text(line, coverage)
            if glyphs:
                characters.update(map(ord, line))
    with PDF_LOCK:
        document = pdfium.PdfDocument.new()
        font = None
        try:
            if characters:
                font = _unicode_font(document, font_bytes, glyphs, sorted(characters))
            for lines in pages:
                if not isinstance(lines, list) or len(lines) > 42:
                    raise ValueError("PDF line limit exceeded")
                page = document.new_page(595, 842)
                try:
                    for index, line in enumerate(lines):
                        _line_text(line, coverage)
                        # PDFium traps on an empty text object. Keep the line index
                        # for layout, but represent blank lines without native objects.
                        if not line:
                            continue
                        handle = raw.FPDFPageObj_CreateTextObj(document, font, 12) if font else raw.FPDFPageObj_NewTextObj(document, b"Helvetica", 12)
                        if not handle:
                            raise ValueError("PDF text unavailable")
                        obj = pdfium.PdfObject(handle, pdf=document)
                        try:
                            encoded = (line + "\x00").encode("utf-16-le")
                            text = (ctypes.c_ushort * (len(encoded) // 2)).from_buffer_copy(encoded)
                            if not raw.FPDFText_SetText(obj, text):
                                raise ValueError("PDF text unavailable")
                            left, bottom, right, top = (ctypes.c_float() for _ in range(4))
                            if not raw.FPDFPageObj_GetBounds(obj, ctypes.byref(left), ctypes.byref(bottom), ctypes.byref(right), ctypes.byref(top)) or right.value - left.value > 499:
                                raise ValueError("PDF line exceeds page width")
                            raw.FPDFPageObj_Transform(obj, 1, 0, 0, 1, 48, 794 - 18 * index)
                            page.insert_obj(obj)
                        finally:
                            obj.close()
                    if not raw.FPDFPage_GenerateContent(page):
                        raise ValueError("PDF content unavailable")
                finally:
                    page.close()
            return _save(document)
        finally:
            if font:
                raw.FPDFFont_Close(font)
            document.close()


def inspect_pdf(data):
    with PDF_LOCK:
        document = _load(data)
        try:
            pages, total = [], 0
            for index in range(len(document)):
                page = document[index]
                try:
                    textpage = page.get_textpage()
                    try:
                        count = textpage.count_chars()
                        total += count
                        if count > 100_000 or total > 2_000_000:
                            raise ValueError("PDF text limit exceeded")
                        pages.append({"page": index + 1, "text": textpage.get_text_range(), "size_points": list(page.get_size())})
                    finally:
                        textpage.close()
                finally:
                    page.close()
            return {"pages": pages, "ocr_performed": False, "forms_executed": False}
        finally:
            document.close()


def select_pdf_pages(data, pages):
    with PDF_LOCK:
        source = _load(data)
        target = pdfium.PdfDocument.new()
        try:
            if not isinstance(pages, list) or not 1 <= len(pages) <= 100 or any(type(p) is not int or not 1 <= p <= len(source) for p in pages):
                raise ValueError("PDF page selection unavailable")
            target.import_pages(source, pages=[p - 1 for p in pages])
            return _save(target)
        finally:
            target.close()
            source.close()


def merge_pdf(documents):
    if not isinstance(documents, list) or not 1 <= len(documents) <= 16 or sum(len(data) for data in documents) > 32 * 1024 * 1024:
        raise ValueError("PDF merge size unavailable")
    with PDF_LOCK:
        target = pdfium.PdfDocument.new()
        try:
            count = 0
            for data in documents:
                source = _load(data)
                try:
                    count += len(source)
                    if count > 100:
                        raise ValueError("PDF merge page limit exceeded")
                    target.import_pages(source)
                finally:
                    source.close()
            return _save(target)
        finally:
            target.close()


def render_pdf_page(data, page_number=1, scale=1):
    if type(page_number) is not int or type(scale) not in {float, int} or not math.isfinite(scale) or not 0.25 <= scale <= 3:
        raise ValueError("PDF rendering scale unavailable")
    with PDF_LOCK:
        document = _load(data)
        try:
            if not 1 <= page_number <= len(document):
                raise ValueError("PDF rendering page unavailable")
            page = document[page_number - 1]
            try:
                width, height = page.get_size()
                if width <= 0 or height <= 0 or not math.isfinite(width * height) or math.ceil(width * scale) * math.ceil(height * scale) > 5_000_000:
                    raise ValueError("PDF render pixel limit exceeded")
                bitmap = page.render(scale=scale, may_draw_forms=False)
                try:
                    image = bitmap.to_pil()
                    try:
                        stream = io.BytesIO()
                        image.save(stream, format="PNG")
                        return stream.getvalue()
                    finally:
                        image.close()
                finally:
                    bitmap.close()
            finally:
                page.close()
        finally:
            document.close()


@tool("office_pdf", parse_docstring=True)
def office_pdf_tool(
    runtime: ToolRuntime, action: str, source_path: str = "", output_path: str = "", document: dict | None = None, pages: list[int] | None = None, sources: list[str] | None = None, page_number: int = 1, scale: float = 1, font_path: str = ""
) -> dict:
    """Inspect PDF text, select/reorder pages, merge owned PDFs, render a bounded PNG, or create a basic text PDF.

    Args:
        action: create, inspect, select, merge or render. No OCR, form filling, JavaScript execution or advanced document rendering claims.
        source_path: Current authorized PDF for inspect/select/render.
        output_path: New owned outputs PDF, or PNG for render; never overwrites. Present with present_files.
        document: Create schema: pages (list of lists of lines). Default font supports printable Latin-1. An authorized TrueType font enables horizontal precomposed Unicode/CJK
            text with actual glyph coverage. Complex shaping/RTL, automatic wrapping and advanced layout remain pending. Lines must fit A4 page width.
        pages: Select action: 1-based page numbers, supporting reordering and repeats.
        sources: Merge action: current authorized PDF virtual paths, checked before and after processing; total max 100 pages.
        page_number: Render action: 1-based PDF page.
        scale: Render action: 0.25..3; total image limited to five million pixels.
        font_path: Create only: current authorized uploaded/owned .ttf or .ttc (first face), max 32 MiB. No implicit host font lookup. Missing glyphs or restricted embedding flags fail explicitly.
    """

    font_receipt = {}
    if font_path and action != "create":
        return {"status": "unavailable", "inspection_required": True, "retry": False}

    def create_owned():
        if not font_path:
            return create_pdf(document)
        if not isinstance(font_path, str) or not font_path.lower().endswith((".ttf", ".ttc")):
            raise ValueError("Owned TrueType font required")
        data = current_file_access(runtime, "read_bytes", font_path)
        if not isinstance(data, bytes):
            raise PermissionError("Current font authority required")
        result = create_pdf(document, font_bytes=data)
        current_file_access(runtime, "read_bytes", font_path)
        font_receipt["source_font_sha256"] = hashlib.sha256(data).hexdigest()
        return result

    def merge_owned():
        if not isinstance(sources, list) or not 1 <= len(sources) <= 16 or any(not isinstance(path, str) or not path.lower().endswith(".pdf") for path in sources):
            raise ValueError("PDF sources unavailable")
        inputs, total = [], 0
        for path in sources:
            data = current_file_access(runtime, "read_bytes", path)
            if data is None:
                raise PermissionError("Current PDF authority required")
            total += len(data)
            if total > 32 * 1024 * 1024:
                raise ValueError("PDF merge size exceeded")
            inputs.append(data)
        result = merge_pdf(inputs)
        for path in sources:
            current_file_access(runtime, "read_bytes", path)
        return result

    if action == "merge":
        return owned_office_operation(runtime, "create", ".pdf", "", output_path, merge_owned, inspect_pdf, lambda data: data)
    if action == "render":
        return owned_office_operation(runtime, "edit", ".png", source_path, output_path, lambda: b"", inspect_pdf, lambda data: render_pdf_page(data, page_number, scale), source_extension=".pdf")
    mapped = "edit" if action == "select" else action
    result = owned_office_operation(runtime, mapped, ".pdf", source_path, output_path, create_owned, inspect_pdf, lambda data: select_pdf_pages(data, pages))
    if result["status"] == "ok":
        result.update(font_receipt)
    return result
