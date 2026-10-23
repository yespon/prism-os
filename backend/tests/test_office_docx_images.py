"""Actual inline image parts/relationships, independent reader and native authority."""

import importlib
import io
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

import mammoth
import pytest
from PIL import Image
from test_file_access_boundaries import owned_runtime as owned_fixture
from test_file_access_boundaries import selected_runtime  # noqa: F401
from test_file_access_http import file_client as client_fixture
from test_office_docx import withdraw
from test_skill_member_tools import configured, scoped_client  # noqa: F401
from test_skill_reference_transactions import durable_sqlite  # noqa: F401

from deerflow.tools.builtins.office_docx import R, W, create_docx, inspect_docx, office_docx_tool
from deerflow.tools.builtins.office_docx_images import WP, add_docx_images

owned_runtime = owned_fixture
file_client = client_fixture
MODULE = importlib.import_module("deerflow.tools.builtins.office_docx_images")


def png():
    stream = io.BytesIO()
    Image.new("RGB", (120, 60), (12, 80, 180)).save(stream, format="PNG")
    return stream.getvalue()


def test_actual_image_package_relationship_dimensions_and_independent_reader():
    source = create_docx({"title": "图文报告", "paragraphs": ["保留正文"], "header": "页眉"})
    result = add_docx_images(source, [{"data": png(), "width_inches": 2, "alt": "实际内嵌图片"}])
    inspected, previous = inspect_docx(result), inspect_docx(source)
    assert inspected["paragraphs"] == previous["paragraphs"] + [""]
    assert all(inspected[key] == previous[key] for key in ["tables", "header", "footer"])
    with zipfile.ZipFile(io.BytesIO(result)) as package:
        root = ET.fromstring(package.read("word/document.xml"))
        drawing = next(root.iter(f"{{{WP}}}inline"))
        extent = drawing.find(f"{{{WP}}}extent")
        assert extent.attrib == {"cx": str(2 * 914400), "cy": str(914400)}
        assert drawing.find(f"{{{WP}}}docPr").get("descr") == "实际内嵌图片"
        ids = {node.get("Id"): node.get("Target") for node in ET.fromstring(package.read("word/_rels/document.xml.rels"))}
        blip = next(node for node in drawing.iter() if node.tag.endswith("}blip"))
        image = package.read("word/" + ids[blip.get(f"{{{R}}}embed")])
        with Image.open(io.BytesIO(image)) as actual:
            assert actual.size == (120, 60) and actual.convert("RGB").getpixel((0, 0)) == (12, 80, 180)
        body = root.find(f"{{{W}}}body")
        assert body[-1].tag == f"{{{W}}}sectPr"
    html = mammoth.convert_to_html(io.BytesIO(result)).value
    assert "<img" in html and "实际内嵌图片" in html and "保留正文" in html


def test_repeated_insertions_keep_existing_images_and_distinct_drawing_ids():
    source = create_docx({"paragraphs": ["正文"]})
    first = add_docx_images(source, [{"data": png()}])
    second = add_docx_images(first, [{"data": png(), "alt": "第二张"}])
    with zipfile.ZipFile(io.BytesIO(second)) as package:
        root = ET.fromstring(package.read("word/document.xml"))
        ids = [node.get("id") for node in root.iter(f"{{{WP}}}docPr")]
        assert len(ids) == 2 and len(set(ids)) == 2
        assert len([name for name in package.namelist() if name.startswith("word/media/")]) == 1
    assert mammoth.convert_to_html(io.BytesIO(second)).value.count("<img") == 2


