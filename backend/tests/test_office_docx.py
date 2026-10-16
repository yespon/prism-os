"""Independent actual DOCX packages through original current file authority."""

import importlib
import io
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest
from sqlalchemy import select
from test_file_access_boundaries import owned_runtime as owned_fixture
from test_file_access_boundaries import selected_runtime  # noqa: F401
from test_file_access_http import file_client as client_fixture
from test_skill_member_tools import configured, scoped_client  # noqa: F401
from test_skill_reference_transactions import durable_sqlite  # noqa: F401

from deerflow.database.models import TenantMembership
from deerflow.tools.builtins.office_docx import W, create_docx, edit_docx, inspect_docx, office_docx_tool

owned_runtime = owned_fixture
file_client = client_fixture
module = importlib.import_module("deerflow.tools.builtins.office_docx")
OUTPUT = "/mnt/user-data/outputs/report.docx"
DOCUMENT = {"title": "季度报告", "paragraphs": [{"text": "执行摘要", "style": "Heading1"}, "完成事项 & <后续>"], "tables": [[["部门", "结果"], ["研发", "已完成"]]], "header": "内部资料", "footer": "审阅草稿"}


def test_actual_docx_package_structure_styles_headers_tables_and_unicode():
    data = create_docx(DOCUMENT)
    with zipfile.ZipFile(io.BytesIO(data)) as package:
        root = ET.fromstring(package.read("word/document.xml"))
        assert [p.get(f"{{{W}}}val") for p in root.iter(f"{{{W}}}pStyle")] == ["Title", "Heading1"]
        assert len(list(root.iter(f"{{{W}}}tbl"))) == 1
        assert package.read("word/header.xml") and package.read("word/footer.xml")
        assert "styles.xml" in package.read("word/_rels/document.xml.rels").decode()
    result = inspect_docx(data)
    assert "完成事项 & <后续>" in result["paragraphs"]
    assert result["tables"] == DOCUMENT["tables"]
    assert (result["header"], result["footer"]) == ("内部资料", "审阅草稿")


def test_existing_docx_cross_run_edit_and_non_document_parts_preserved():
    parts = {}
    with zipfile.ZipFile(io.BytesIO(create_docx(DOCUMENT))) as package:
        parts.update({p: package.read(p) for p in package.namelist()})
    root = ET.fromstring(parts["word/document.xml"])
    p = root.find(f"{{{W}}}body/{{{W}}}p")
    p.find(f"{{{W}}}r/{{{W}}}t").text = "季度"
    ET.SubElement(ET.SubElement(p, f"{{{W}}}r"), f"{{{W}}}t").text = "报告"
    parts["word/document.xml"] = ET.tostring(root)
    parts["docProps/custom.xml"] = b'<properties><unchanged value="keep"/></properties>'
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as package:
        for name, data in parts.items():
            package.writestr(name, data)
    changed, matches = edit_docx(output.getvalue(), {"季度报告": "年度总结", "研发": "平台", "内部资料": "内部审阅"})
    assert matches == 3
    result = inspect_docx(changed)
    assert result["paragraphs"][0] == "年度总结" and result["tables"][0][1][0] == "平台"
    assert result["header"] == "内部审阅"
    with zipfile.ZipFile(io.BytesIO(changed)) as package:
        assert package.read("docProps/custom.xml") == parts["docProps/custom.xml"]


def test_tool_schema_available_without_injected_runtime_and_native_registration():
    from deerflow.tools.tools import BUILTIN_TOOLS

    assert office_docx_tool in BUILTIN_TOOLS
    schema = office_docx_tool.tool_call_schema.model_json_schema()
    assert "runtime" not in schema["properties"]
    assert set(schema["properties"]) == {"action", "source_path", "output_path", "document", "replacements", "images"}


def test_native_create_inspect_edit_and_original_artifact_download(file_client):
    client, _, _, runtime = file_client
    created = office_docx_tool.func(runtime, "create", output_path=OUTPUT, document=DOCUMENT)
    assert created["status"] == "ok" and created["bytes"] > 100
    response = client.get("/api/threads/member-thread/artifacts/mnt/user-data/outputs/report.docx?download=true")
    assert response.status_code == 200 and response.headers["cache-control"] == "no-store"
    assert inspect_docx(response.content)["tables"] == DOCUMENT["tables"]
    inspected = office_docx_tool.func(runtime, "inspect", source_path=OUTPUT)
    assert inspected["status"] == "ok" and "季度报告" in inspected["document"]["paragraphs"]
    updated = office_docx_tool.func(runtime, "replace", source_path=OUTPUT, output_path=OUTPUT.replace("report", "edited"), replacements={"季度报告": "周报"})
    assert updated["status"] == "ok" and updated["replacements"] == 1
    original = Path(runtime.state["thread_data"]["outputs_path"]) / "report.docx"
    assert inspect_docx(original.read_bytes())["paragraphs"][0] == "季度报告"
    assert client.get("/api/threads/member-thread/artifacts/mnt/user-data/outputs/report.docx", headers={"x-user": "user-b"}).status_code == 404


