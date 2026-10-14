from unittest.mock import patch

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.gateway.routers import threads
from deerflow.config.paths import Paths


def test_delete_thread_data_removes_thread_directory(tmp_path):
    paths = Paths(tmp_path)
    thread_dir = paths.thread_dir("local", "thread-cleanup")
    workspace = paths.sandbox_work_dir("local", "thread-cleanup")
    uploads = paths.sandbox_uploads_dir("local", "thread-cleanup")
    outputs = paths.sandbox_outputs_dir("local", "thread-cleanup")

    for directory in [workspace, uploads, outputs]:
        directory.mkdir(parents=True, exist_ok=True)
    (workspace / "notes.txt").write_text("hello", encoding="utf-8")
    (uploads / "report.pdf").write_bytes(b"pdf")
    (outputs / "result.json").write_text("{}", encoding="utf-8")

    assert thread_dir.exists()

    response = threads._delete_thread_data("local", "thread-cleanup", paths=paths)

    assert response.success is True
    assert not thread_dir.exists()


def test_delete_thread_data_is_idempotent_for_missing_directory(tmp_path):
    paths = Paths(tmp_path)

    response = threads._delete_thread_data("local", "missing-thread", paths=paths)

    assert response.success is True
    assert not paths.thread_dir("local", "missing-thread").exists()


def test_delete_thread_data_rejects_invalid_thread_id(tmp_path):
    paths = Paths(tmp_path)

    with pytest.raises(HTTPException) as exc_info:
        threads._delete_thread_data("local", "../escape", paths=paths)

    assert exc_info.value.status_code == 422
    assert "Invalid thread_id" in exc_info.value.detail


def test_delete_thread_route_cleans_thread_directory(tmp_path):
    paths = Paths(tmp_path)
    thread_dir = paths.thread_dir("local", "thread-route")
    paths.sandbox_work_dir("local", "thread-route").mkdir(parents=True, exist_ok=True)
    (paths.sandbox_work_dir("local", "thread-route") / "notes.txt").write_text("hello", encoding="utf-8")

    app = FastAPI()

    @app.middleware("http")
    async def _inject_user(request, call_next):
        request.state.user_id = "local"
        request.state.tenant_id = "tenant-a"
        return await call_next(request)

    app.include_router(threads.router)

    with patch("app.gateway.routers.threads.get_paths", return_value=paths):
        with TestClient(app) as client:
            response = client.delete("/api/threads/thread-route")

    assert response.status_code == 200
    assert response.json() == {"success": True, "message": "Deleted local thread data for thread-route"}
    assert not thread_dir.exists()


def test_delete_thread_route_rejects_invalid_thread_id(tmp_path):
    paths = Paths(tmp_path)

    app = FastAPI()

    @app.middleware("http")
    async def _inject_user(request, call_next):
        request.state.user_id = "local"
        request.state.tenant_id = "tenant-a"
        return await call_next(request)

    app.include_router(threads.router)

    with patch("app.gateway.routers.threads.get_paths", return_value=paths):
        with TestClient(app) as client:
            response = client.delete("/api/threads/../escape")

    assert response.status_code == 404


def test_delete_thread_route_returns_422_for_route_safe_invalid_id(tmp_path):
    paths = Paths(tmp_path)

    app = FastAPI()

    @app.middleware("http")
    async def _inject_user(request, call_next):
        request.state.user_id = "local"
        request.state.tenant_id = "tenant-a"
        return await call_next(request)

    app.include_router(threads.router)

    with patch("app.gateway.routers.threads.get_paths", return_value=paths):
        with TestClient(app) as client:
            response = client.delete("/api/threads/thread.with.dot")

    assert response.status_code == 422
    assert "Invalid thread_id" in response.json()["detail"]


def test_delete_thread_data_returns_generic_500_error(tmp_path):
    paths = Paths(tmp_path)

    with (
        patch.object(paths, "delete_thread_dir", side_effect=OSError("/secret/path")),
        patch.object(threads.logger, "exception") as log_exception,
    ):
        with pytest.raises(HTTPException) as exc_info:
            threads._delete_thread_data("local", "thread-cleanup", paths=paths)

    assert exc_info.value.status_code == 500
    assert exc_info.value.detail == "Failed to delete local thread data."
    assert "/secret/path" not in exc_info.value.detail
    log_exception.assert_called_once_with("Failed to delete thread data for %s", "thread-cleanup")


def test_delete_thread_data_invokes_checkpointer_delete_thread(tmp_path):
    paths = Paths(tmp_path)
    thread_dir = paths.thread_dir("local", "thread-cleanup")
    paths.sandbox_work_dir("local", "thread-cleanup").mkdir(parents=True, exist_ok=True)
    assert thread_dir.exists()

    class _Checkpointer:
        def __init__(self):
            self.deleted_thread_id = None

        def delete_thread(self, thread_id):
            self.deleted_thread_id = thread_id

    cp = _Checkpointer()
    with patch("app.gateway.routers.threads.get_checkpointer", return_value=cp):
        response = threads._delete_thread_data("local", "thread-cleanup", paths=paths)

    assert response.success is True
    assert cp.deleted_thread_id == "thread-cleanup"
    assert not thread_dir.exists()


def test_delete_thread_data_keeps_local_cleanup_when_checkpointer_delete_fails(tmp_path):
    paths = Paths(tmp_path)
    thread_dir = paths.thread_dir("local", "thread-cleanup")
    paths.sandbox_work_dir("local", "thread-cleanup").mkdir(parents=True, exist_ok=True)
    assert thread_dir.exists()

    class _Checkpointer:
        def delete_thread(self, thread_id):
            raise RuntimeError("delete failed")

    with (
        patch("app.gateway.routers.threads.get_checkpointer", return_value=_Checkpointer()),
        patch.object(threads.logger, "warning") as warn,
    ):
        response = threads._delete_thread_data("local", "thread-cleanup", paths=paths)

    assert response.success is True
    assert not thread_dir.exists()
    assert warn.called


@pytest.fixture(autouse=True)
def isolated_route_contract(monkeypatch):
    # These tests exercise filesystem/upload contracts. Current database
    # authority is exercised separately by test_file_access_http.py.
    async def authorized(*args, **kwargs):
        return None
    monkeypatch.setattr('app.gateway.file_authorization.require_thread_access', authorized)