@pytest.mark.parametrize("case", ["invalid", "svg", "width", "height", "count", "alt", "animated"])
def test_unsupported_or_unbounded_image_inputs_fail_explicitly(case):
    images = [{"data": png()}]
    if case == "invalid":
        images[0]["data"] = b"not an image"
    elif case == "svg":
        images[0]["data"] = b'<svg xmlns="http://www.w3.org/2000/svg"/>'
    elif case == "width":
        images[0]["width_inches"] = float("nan")
    elif case == "height":
        stream = io.BytesIO()
        Image.new("RGB", (1, 100)).save(stream, format="PNG")
        images[0]["data"] = stream.getvalue()
    elif case == "count":
        images *= 17
    elif case == "alt":
        images[0]["alt"] = "a" * 2001
    else:
        stream = io.BytesIO()
        Image.new("RGB", (2, 2), "red").save(stream, format="PNG", save_all=True, append_images=[Image.new("RGB", (2, 2), "blue")])
        images[0]["data"] = stream.getvalue()
    with pytest.raises((ValueError, OSError)):
        add_docx_images(create_docx({}), images)


def test_native_owned_image_insert_download_and_foreign_source_denial(file_client):
    client, _, _, runtime = file_client
    output = Path(runtime.state["thread_data"]["outputs_path"])
    uploads = Path(runtime.state["thread_data"]["uploads_path"])
    (uploads / "source.png").write_bytes(png())
    source = "/mnt/user-data/outputs/source.docx"
    assert office_docx_tool.func(runtime, "create", output_path=source, document={"paragraphs": ["图片正文"]})["status"] == "ok"
    result = office_docx_tool.func(runtime, "add_images", source_path=source, output_path="/mnt/user-data/outputs/pictured.docx", images=[{"source_path": "/mnt/user-data/uploads/source.png", "width_inches": 2}])
    assert result["status"] == "ok"
    response = client.get("/api/threads/member-thread/artifacts/mnt/user-data/outputs/pictured.docx?download=true")
    assert response.status_code == 200 and "<img" in mammoth.convert_to_html(io.BytesIO(response.content)).value
    assert client.get("/api/threads/member-thread/artifacts/mnt/user-data/outputs/pictured.docx", headers={"x-user": "user-b"}).status_code == 404
    private = output.parent / "private.png"
    private.write_bytes(png())
    assert office_docx_tool.func(runtime, "add_images", source_path=source, output_path="/mnt/user-data/outputs/foreign.docx", images=[{"source_path": str(private)}])["status"] == "unavailable"
    assert not (output / "foreign.docx").exists()


@pytest.mark.parametrize("point", ["before", "during"])
def test_image_read_or_member_withdrawal_discards_document_output(owned_runtime, monkeypatch, point):
    factory, _, _, _, runtime = owned_runtime
    output = Path(runtime.state["thread_data"]["outputs_path"])
    uploads = Path(runtime.state["thread_data"]["uploads_path"])
    (output / "source.docx").write_bytes(create_docx({"paragraphs": ["原文"]}))
    (uploads / "source.png").write_bytes(png())
    if point == "before":
        withdraw(factory)
    else:
        original = MODULE.add_docx_images

        def revoke(*args):
            result = original(*args)
            withdraw(factory)
            return result

        monkeypatch.setattr(MODULE, "add_docx_images", revoke)
    result = office_docx_tool.func(runtime, "add_images", source_path="/mnt/user-data/outputs/source.docx", output_path="/mnt/user-data/outputs/revoked.docx", images=[{"source_path": "/mnt/user-data/uploads/source.png"}])
    assert result == {"status": "unavailable", "inspection_required": True, "retry": False}
    assert not (output / "revoked.docx").exists()


def test_docx_image_schema_keeps_runtime_hidden():
    schema = office_docx_tool.tool_call_schema.model_json_schema()["properties"]
    assert "images" in schema and "runtime" not in schema


def test_jpeg_orientation_is_applied_and_metadata_is_not_embedded():
    from deerflow.tools.builtins.office_docx_images import _image

    stream = io.BytesIO()
    exif = Image.Exif()
    exif[274] = 6
    exif[270] = "PRIVATE IMAGE DESCRIPTION"
    Image.new("RGB", (120, 60), "green").save(stream, format="JPEG", exif=exif)
    data, width, height = _image(stream.getvalue())
    assert (width, height) == (60, 120)
    with Image.open(io.BytesIO(data)) as image:
        assert not image.getexif() and not image.info.get("icc_profile")
    assert b"PRIVATE IMAGE DESCRIPTION" not in data
