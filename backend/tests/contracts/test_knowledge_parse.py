"""R2 parse contracts: migrated extraction across supported types."""

from pathlib import Path

import pytest

from app.knowledge.parse import parse_document


def _write(path: Path, content: bytes, suffix: str) -> Path:
    target = path.with_suffix(suffix)
    target.write_bytes(content)
    return target


def test_plain_text_utf8_and_gbk(tmp_path):
    utf8 = _write(tmp_path / "a", "你好 knowledge".encode(), ".md")
    assert parse_document(utf8) == "你好 knowledge"
    gbk = _write(tmp_path / "b", "中文文档".encode("gb18030"), ".txt")
    assert parse_document(gbk) == "中文文档"


def test_json_and_csv(tmp_path):
    import json

    doc = _write(tmp_path / "c", json.dumps({"k": "值"}, ensure_ascii=False).encode(), ".json")
    parsed = parse_document(doc)
    assert '"k"' in parsed and "值" in parsed
    csv_doc = _write(tmp_path / "d", b"name,role\nalpha,guard\n", ".csv")
    assert "alpha" in parse_document(csv_doc) and "guard" in parse_document(csv_doc)


def test_html_extraction(tmp_path):
    html = _write(tmp_path / "e", b"<html><body><h1>Title</h1><p>Body text</p></body></html>", ".html")
    text = parse_document(html)
    assert "Title" in text and "Body text" in text


def test_pdf_text_layer(tmp_path):
    from pypdf import PdfWriter

    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    # Blank PDF has no text layer; parse must return empty, not raise.
    doc = _write(tmp_path / "f", b"", ".pdf")
    doc.write_bytes(_pdf_bytes(writer))
    assert parse_document(doc) == ""


def _pdf_bytes(writer) -> bytes:
    import io

    buffer = io.BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


def test_unsupported_suffix_rejected(tmp_path):
    doc = _write(tmp_path / "g", b"data", ".exe")
    with pytest.raises(ValueError, match="unsupported knowledge document extension"):
        parse_document(doc)


def test_image_ocr_disabled_in_r2(tmp_path):
    doc = _write(tmp_path / "h", b"pngdata", ".png")
    # OCR suffixes are an empty set in R2, so .png falls through to the
    # unsupported-extension branch rather than raising the OCR error.
    with pytest.raises(ValueError):
        parse_document(doc)