@pytest.mark.parametrize("path", ["/etc/private.docx", "/mnt/user-data/outputs/../uploads/fake.docx", "/mnt/user-data/uploads/new.docx", "/mnt/user-data/outputs/nested/../../x.docx", "/mnt/user-data/outputs/fake.docm"])
def test_output_never_escapes_owned_outputs(owned_runtime, path):
    runtime = owned_runtime[-1]
    result = office_docx_tool.func(runtime, "create", output_path=path, document=DOCUMENT)
    assert result["status"] == "unavailable"
    assert not list(Path(runtime.state["thread_data"]["uploads_path"]).iterdir())


@pytest.mark.parametrize("alias", ["existing", "symlink", "hardlink", "ancestor"])
def test_exclusive_output_does_not_overwrite_or_follow_aliases(owned_runtime, alias):
    import os

    runtime = owned_runtime[-1]
    root = Path(runtime.state["thread_data"]["outputs_path"])
    private = root.parent / "private.docx"
    private.write_bytes(b"KEEP PRIVATE")
    target = root / "report.docx"
    if alias == "existing":
        target.write_bytes(b"KEEP PRIVATE")
    elif alias == "symlink":
        target.symlink_to(private)
    elif alias == "hardlink":
        os.link(private, target)
    else:
        root.rename(root.with_name("original-output"))
        root.symlink_to(root.with_name("original-output"), target_is_directory=True)
    result = office_docx_tool.func(runtime, "create", output_path=OUTPUT, document=DOCUMENT)
    assert result["status"] == "unavailable" and result["retry"] is False
    assert private.read_bytes() == b"KEEP PRIVATE"
    if target.exists():
        assert target.read_bytes() == b"KEEP PRIVATE"


def withdraw(factory):
    async def change():
        async with factory() as session:
            member = (await session.exec(select(TenantMembership).where(TenantMembership.tenant_id == "tenant-a", TenantMembership.user_id == "user-a"))).scalars().one()
            member.status = "inactive"
            session.add(member)
            await session.commit()

    from app.runtime_adapters import _run_async

    _run_async(change())


@pytest.mark.parametrize("action", ["create", "inspect", "replace"])
def test_current_membership_revocation_blocks_all_document_operations(owned_runtime, action):
    factory, _, _, _, runtime = owned_runtime
    root = Path(runtime.state["thread_data"]["outputs_path"])
    (root / "source.docx").write_bytes(create_docx(DOCUMENT))
    withdraw(factory)
    result = office_docx_tool.func(runtime, action, source_path="/mnt/user-data/outputs/source.docx", output_path=OUTPUT, document=DOCUMENT, replacements={"季度": "年度"})
    assert result == {"status": "unavailable", "inspection_required": True, "retry": False}
    assert not (root / "report.docx").exists()


def test_revocation_during_document_creation_prevents_publish(owned_runtime, monkeypatch):
    factory, _, _, _, runtime = owned_runtime
    original = module.create_docx

    def revoke(document):
        data = original(document)
        withdraw(factory)
        return data

    monkeypatch.setattr(module, "create_docx", revoke)
    assert office_docx_tool.func(runtime, "create", output_path=OUTPUT, document=DOCUMENT)["status"] == "unavailable"
    assert not (Path(runtime.state["thread_data"]["outputs_path"]) / "report.docx").exists()


def test_revocation_after_parsing_does_not_return_private_document(owned_runtime, monkeypatch):
    factory, _, _, _, runtime = owned_runtime
    (Path(runtime.state["thread_data"]["outputs_path"]) / "report.docx").write_bytes(create_docx(DOCUMENT))
    original = module.inspect_docx

    def revoke(data):
        result = original(data)
        withdraw(factory)
        return result

    monkeypatch.setattr(module, "inspect_docx", revoke)
    result = office_docx_tool.func(runtime, "inspect", source_path=OUTPUT)
    assert result["status"] == "unavailable" and "季度报告" not in str(result)


