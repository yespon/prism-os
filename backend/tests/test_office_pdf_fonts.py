"""Actual font embedding, glyph coverage, owned inputs and native output authority."""

import hashlib
import importlib
import io
import json
import struct
from pathlib import Path

import pytest
from PIL import Image
from test_file_access_boundaries import owned_runtime as owned_fixture
from test_file_access_boundaries import selected_runtime  # noqa: F401
from test_file_access_http import file_client as client_fixture
from test_office_docx import withdraw
from test_skill_member_tools import configured, scoped_client  # noqa: F401
from test_skill_reference_transactions import durable_sqlite  # noqa: F401

from deerflow.tools.builtins.office_fonts import font_coverage
from deerflow.tools.builtins.office_pdf import create_pdf, inspect_pdf, office_pdf_tool, render_pdf_page

owned_runtime = owned_fixture
file_client = client_fixture
FIXTURE = Path(__file__).parent / "fixtures/pdf-fonts"
FONT = (FIXTURE / "NotoMono-Regular.ttf").read_bytes()
SPEC = {"pages": [["PrismOS Ελληνικά Русский café", "Horizontal Unicode font embedding"]]}
MODULE = importlib.import_module("deerflow.tools.builtins.office_pdf")


def test_original_test_font_identity_and_actual_unicode_pdf():
    assert hashlib.sha256(FONT).hexdigest() == json.loads((FIXTURE / "provenance.json").read_text())["sha256"]
    data = create_pdf(SPEC, font_bytes=FONT)
    text = inspect_pdf(data)["pages"][0]["text"]
    assert "Ελληνικά Русский café" in text
    assert b"/FontFile2" in data  # A font program is actually embedded.
    with Image.open(io.BytesIO(render_pdf_page(data))) as image:
        assert image.convert("RGB").getextrema() != ((255, 255),) * 3
    assert all(font_coverage(FONT)(ord(c)) for c in "Ελληνικά Русский")
    assert not font_coverage(FONT)(ord("中"))


@pytest.mark.parametrize("text", ["中文缺字", "😀", "עברית", "العربية", "e\u0301", "hidden\u200djoiner"])
def test_missing_glyphs_and_unimplemented_shaping_are_explicitly_rejected(text):
    with pytest.raises(ValueError, match="coverage|shaping|text"):
        create_pdf({"pages": [[text]]}, font_bytes=FONT)


@pytest.mark.parametrize("mutation", ["truncated", "offset", "restricted", "bitmap", "missing-cmap", "collection"])
def test_malformed_or_embedding_restricted_fonts_fail_before_native_parse(mutation, monkeypatch):
    data = bytearray(FONT)
    count = struct.unpack_from(">H", data, 4)[0]
    tables = {struct.unpack_from(">4s", data, 12 + index * 16)[0]: 12 + index * 16 for index in range(count)}
    if mutation == "truncated":
        data = data[:20]
    elif mutation == "offset":
        struct.pack_into(">I", data, tables[b"cmap"] + 8, len(data) + 1)
    elif mutation in {"restricted", "bitmap"}:
        start = struct.unpack_from(">I", data, tables[b"OS/2"] + 8)[0]
        struct.pack_into(">H", data, start + 8, 2 if mutation == "restricted" else 0x200)
    elif mutation == "missing-cmap":
        data[tables[b"cmap"] : tables[b"cmap"] + 4] = b"NOPE"
    else:
        data = bytearray(b"ttcf\x00\x01\x00\x00" + struct.pack(">II", 1, 0x7FFFFFFF))

    def native(*args):
        pytest.fail("Malformed font reached the native parser")

    monkeypatch.setattr(MODULE.raw, "FPDFText_LoadFont", native)
    with pytest.raises(ValueError):
        create_pdf(SPEC, font_bytes=bytes(data))


