import asyncio
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import UploadFile

from app.gateway.routers import uploads


def _mock_request() -> SimpleNamespace:
    return SimpleNamespace(
        state=SimpleNamespace(
            user_id="u-test",
            tenant_id="tenant-a",
        )
    )


def test_upload_files_writes_thread_storage_and_skips_local_sandbox_sync(tmp_path):
    thread_uploads_dir = tmp_path / "uploads"
    thread_uploads_dir.mkdir(parents=True)

    provider = MagicMock()
    provider.acquire.return_value = "local"
    sandbox = MagicMock()
    provider.get.return_value = sandbox

    with (
        patch.object(uploads, "get_uploads_dir", return_value=thread_uploads_dir),
        patch.object(uploads, "ensure_uploads_dir", return_value=thread_uploads_dir),
        patch.object(uploads, "get_sandbox_provider", return_value=provider),
    ):
        file = UploadFile(filename="notes.txt", file=BytesIO(b"hello uploads"))
        result = asyncio.run(uploads.upload_files("thread-local", _mock_request(), files=[file]))

    assert result.success is True
    assert len(result.files) == 1
    assert result.files[0]["filename"] == "notes.txt"
    assert result.files[0]["original_filename"] == "notes.txt"
    assert result.files[0]["stored_filename"] == "notes.txt"
    assert result.files[0]["attachment_id"].startswith("att-")
    assert result.files[0]["virtual_path"] == "/mnt/user-data/uploads/notes.txt"
    assert (thread_uploads_dir / "notes.txt").read_bytes() == b"hello uploads"

    sandbox.update_file.assert_not_called()


def test_upload_files_syncs_non_local_sandbox_and_marks_markdown_file(tmp_path):
    thread_uploads_dir = tmp_path / "uploads"
    thread_uploads_dir.mkdir(parents=True)

    provider = MagicMock()
    provider.acquire.return_value = "aio-1"
    sandbox = MagicMock()
    provider.get.return_value = sandbox

    async def fake_convert(file_path: Path) -> Path:
        md_path = file_path.with_suffix(".md")
        md_path.write_text("converted", encoding="utf-8")
        return md_path

    with (
        patch.object(uploads, "get_uploads_dir", return_value=thread_uploads_dir),
        patch.object(uploads, "ensure_uploads_dir", return_value=thread_uploads_dir),
        patch.object(uploads, "get_sandbox_provider", return_value=provider),
        patch.object(uploads, "convert_file_to_markdown", AsyncMock(side_effect=fake_convert)),
    ):
        file = UploadFile(filename="report.pdf", file=BytesIO(b"pdf-bytes"))
        result = asyncio.run(uploads.upload_files("thread-aio", _mock_request(), files=[file]))

    assert result.success is True
    assert len(result.files) == 1
    file_info = result.files[0]
    assert file_info["filename"] == "report.pdf"
    assert file_info["markdown_file"] == "report.md"

    assert (thread_uploads_dir / "report.pdf").read_bytes() == b"pdf-bytes"
    assert (thread_uploads_dir / "report.md").read_text(encoding="utf-8") == "converted"

    sandbox.update_file.assert_any_call("/mnt/user-data/uploads/report.pdf", b"pdf-bytes")
    sandbox.update_file.assert_any_call("/mnt/user-data/uploads/report.md", b"converted")


def test_upload_files_keeps_same_name_files_side_by_side(tmp_path):
    thread_uploads_dir = tmp_path / "uploads"
    thread_uploads_dir.mkdir(parents=True)

    provider = MagicMock()
    provider.acquire.return_value = "local"
    sandbox = MagicMock()
    provider.get.return_value = sandbox

    with (
        patch.object(uploads, "get_uploads_dir", return_value=thread_uploads_dir),
        patch.object(uploads, "ensure_uploads_dir", return_value=thread_uploads_dir),
        patch.object(uploads, "get_sandbox_provider", return_value=provider),
    ):
        first = UploadFile(filename="stable.txt", file=BytesIO(b"hello"))
        second = UploadFile(filename="stable.txt", file=BytesIO(b"world"))
        result_1 = asyncio.run(uploads.upload_files("thread-stable", _mock_request(), files=[first]))
        result_2 = asyncio.run(uploads.upload_files("thread-stable", _mock_request(), files=[second]))

    assert result_1.success is True and result_2.success is True
    assert result_1.files[0]["filename"] == "stable.txt"
    assert result_2.files[0]["filename"] == "stable_1.txt"
    assert result_2.files[0]["original_filename"] == "stable.txt"
    assert result_2.files[0]["stored_filename"] == "stable_1.txt"
    assert result_1.files[0]["attachment_id"] != result_2.files[0]["attachment_id"]
    assert (thread_uploads_dir / "stable.txt").read_bytes() == b"hello"
    assert (thread_uploads_dir / "stable_1.txt").read_bytes() == b"world"


def test_upload_files_keeps_same_name_files_in_single_batch(tmp_path):
    thread_uploads_dir = tmp_path / "uploads"
    thread_uploads_dir.mkdir(parents=True)

    provider = MagicMock()
    provider.acquire.return_value = "local"
    sandbox = MagicMock()
    provider.get.return_value = sandbox

    with (
        patch.object(uploads, "get_uploads_dir", return_value=thread_uploads_dir),
        patch.object(uploads, "ensure_uploads_dir", return_value=thread_uploads_dir),
        patch.object(uploads, "get_sandbox_provider", return_value=provider),
    ):
        first = UploadFile(filename="dup.txt", file=BytesIO(b"first"))
        second = UploadFile(filename="dup.txt", file=BytesIO(b"second"))
        result = asyncio.run(uploads.upload_files("thread-batch", _mock_request(), files=[first, second]))

    assert result.success is True
    assert [f["filename"] for f in result.files] == ["dup.txt", "dup_1.txt"]
    assert result.files[0]["attachment_id"] != result.files[1]["attachment_id"]
    assert (thread_uploads_dir / "dup.txt").read_bytes() == b"first"
    assert (thread_uploads_dir / "dup_1.txt").read_bytes() == b"second"