@pytest.mark.parametrize("kind", ["external", "entity", "duplicate", "traversal", "macro", "field", "wrong-main"])
def test_unsafe_or_forged_packages_rejected_without_fetch_or_execution(kind):
    with zipfile.ZipFile(io.BytesIO(create_docx(DOCUMENT))) as package:
        parts = {name: package.read(name) for name in package.namelist()}
    if kind == "external":
        parts["word/_rels/document.xml.rels"] = b'<Relationships><Relationship TargetMode="External" Target="file:///etc/private"/></Relationships>'
    elif kind == "entity":
        parts["word/document.xml"] = '<!DOCTYPE x [<!ENTITY secret SYSTEM "file:///etc/private">]><x>&secret;</x>'.encode("utf-16")
    elif kind == "traversal":
        parts["../private.xml"] = b"<x/>"
    elif kind == "macro":
        parts["word/vbaProject.bin"] = b"active"
    elif kind == "field":
        root = ET.fromstring(parts["word/document.xml"])
        ET.SubElement(root, f"{{{W}}}instrText").text = "DDEAUTO active"
        parts["word/document.xml"] = ET.tostring(root)
    elif kind == "wrong-main":
        parts["[Content_Types].xml"] = parts["[Content_Types].xml"].replace(b"wordprocessingml.document.main", b"wordprocessingml.template.main")
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as package:
        for name, data in parts.items():
            package.writestr(name, data)
        if kind == "duplicate":
            with pytest.warns(UserWarning):
                package.writestr("word/document.xml", parts["word/document.xml"])
    with pytest.raises(ValueError):
        inspect_docx(out.getvalue())


def test_standalone_or_forged_host_runtime_does_not_get_document_write(tmp_path, monkeypatch):
    from types import SimpleNamespace

    import deerflow.runtime as adapters

    monkeypatch.setattr(adapters, "_file_access_provider", None)
    monkeypatch.delenv("PRISMOS_RUNTIME_ADAPTER_MODULE", raising=False)
    runtime = SimpleNamespace(context={}, state={"thread_data": {"outputs_path": str(tmp_path)}})
    assert office_docx_tool.func(runtime, "create", output_path=OUTPUT, document=DOCUMENT)["status"] == "unavailable"
    assert not list(tmp_path.iterdir())


def test_output_published_only_as_complete_package(owned_runtime, monkeypatch):
    from deerflow.skills import install_receipts

    runtime = owned_runtime[-1]
    destination = Path(runtime.state["thread_data"]["outputs_path"]) / "report.docx"
    original = install_receipts.publish_no_replace
    observations = []

    def observe(source, target, **kwargs):
        assert not destination.exists()
        assert inspect_docx(source.read_bytes())["tables"] == DOCUMENT["tables"]
        observations.append(True)
        original(source, target, **kwargs)

    monkeypatch.setattr(install_receipts, "publish_no_replace", observe)
    assert office_docx_tool.func(runtime, "create", output_path=OUTPUT, document=DOCUMENT)["status"] == "ok"
    assert observations == [True]
    assert not list(destination.parent.glob(".prismos-stage-output-*"))


@pytest.mark.parametrize("failure", ["write", "publish", "post-publish"])
def test_failed_binary_publication_preserves_original_or_complete_unknown_output(owned_runtime, monkeypatch, failure):
    from deerflow.sandbox import file_access
    from deerflow.skills import install_receipts

    factory, _, _, _, runtime = owned_runtime
    root = Path(runtime.state["thread_data"]["outputs_path"])
    if failure == "write":
        original_write = file_access.os.write
        calls = []

        def fail_partial(fd, data):
            if len(data) > 100:
                if calls:
                    raise OSError("Controlled disk failure")
                calls.append(True)
                return original_write(fd, data[:10])
            return original_write(fd, data)

        monkeypatch.setattr(file_access.os, "write", fail_partial)
    else:
        original_publish = install_receipts.publish_no_replace

        def fail_publish(source, target, **kwargs):
            if failure == "publish":
                raise OSError("Controlled publish failure")
            original_publish(source, target, **kwargs)
            # Business publication happened; losing current authority must not
            # pretend rollback or success. Preserve the complete owned result.
            withdraw(factory)

        monkeypatch.setattr(install_receipts, "publish_no_replace", fail_publish)
    result = office_docx_tool.func(runtime, "create", output_path=OUTPUT, document=DOCUMENT)
    assert result == {"status": "unavailable", "inspection_required": True, "retry": False}
    assert not list(root.glob(".prismos-stage-output-*"))
    if failure == "post-publish":
        async def current_member():
            async with factory() as session:
                row = (await session.exec(select(TenantMembership).where(TenantMembership.tenant_id == "tenant-a", TenantMembership.user_id == "user-a"))).scalars().one()
                return row.status

        from app.runtime_adapters import _run_async

        assert _run_async(current_member()) == "inactive"
        assert inspect_docx((root / "report.docx").read_bytes())["tables"] == DOCUMENT["tables"]
    else:
        assert not (root / "report.docx").exists()


def test_independent_document_reader_accepts_created_file():
    import mammoth

    result = mammoth.extract_raw_text(io.BytesIO(create_docx(DOCUMENT)))
    assert "季度报告" in result.value and "研发" in result.value


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