def test_authorized_uploaded_font_native_download_and_foreign_font_denial(file_client):
    client, _, _, runtime = file_client
    uploads = Path(runtime.state["thread_data"]["uploads_path"])
    (uploads / "source.ttf").write_bytes(FONT)
    virtual = "/mnt/user-data/uploads/source.ttf"
    result = office_pdf_tool.func(runtime, "create", output_path="/mnt/user-data/outputs/unicode.pdf", document=SPEC, font_path=virtual)
    assert result["status"] == "ok" and result["source_font_sha256"] == hashlib.sha256(FONT).hexdigest()
    response = client.get("/api/threads/member-thread/artifacts/mnt/user-data/outputs/unicode.pdf?download=true")
    assert response.status_code == 200 and "Ελληνικά" in inspect_pdf(response.content)["pages"][0]["text"]
    assert client.get("/api/threads/member-thread/artifacts/mnt/user-data/outputs/unicode.pdf", headers={"x-user": "user-b"}).status_code == 404
    outside = uploads.parent / "private.ttf"
    outside.write_bytes(FONT)
    for path in [str(outside), "/etc/private.ttf", "/mnt/user-data/uploads/../private.ttf"]:
        assert office_pdf_tool.func(runtime, "create", output_path="/mnt/user-data/outputs/foreign.pdf", document=SPEC, font_path=path)["status"] == "unavailable"
    assert not (Path(runtime.state["thread_data"]["outputs_path"]) / "foreign.pdf").exists()


@pytest.mark.parametrize("point", ["before", "during"])
def test_font_member_withdrawal_cannot_publish(owned_runtime, monkeypatch, point):
    factory, _, _, _, runtime = owned_runtime
    (Path(runtime.state["thread_data"]["uploads_path"]) / "source.ttf").write_bytes(FONT)
    if point == "before":
        withdraw(factory)
    else:
        original = MODULE.create_pdf

        def revoke(*args, **kwargs):
            result = original(*args, **kwargs)
            withdraw(factory)
            return result

        monkeypatch.setattr(MODULE, "create_pdf", revoke)
    result = office_pdf_tool.func(runtime, "create", output_path="/mnt/user-data/outputs/revoked.pdf", document=SPEC, font_path="/mnt/user-data/uploads/source.ttf")
    assert result == {"status": "unavailable", "inspection_required": True, "retry": False}
    assert not (Path(runtime.state["thread_data"]["outputs_path"]) / "revoked.pdf").exists()


def test_selected_fixture_font_supports_actual_native_text_and_visible_pixels(file_client):
    import os

    source = Path(os.environ.get("PRISMOS_OFFICE_FONT_CHECK", FIXTURE / "NotoMono-Regular.ttf"))
    text = "PrismOS 中文字体与预算 123" if os.environ.get("PRISMOS_OFFICE_FONT_CHECK") else "PrismOS Ελληνικά Русский"
    client, _, _, runtime = file_client
    (Path(runtime.state["thread_data"]["uploads_path"]) / "selected.ttc").write_bytes(source.read_bytes())
    result = office_pdf_tool.func(runtime, "create", output_path="/mnt/user-data/outputs/selected.pdf", document={"pages": [[text]]}, font_path="/mnt/user-data/uploads/selected.ttc")
    assert result["status"] == "ok"
    response = client.get("/api/threads/member-thread/artifacts/mnt/user-data/outputs/selected.pdf?download=true")
    assert response.status_code == 200 and text in inspect_pdf(response.content)["pages"][0]["text"]
    png = render_pdf_page(response.content)
    with Image.open(io.BytesIO(png)) as image:
        assert image.convert("RGB").getextrema() != ((255, 255),) * 3


def test_font_path_schema_and_action_are_explicit(owned_runtime):
    schema = office_pdf_tool.tool_call_schema.model_json_schema()["properties"]
    assert "font_path" in schema and "runtime" not in schema
    assert office_pdf_tool.func(owned_runtime[-1], "inspect", font_path="/mnt/user-data/uploads/font.ttf")["status"] == "unavailable"