def test_upload_files_rejects_dotdot_and_dot_filenames(tmp_path):
    thread_uploads_dir = tmp_path / "uploads"
    thread_uploads_dir.mkdir(parents=True)

    provider = MagicMock()
    provider.acquire.return_value = "local"
    sandbox = MagicMock()
    provider.get.return_value = sandbox

    with (
        patch.object(uploads, "get_uploads_dir", return_value=thread_uploads_dir),
        patch.object(uploads, "ensure_uploads_dir", return_value=thread_uploads_dir),
        patch.object(uploads, "get_sandbox_provider", return_value=provider),
    ):
        # These filenames must be rejected outright
        for bad_name in ["..", "."]:
            file = UploadFile(filename=bad_name, file=BytesIO(b"data"))
            result = asyncio.run(uploads.upload_files("thread-local", _mock_request(), files=[file]))
            assert result.success is True
            assert result.files == [], f"Expected no files for unsafe filename {bad_name!r}"

        # Path-traversal prefixes are stripped to the basename and accepted safely
        file = UploadFile(filename="../etc/passwd", file=BytesIO(b"data"))
        result = asyncio.run(uploads.upload_files("thread-local", _mock_request(), files=[file]))
        assert result.success is True
        assert len(result.files) == 1
        assert result.files[0]["filename"] == "passwd"

    # Only the safely normalised file should exist
    assert [f.name for f in thread_uploads_dir.iterdir()] == ["passwd"]


def test_delete_uploaded_file_removes_generated_markdown_companion(tmp_path):
    thread_uploads_dir = tmp_path / "uploads"
    thread_uploads_dir.mkdir(parents=True)
    (thread_uploads_dir / "report.pdf").write_bytes(b"pdf-bytes")
    (thread_uploads_dir / "report.md").write_text("converted", encoding="utf-8")

    with patch.object(uploads, "get_uploads_dir", return_value=thread_uploads_dir):
        result = asyncio.run(uploads.delete_uploaded_file("thread-aio", "report.pdf", _mock_request()))

    assert result == {
        "success": True,
        "message": "Deleted report.pdf",
        "deleted_files": ["report.pdf", "report.md"],
        "cascaded_deleted_files": ["report.md"],
    }
    assert not (thread_uploads_dir / "report.pdf").exists()
    assert not (thread_uploads_dir / "report.md").exists()


def test_delete_uploaded_file_by_attachment_id(tmp_path):
    thread_uploads_dir = tmp_path / "uploads"
    thread_uploads_dir.mkdir(parents=True)
    (thread_uploads_dir / "keep.txt").write_text("keep", encoding="utf-8")
    (thread_uploads_dir / "target.txt").write_text("delete", encoding="utf-8")

    attachment_id = uploads.upload_attachment_id("thread-aio", "target.txt")

    with patch.object(uploads, "get_uploads_dir", return_value=thread_uploads_dir):
        result = asyncio.run(
            uploads.delete_uploaded_file_by_attachment_id(
                "thread-aio",
                attachment_id,
                _mock_request(),
            )
        )

    assert result == {
        "success": True,
        "message": "Deleted target.txt",
        "deleted_files": ["target.txt"],
        "cascaded_deleted_files": [],
    }
    assert (thread_uploads_dir / "keep.txt").exists()
    assert not (thread_uploads_dir / "target.txt").exists()


def test_delete_uploaded_file_by_attachment_id_not_found(tmp_path):
    thread_uploads_dir = tmp_path / "uploads"
    thread_uploads_dir.mkdir(parents=True)
    (thread_uploads_dir / "present.txt").write_text("present", encoding="utf-8")

    with patch.object(uploads, "get_uploads_dir", return_value=thread_uploads_dir):
        try:
            asyncio.run(
                uploads.delete_uploaded_file_by_attachment_id(
                    "thread-aio",
                    "att-not-found",
                    _mock_request(),
                )
            )
            assert False, "Expected HTTPException for missing attachment id"
        except uploads.HTTPException as exc:
            assert exc.status_code == 404
            assert "Attachment not found" in str(exc.detail)


def test_upload_files_skips_virtual_sync_for_thread_bound_local_sandbox(tmp_path):
    thread_uploads_dir = tmp_path / "uploads"
    thread_uploads_dir.mkdir(parents=True)

    provider = MagicMock()
    provider.acquire.return_value = "local-abc123"
    sandbox = MagicMock()
    provider.get.return_value = sandbox

    with (
        patch.object(uploads, "get_uploads_dir", return_value=thread_uploads_dir),
        patch.object(uploads, "ensure_uploads_dir", return_value=thread_uploads_dir),
        patch.object(uploads, "get_sandbox_provider", return_value=provider),
    ):
        file = UploadFile(filename="2507.log", file=BytesIO(b"log content"))
        result = asyncio.run(uploads.upload_files("thread-local", _mock_request(), files=[file]))

    assert result.success is True
    assert (thread_uploads_dir / "2507.log").read_bytes() == b"log content"
    sandbox.update_file.assert_not_called()


@pytest.fixture(autouse=True)
def isolated_route_contract(monkeypatch):
    # These tests exercise filesystem/upload contracts. Current database
    # authority is exercised separately by test_file_access_http.py.
    async def authorized(*args, **kwargs):
        return None
    monkeypatch.setattr('app.gateway.file_authorization.require_thread_access', authorized)
    monkeypatch.setattr(uploads, 'require_thread_access', authorized)