def test_combined_character_maps_have_one_total_budget_before_native_parse(monkeypatch):
    data = bytearray(FONT)
    count = struct.unpack_from(">H", data, 4)[0]
    cmap_record = next(12 + i * 16 for i in range(count) if data[12 + i * 16 : 16 + i * 16] == b"cmap")
    groups = 60_000
    payload = struct.pack(">HHIII", 12, 0, 16 + 12 * groups, 0, groups) + b"".join(struct.pack(">III", 2 * i, 2 * i, 1) for i in range(groups))
    start = 20
    cmap = struct.pack(">HH", 0, 2) + struct.pack(">HHI", 3, 10, start) + struct.pack(">HHI", 0, 4, start + len(payload)) + payload + payload
    struct.pack_into(">II", data, cmap_record + 8, len(data), len(cmap))
    data.extend(cmap)

    def native(*args):
        pytest.fail("Character map budget exceeded before native parsing")

    monkeypatch.setattr(MODULE.raw, "FPDFText_LoadFont", native)
    with pytest.raises(ValueError, match="total character map limit"):
        create_pdf(SPEC, font_bytes=bytes(data))


def test_http_font_upload_to_native_generation_and_current_download(file_client, monkeypatch):
    from types import SimpleNamespace

    from app.gateway.routers import uploads
    from deerflow.uploads import manager

    client, _, paths, runtime = file_client
    calls = []

    def acquire(thread_id, **identity):
        calls.append((thread_id, identity))
        return "local-font-http"

    monkeypatch.setattr(manager, "get_paths", lambda: paths)
    monkeypatch.setattr(uploads, "get_sandbox_provider", lambda: SimpleNamespace(acquire=acquire, get=lambda _: SimpleNamespace()))
    endpoint = "/api/threads/member-thread/uploads"
    uploaded = client.post(endpoint, files={"files": ("source.ttf", FONT, "font/ttf")})
    assert uploaded.status_code == 200, uploaded.text
    item = uploaded.json()["files"][0]
    assert item["virtual_path"] == "/mnt/user-data/uploads/source.ttf"
    assert (Path(runtime.state["thread_data"]["uploads_path"]) / "source.ttf").read_bytes() == FONT
    assert calls == [("member-thread", {"user_id": "user-a", "tenant_id": "tenant-a"})]
    for headers in [{"x-user": "user-b"}, {"x-tenant": "tenant-b"}]:
        assert client.post(endpoint, headers=headers, files={"files": ("denied.ttf", FONT, "font/ttf")}).status_code == 404
    assert len(calls) == 1
    result = office_pdf_tool.func(runtime, "create", output_path="/mnt/user-data/outputs/http-font.pdf", document=SPEC, font_path=item["virtual_path"])
    assert result["status"] == "ok"
    response = client.get("/api/threads/member-thread/artifacts/mnt/user-data/outputs/http-font.pdf?download=true")
    assert response.status_code == 200 and "Ελληνικά" in inspect_pdf(response.content)["pages"][0]["text"]


def test_aliased_font_table_payloads_cannot_amplify_copy_budget_before_native_parse(monkeypatch):
    count = struct.unpack_from(">H", FONT, 4)[0]
    data = bytearray(FONT)
    payload = len(data)
    data.extend(b"x" * 65536)
    face = len(data)
    header = bytearray(FONT[:12])
    struct.pack_into(">H", header, 4, count + 128)
    records = FONT[12 : 12 + count * 16] + b"".join(struct.pack(">4sIII", f"{i:04x}".encode(), 0, payload, 65536) for i in range(128))
    data.extend(header + records)
    data[:16] = b"ttcf" + struct.pack(">III", 0x10000, 1, face)

    def native(*args):
        pytest.fail("Aliased table budget reached native parsing")

    monkeypatch.setattr(MODULE.raw, "FPDFText_LoadFont", native)
    with pytest.raises(ValueError, match="total table budget"):
        create_pdf(SPEC, font_bytes=bytes(data))
