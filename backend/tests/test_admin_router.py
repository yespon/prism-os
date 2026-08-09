import sqlite3
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from app.gateway import auth_db
from app.gateway.routers import admin


def _patch_auth_db(monkeypatch, db_path):
    """Patch auth_db to use a specific SQLite database path for testing."""
    monkeypatch.setenv("AUTH_DB_URL", f"sqlite+pysqlite:///{db_path}")
    auth_db.reset_auth_engine()


def _create_auth_db(path):
    with sqlite3.connect(path) as conn:
        conn.execute(
            """
            CREATE TABLE user (
                id TEXT PRIMARY KEY,
                email TEXT,
                name TEXT,
                role TEXT,
                createdAt TEXT,
                updatedAt TEXT
            )
            """
        )
        conn.execute(
            """
            INSERT INTO user(id, email, name, role, createdAt, updatedAt)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            ("u-admin", "admin@example.com", "admin", "admin", "2026-03-30T00:00:00Z", "2026-03-30T00:00:00Z"),
        )


def _create_auth_db_with_status(path):
    with sqlite3.connect(path) as conn:
        conn.execute(
            """
            CREATE TABLE user (
                id TEXT PRIMARY KEY,
                email TEXT,
                name TEXT,
                role TEXT,
                status TEXT,
                createdAt TEXT,
                updatedAt TEXT
            )
            """
        )
        conn.executemany(
            """
            INSERT INTO user(id, email, name, role, status, createdAt, updatedAt)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [
                ("u-admin", "admin@example.com", "admin", "admin", "active", "2026-03-30T00:00:00Z", "2026-03-30T00:00:00Z"),
                ("u-user", "user@example.com", "user", "user", "active", "2026-03-30T00:00:00Z", "2026-03-30T00:00:00Z"),
            ],
        )


def _create_auth_db_many_users(path, total_users: int = 55):
    with sqlite3.connect(path) as conn:
        conn.execute(
            """
            CREATE TABLE user (
                id TEXT PRIMARY KEY,
                email TEXT,
                name TEXT,
                role TEXT,
                status TEXT,
                mustChangePassword INTEGER,
                isBootstrapAdmin INTEGER,
                createdAt TEXT,
                updatedAt TEXT
            )
            """
        )
        rows = []
        recent_created_at = (datetime.now(UTC) - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
        older_created_at = (datetime.now(UTC) - timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%SZ")
        for idx in range(total_users):
            user_id = f"u-{idx:03d}"
            status = "suspended" if idx % 10 == 0 else "active"
            is_bootstrap_admin = 1 if idx == 0 else 0
            must_change_password = 1 if idx % 7 == 0 else 0
            created_at = recent_created_at if idx < 3 else older_created_at
            rows.append(
                (
                    user_id,
                    f"{user_id}@example.com",
                    user_id,
                    "user",
                    status,
                    must_change_password,
                    is_bootstrap_admin,
                    created_at,
                    created_at,
                )
            )
        conn.executemany(
            """
            INSERT INTO user(id, email, name, role, status, mustChangePassword, isBootstrapAdmin, createdAt, updatedAt)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )


def _create_auth_db_with_credentials(path):
    with sqlite3.connect(path) as conn:
        conn.execute(
            """
            CREATE TABLE user (
                id TEXT PRIMARY KEY,
                email TEXT,
                name TEXT,
                role TEXT,
                status TEXT,
                mustChangePassword INTEGER,
                isBootstrapAdmin INTEGER,
                createdAt TEXT,
                updatedAt TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE account (
                id TEXT PRIMARY KEY,
                accountId TEXT,
                providerId TEXT,
                userId TEXT,
                password TEXT,
                createdAt TEXT,
                updatedAt TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE session (
                id TEXT PRIMARY KEY,
                userId TEXT,
                token TEXT
            )
            """
        )
        conn.executemany(
            """
            INSERT INTO user(id, email, name, role, status, mustChangePassword, isBootstrapAdmin, createdAt, updatedAt)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                ("u-admin", "admin@example.com", "admin", "admin", "active", 0, 0, "2026-03-30T00:00:00Z", "2026-03-30T00:00:00Z"),
                ("u-user", "user@example.com", "user", "user", "active", 0, 0, "2026-03-30T00:00:00Z", "2026-03-30T00:00:00Z"),
            ],
        )
        conn.executemany(
            """
            INSERT INTO account(id, accountId, providerId, userId, password, createdAt, updatedAt)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [
                ("acc-admin", "admin@example.com", "credential", "u-admin", "hash-admin", "2026-03-30T00:00:00Z", "2026-03-30T00:00:00Z"),
                ("acc-user", "user@example.com", "credential", "u-user", "hash-user", "2026-03-30T00:00:00Z", "2026-03-30T00:00:00Z"),
            ],
        )
        conn.execute(
            "INSERT INTO session(id, userId, token) VALUES (?, ?, ?)",
            ("s-user", "u-user", "token-u-user"),
        )


def _create_app() -> FastAPI:
    app = FastAPI()

    @app.middleware("http")
    async def inject_user_context(request: Request, call_next):
        request.state.user_id = request.headers.get("x-user-id", "u-user")
        request.state.user_role = request.headers.get("x-user-role", "user")
        request.state.tenant_role = request.headers.get("x-tenant-role", request.state.user_role)
        tenant_id = request.headers.get("x-tenant-id")
        if tenant_id is not None:
            request.state.tenant_id = tenant_id
        request.state.must_change_password = request.headers.get("x-must-change-password", "false").lower() == "true"
        return await call_next(request)

    app.include_router(admin.router)
    return app


def test_admin_users_requires_admin_role(tmp_path, monkeypatch):
    db_path = tmp_path / "auth.db"
    _create_auth_db(db_path)
    _patch_auth_db(monkeypatch, db_path)

    app = _create_app()
    with TestClient(app) as client:
        response = client.get("/api/admin/users", headers={"x-user-role": "user"})

    assert response.status_code == 403


def test_admin_users_returns_users_for_admin(tmp_path, monkeypatch):
    db_path = tmp_path / "auth.db"
    _create_auth_db(db_path)
    _patch_auth_db(monkeypatch, db_path)

    app = _create_app()
    with TestClient(app) as client:
        response = client.get("/api/admin/users", headers={"x-user-role": "admin"})

    print(response.json())
    assert response.status_code == 200
    payload = response.json()
    assert len(payload["users"]) == 1
    assert payload["users"][0]["id"] == "u-admin"
    assert payload["users"][0]["role"] == "admin"


def test_admin_me_returns_current_admin_context():
    app = _create_app()
    with TestClient(app) as client:
        response = client.get(
            "/api/admin/me",
            headers={"x-user-id": "u-admin", "x-user-role": "admin"},
        )

    print(response.json())
    assert response.status_code == 200
    assert response.json() == {"user_id": "u-admin", "role": "admin"}


def test_admin_users_includes_status_when_column_exists(tmp_path, monkeypatch):
    db_path = tmp_path / "auth.db"
    _create_auth_db_with_status(db_path)
    _patch_auth_db(monkeypatch, db_path)

    app = _create_app()
    with TestClient(app) as client:
        response = client.get("/api/admin/users", headers={"x-user-role": "admin"})

    print(response.json())
    assert response.status_code == 200
    users = response.json()["users"]
    assert any(user["id"] == "u-user" and user["status"] == "active" for user in users)


def test_admin_update_user_status(tmp_path, monkeypatch):
    db_path = tmp_path / "auth.db"
    _create_auth_db_with_status(db_path)
    _patch_auth_db(monkeypatch, db_path)

    calls = []
    monkeypatch.setattr(admin, "record_audit_event", lambda *args, **kwargs: calls.append((args, kwargs)))

    app = _create_app()
    with TestClient(app) as client:
        response = client.patch(
            "/api/admin/users/u-user/status",
            headers={"x-user-role": "admin", "x-user-id": "u-admin"},
            json={"status": "suspended"},
        )

    print(response.json())
    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] == "u-user"
    assert payload["status"] == "suspended"
    assert calls, "expected audit event to be recorded"
    assert calls[0][0][0] == "admin.user.status.updated"
    assert calls[0][1]["actor_id"] == "u-admin"


def test_admin_update_user_status_returns_501_without_status_column(tmp_path, monkeypatch):
    db_path = tmp_path / "auth.db"
    _create_auth_db(db_path)
    _patch_auth_db(monkeypatch, db_path)

    app = _create_app()
    with TestClient(app) as client:
        response = client.patch(
            "/api/admin/users/u-admin/status",
            headers={"x-user-role": "admin"},
            json={"status": "suspended"},
        )

    assert response.status_code == 501


def test_admin_users_usage_requires_admin_role(tmp_path, monkeypatch):
    db_path = tmp_path / "auth.db"
    _create_auth_db_with_status(db_path)
    _patch_auth_db(monkeypatch, db_path)

    app = _create_app()
    with TestClient(app) as client:
        response = client.get("/api/admin/users/usage", headers={"x-user-role": "user"})

    assert response.status_code == 403


def test_admin_users_usage_returns_thread_and_upload_stats(tmp_path, monkeypatch):
    db_path = tmp_path / "auth.db"
    _create_auth_db_with_status(db_path)
    _patch_auth_db(monkeypatch, db_path)

    base_dir = tmp_path / ".opsintech"
    uploads_dir = base_dir / "users" / "u-user" / "threads" / "t-1" / "user-data" / "uploads"
    uploads_dir.mkdir(parents=True)
    (uploads_dir / "a.txt").write_text("hello")
    (uploads_dir / "b.bin").write_bytes(b"123456")
    (base_dir / "users" / "u-user" / "threads" / "t-2" / "user-data" / "workspace").mkdir(parents=True)

    monkeypatch.setenv("OPSINTECH_HOME", str(base_dir))

    app = _create_app()
    with TestClient(app) as client:
        response = client.get("/api/admin/users/usage", headers={"x-user-role": "admin"})

    print(response.json())
    assert response.status_code == 200
    payload = response.json()
    rows = {row["user_id"]: row for row in payload["users"]}

    assert rows["u-user"]["thread_count"] == 2
    assert rows["u-user"]["upload_file_count"] == 2
    assert rows["u-user"]["upload_bytes_total"] == 11


def test_admin_users_usage_marks_soft_limit_overages(tmp_path, monkeypatch):
    db_path = tmp_path / "auth.db"
    _create_auth_db_with_status(db_path)
    _patch_auth_db(monkeypatch, db_path)

    base_dir = tmp_path / ".opsintech"
    uploads_dir = base_dir / "users" / "u-user" / "threads" / "t-1" / "user-data" / "uploads"
    uploads_dir.mkdir(parents=True)
    (uploads_dir / "a.txt").write_text("hello")
    (base_dir / "users" / "u-user" / "threads" / "t-2" / "user-data" / "workspace").mkdir(parents=True)

    monkeypatch.setenv("OPSINTECH_HOME", str(base_dir))
    monkeypatch.setenv("ADMIN_THREAD_SOFT_LIMIT", "1")
    monkeypatch.setenv("ADMIN_UPLOAD_BYTES_SOFT_LIMIT", "4")

    app = _create_app()
    with TestClient(app) as client:
        response = client.get("/api/admin/users/usage", headers={"x-user-role": "admin"})

    print(response.json())
    assert response.status_code == 200
    payload = response.json()
    rows = {row["user_id"]: row for row in payload["users"]}

    assert rows["u-user"]["thread_soft_limit"] == 1
    assert rows["u-user"]["upload_bytes_soft_limit"] == 4
    assert rows["u-user"]["thread_over_soft_limit"] is True
    assert rows["u-user"]["upload_bytes_over_soft_limit"] is True


def test_admin_users_usage_ignores_invalid_soft_limit_env(tmp_path, monkeypatch):
    db_path = tmp_path / "auth.db"
    _create_auth_db_with_status(db_path)
    _patch_auth_db(monkeypatch, db_path)

    base_dir = tmp_path / ".opsintech"
    (base_dir / "users" / "u-user" / "threads" / "t-1" / "user-data" / "workspace").mkdir(parents=True)

    monkeypatch.setenv("OPSINTECH_HOME", str(base_dir))
    monkeypatch.setenv("ADMIN_THREAD_SOFT_LIMIT", "0")
    monkeypatch.setenv("ADMIN_UPLOAD_BYTES_SOFT_LIMIT", "not-an-int")

    app = _create_app()
    with TestClient(app) as client:
        response = client.get("/api/admin/users/usage", headers={"x-user-role": "admin"})

    print(response.json())
    assert response.status_code == 200
    payload = response.json()
    rows = {row["user_id"]: row for row in payload["users"]}
    assert rows["u-user"]["thread_soft_limit"] is None
    assert rows["u-user"]["upload_bytes_soft_limit"] is None
    assert rows["u-user"]["thread_over_soft_limit"] is False
    assert rows["u-user"]["upload_bytes_over_soft_limit"] is False


def test_admin_users_usage_aggregates_all_users_not_first_page_only(tmp_path, monkeypatch):
    db_path = tmp_path / "auth.db"
    _create_auth_db_many_users(db_path, total_users=55)
    _patch_auth_db(monkeypatch, db_path)

    def _fake_collect_user_usage(user_id: str, tenant_id: str | None = None):
        return admin.AdminUserUsage(
            user_id=user_id,
            thread_count=1,
            upload_file_count=1,
            upload_bytes_total=1,
            thread_soft_limit=None,
            upload_bytes_soft_limit=None,
            thread_over_soft_limit=False,
            upload_bytes_over_soft_limit=False,
        )

    monkeypatch.setattr(admin, "_collect_user_usage", _fake_collect_user_usage)

    app = _create_app()
    with TestClient(app) as client:
        response = client.get("/api/admin/users/usage", headers={"x-user-role": "admin"})

    assert response.status_code == 200
    payload = response.json()
    assert len(payload["users"]) == 55
    user_ids = {item["user_id"] for item in payload["users"]}
    assert "u-000" in user_ids
    assert "u-054" in user_ids


def test_admin_overview_returns_governance_metrics(tmp_path, monkeypatch):
    db_path = tmp_path / "auth.db"
    _create_auth_db_many_users(db_path, total_users=55)
    _patch_auth_db(monkeypatch, db_path)

    class _Result:
        def __init__(self, rows):
            self._rows = rows

        def scalars(self):
            return self

        def all(self):
            return self._rows

    class _Session:
        async def execute(self, stmt):
            stmt_str = str(stmt)
            if "FROM tenants" in stmt_str:
                return _Result(
                    [
                        SimpleNamespace(id="tenant-a", status="active"),
                        SimpleNamespace(id="tenant-b", status="inactive"),
                    ]
                )
            return _Result([SimpleNamespace(name="m1"), SimpleNamespace(name="m2"), SimpleNamespace(name="m3")])

    class _SessionCtx:
        async def __aenter__(self):
            return _Session()

        async def __aexit__(self, exc_type, exc, tb):
            return False

    async def _fake_list_platform_global_models():
        return [SimpleNamespace(name="gpt-4.1"), SimpleNamespace(name="gpt-4o")]

    def _fake_collect_user_usage(user_id: str, tenant_id: str | None = None):
        return admin.AdminUserUsage(
            user_id=user_id,
            thread_count=2,
            upload_file_count=3,
            upload_bytes_total=10,
            thread_soft_limit=None,
            upload_bytes_soft_limit=None,
            thread_over_soft_limit=False,
            upload_bytes_over_soft_limit=False,
        )

    monkeypatch.setattr(admin, "get_session_factory", lambda: (lambda: _SessionCtx()))
    monkeypatch.setattr(admin, "list_platform_global_models", _fake_list_platform_global_models)
    monkeypatch.setattr(admin, "_collect_user_usage", _fake_collect_user_usage)

    app = _create_app()
    with TestClient(app) as client:
        response = client.get("/api/admin/overview", headers={"x-user-role": "admin"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["total_users"] == 55
    assert payload["suspended_users"] == 6
    assert payload["active_users"] == 49
    assert payload["total_threads"] == 110
    assert payload["total_files"] == 165
    assert payload["total_bytes"] == 550
    assert payload["total_tenants"] == 2
    assert payload["active_tenants"] == 1
    assert payload["platform_model_template_count"] == 2
    assert payload["assigned_model_count"] == 3
    assert payload["bootstrap_admin_users"] == 1
    assert payload["must_change_password_users"] == 8
    assert payload["recent_new_users_7d"] == 3


def test_admin_reset_target_user_password(tmp_path, monkeypatch):
    from app.gateway.auth_crypto import verify_password

    db_path = tmp_path / "auth.db"
    _create_auth_db_with_credentials(db_path)
    _patch_auth_db(monkeypatch, db_path)

    calls = []
    monkeypatch.setattr(admin, "record_audit_event", lambda *args, **kwargs: calls.append((args, kwargs)))

    app = _create_app()
    with TestClient(app) as client:
        response = client.put(
            "/api/admin/users/u-user/password",
            headers={"x-user-role": "admin", "x-user-id": "u-admin"},
            json={"new_password": "UserNewPassword123!", "must_change_password": True},
        )

    print(response.json())
    assert response.status_code == 200
    assert calls and calls[0][0][0] == "admin.user.password.reset"

    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT password FROM account WHERE userId = ?", ("u-user",)).fetchone()

    assert row is not None
    assert verify_password(row["password"], "UserNewPassword123!") is True


def test_admin_delete_user_cascades_auth_and_files(tmp_path, monkeypatch):
    db_path = tmp_path / "auth.db"
    _create_auth_db_with_credentials(db_path)
    _patch_auth_db(monkeypatch, db_path)

    base_dir = tmp_path / ".opsintech"
    uploads_dir = base_dir / "users" / "u-user" / "threads" / "t-1" / "user-data" / "uploads"
    uploads_dir.mkdir(parents=True)
    (uploads_dir / "dead-file.txt").write_text("delete-me")
    monkeypatch.setenv("OPSINTECH_HOME", str(base_dir))

    calls = []
    monkeypatch.setattr(admin, "record_audit_event", lambda *args, **kwargs: calls.append((args, kwargs)))

    app = _create_app()
    with TestClient(app) as client:
        response = client.delete(
            "/api/admin/users/u-user",
            headers={"x-user-role": "admin", "x-user-id": "u-admin"},
        )

    print(response.json())
    assert response.status_code == 200
    payload = response.json()
    assert payload["user_id"] == "u-user"
    assert payload["deleted_accounts"] == 1
    assert payload["deleted_sessions"] == 1
    assert payload["deleted_files"] >= 1
    assert payload["deleted_user_data_dir"] is True

    with sqlite3.connect(db_path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM user WHERE id = ?", ("u-user",)).fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM account WHERE userId = ?", ("u-user",)).fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM session WHERE userId = ?", ("u-user",)).fetchone()[0] == 0

    assert (base_dir / "users" / "u-user").exists() is False
    assert calls and calls[0][0][0] == "admin.user.deleted"


def test_admin_audit_logs_requires_admin_role():
    app = _create_app()
    with TestClient(app) as client:
        response = client.get("/api/admin/audit/logs", headers={"x-user-role": "user"})
    assert response.status_code == 403


def test_admin_audit_logs_returns_events(monkeypatch):
    monkeypatch.setattr(
        admin,
        "read_audit_events",
        lambda **kwargs: [
            {
                "ts": "2026-03-30T00:00:00Z",
                "event_type": "upload.quota.blocked",
                "severity": "warning",
                "actor_id": "u-user",
                "target_user_id": "u-user",
                "metadata": {"hard_limit": 10},
            }
        ],
    )

    app = _create_app()
    with TestClient(app) as client:
        response = client.get("/api/admin/audit/logs?limit=10", headers={"x-user-role": "admin"})

    print(response.json())
    assert response.status_code == 200
    payload = response.json()
    assert len(payload["events"]) == 1
    assert payload["events"][0]["event_type"] == "upload.quota.blocked"


def test_admin_audit_logs_supports_tenant_and_scope_filters(monkeypatch):
    captured = {}

    def _fake_read_audit_events(**kwargs):
        captured.update(kwargs)
        return [
            {
                "ts": "2026-03-30T00:00:00Z",
                "event_type": "tenant.member.added",
                "severity": "info",
                "actor_id": "u-admin",
                "target_user_id": "u-1",
                "tenant_id": "tenant-a",
                "scope": "tenant",
                "metadata": {"role": "tenant_member"},
            }
        ]

    monkeypatch.setattr(
        admin,
        "read_audit_events",
        _fake_read_audit_events,
    )

    app = _create_app()
    with TestClient(app) as client:
        response = client.get(
            "/api/admin/audit/logs?tenant_id=tenant-a&scope=tenant&limit=10",
            headers={"x-user-role": "admin"},
        )

    assert response.status_code == 200
    payload = response.json()
    assert len(payload["events"]) == 1
    event = payload["events"][0]
    assert event["event_type"] == "tenant.member.added"
    assert event["tenant_id"] == "tenant-a"
    assert event["scope"] == "tenant"
    assert captured["tenant_id"] == "tenant-a"
    assert captured["scope"] == "tenant"


def test_admin_audit_logs_filter_limit_applies_after_filter(monkeypatch):
    monkeypatch.setattr(
        admin,
        "read_audit_events",
        lambda **kwargs: [
            {
                "ts": "2026-03-30T00:00:00Z",
                "event_type": "tenant.event.1",
                "severity": "info",
                "tenant_id": "tenant-a",
                "scope": "tenant",
                "metadata": {},
            },
            {
                "ts": "2026-03-30T00:00:01Z",
                "event_type": "tenant.event.2",
                "severity": "info",
                "tenant_id": "tenant-a",
                "scope": "tenant",
                "metadata": {},
            },
        ],
    )

    app = _create_app()
    with TestClient(app) as client:
        response = client.get(
            "/api/admin/audit/logs?tenant_id=tenant-a&scope=tenant&limit=1",
            headers={"x-user-role": "admin"},
        )

    assert response.status_code == 200
    payload = response.json()
    assert len(payload["events"]) == 1
    assert payload["events"][0]["event_type"] == "tenant.event.1"


def test_platform_daily_tenant_member_api_removed_routes() -> None:
    app = _create_app()

    with TestClient(app) as client:
        list_resp = client.get("/api/admin/tenants/tenant-a/members", headers={"x-user-role": "admin"})
        add_resp = client.post(
            "/api/admin/tenants/tenant-a/members",
            headers={"x-user-role": "admin"},
            json={"user_id": "u-1", "role": "tenant_admin"},
        )
        upd_resp = client.put(
            "/api/admin/tenants/tenant-a/members/u-1",
            headers={"x-user-role": "admin"},
            json={"role": "tenant_member"},
        )
        del_resp = client.delete("/api/admin/tenants/tenant-a/members/u-1", headers={"x-user-role": "admin"})

    assert list_resp.status_code == 404
    assert add_resp.status_code == 404
    assert upd_resp.status_code == 404
    assert del_resp.status_code == 404


def test_platform_initialize_tenant_admin_conflict_when_active_members_exist(monkeypatch):
    class _ExecuteResult:
        def __init__(self, rows):
            self._rows = rows

        def scalars(self):
            return self

        def all(self):
            return self._rows

    class _Session:
        async def get(self, model, tenant_id):
            return SimpleNamespace(id=tenant_id)

        async def execute(self, stmt):
            return _ExecuteResult([SimpleNamespace(user_id="u-existing", status="active")])

    class _SessionCtx:
        async def __aenter__(self):
            return _Session()

        async def __aexit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(admin, "get_session_factory", lambda: (lambda: _SessionCtx()))

    app = _create_app()
    with TestClient(app) as client:
        response = client.post(
            "/api/admin/tenants/tenant-a/members/initialize-admin",
            headers={"x-user-role": "admin", "x-user-id": "u-admin"},
            json={"user_id": "u-target"},
        )

    assert response.status_code == 409


def test_platform_initialize_tenant_admin_success(monkeypatch):
    class _ExecuteResult:
        def __init__(self, rows):
            self._rows = rows

        def scalars(self):
            return self

        def all(self):
            return self._rows

    class _Session:
        async def get(self, model, tenant_id):
            return SimpleNamespace(id=tenant_id)

        async def execute(self, stmt):
            return _ExecuteResult([])

    class _SessionCtx:
        async def __aenter__(self):
            return _Session()

        async def __aexit__(self, exc_type, exc, tb):
            return False

    class _Repo:
        def __init__(self, *_args, **_kwargs):
            pass

        def get_user_by_id(self, user_id: str):
            return {"id": user_id, "email": "x@example.com"}

    calls = []

    async def _fake_add_tenant_member(tenant_id: str, user_id: str, role: str):
        calls.append((tenant_id, user_id, role))
        return SimpleNamespace(role="admin")

    monkeypatch.setattr(admin, "get_session_factory", lambda: (lambda: _SessionCtx()))
    monkeypatch.setattr(admin, "AuthUserRepository", _Repo)
    monkeypatch.setattr(admin, "add_tenant_member", _fake_add_tenant_member)

    app = _create_app()
    with TestClient(app) as client:
        response = client.post(
            "/api/admin/tenants/tenant-a/members/initialize-admin",
            headers={"x-user-role": "admin", "x-user-id": "u-admin"},
            json={"user_id": "u-target"},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "success"
    assert payload["tenant_id"] == "tenant-a"
    assert payload["user_id"] == "u-target"
    assert calls == [("tenant-a", "u-target", "tenant_admin")]


def test_platform_create_tenant_rejects_tenant_member_owner_role():
    app = _create_app()

    with TestClient(app) as client:
        response = client.post(
            "/api/admin/tenants",
            headers={"x-user-role": "admin", "x-user-id": "u-admin"},
            json={
                "name": "tenant-a",
                "owner_user_id": "u-owner",
                "owner_role": "tenant_member",
            },
        )

    assert response.status_code == 422


def test_platform_create_tenant_requires_owner_user_id():
    app = _create_app()

    with TestClient(app) as client:
        response = client.post(
            "/api/admin/tenants",
            headers={"x-user-role": "admin", "x-user-id": "u-admin"},
            json={
                "name": "tenant-a",
                "owner_user_id": "   ",
            },
        )

    assert response.status_code == 422
    assert response.json()["detail"] == "owner_user_id is required"


def test_platform_reset_tenant_admin_can_reassign_and_demote(monkeypatch):
    class _ExecuteResult:
        def __init__(self, rows):
            self._rows = rows

        def scalars(self):
            return self

        def all(self):
            return self._rows

    active_members = [
        SimpleNamespace(user_id="u-old-admin", role="admin", status="active"),
        SimpleNamespace(user_id="u-backup-admin", role="owner", status="active"),
        SimpleNamespace(user_id="u-member", role="member", status="active"),
    ]

    class _Session:
        async def get(self, model, tenant_id):
            return SimpleNamespace(id=tenant_id)

        async def execute(self, stmt):
            return _ExecuteResult(active_members)

    class _SessionCtx:
        async def __aenter__(self):
            return _Session()

        async def __aexit__(self, exc_type, exc, tb):
            return False

    class _Repo:
        def __init__(self, *_args, **_kwargs):
            pass

        def get_user_by_id(self, user_id: str):
            return {"id": user_id, "email": "x@example.com", "role": "user"}

    add_calls = []
    demote_calls = []

    async def _fake_add_tenant_member(tenant_id: str, user_id: str, role: str):
        add_calls.append((tenant_id, user_id, role))
        return SimpleNamespace(role="admin")

    async def _fake_update_tenant_member_role(tenant_id: str, user_id: str, role: str):
        demote_calls.append((tenant_id, user_id, role))
        return SimpleNamespace(role="member")

    monkeypatch.setattr(admin, "get_session_factory", lambda: (lambda: _SessionCtx()))
    monkeypatch.setattr(admin, "AuthUserRepository", _Repo)
    monkeypatch.setattr(admin, "add_tenant_member", _fake_add_tenant_member)
    monkeypatch.setattr(admin, "update_tenant_member_role", _fake_update_tenant_member_role)

    app = _create_app()
    with TestClient(app) as client:
        response = client.post(
            "/api/admin/tenants/tenant-a/members/reset-admin",
            headers={"x-user-role": "admin", "x-user-id": "u-admin"},
            json={"user_id": "u-new-admin", "demote_other_active_admins": True},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "success"
    assert payload["tenant_id"] == "tenant-a"
    assert payload["user_id"] == "u-new-admin"
    assert payload["prior_active_admin_user_ids"] == ["u-old-admin", "u-backup-admin"]
    assert payload["demoted_user_ids"] == ["u-old-admin", "u-backup-admin"]
    assert add_calls == [("tenant-a", "u-new-admin", "tenant_admin")]
    assert demote_calls == [
        ("tenant-a", "u-old-admin", "tenant_member"),
        ("tenant-a", "u-backup-admin", "tenant_member"),
    ]


def test_platform_tenant_admin_recovery_flow_create_then_lost_then_reset(monkeypatch):
    tenant_id = "tenant-flow"
    membership_store: dict[str, dict[str, str]] = {
        "u-owner": {"role": "admin", "status": "active"}
    }

    class _Repo:
        def __init__(self, *_args, **_kwargs):
            pass

        def get_user_by_id(self, user_id: str):
            if user_id in {"u-owner", "u-recovery"}:
                return {"id": user_id, "email": f"{user_id}@example.com", "role": "user"}
            return None

    async def _fake_create_tenant(name: str, owner_user_id: str, slug: str | None = None):
        membership_store[owner_user_id] = {"role": "admin", "status": "active"}
        return SimpleNamespace(id=tenant_id, name=name)

    async def _fake_add_tenant_member(in_tenant_id: str, user_id: str, role: str):
        assert in_tenant_id == tenant_id
        membership_store[user_id] = {"role": "admin", "status": "active"}
        return SimpleNamespace(role="admin")

    async def _fake_update_tenant_member_role(in_tenant_id: str, user_id: str, role: str):
        assert in_tenant_id == tenant_id
        membership_store[user_id] = {"role": "member", "status": membership_store[user_id]["status"]}
        return SimpleNamespace(role="member")

    class _ExecuteResult:
        def __init__(self, rows):
            self._rows = rows

        def scalars(self):
            return self

        def all(self):
            return self._rows

    class _Session:
        async def get(self, model, in_tenant_id):
            if in_tenant_id != tenant_id:
                return None
            return SimpleNamespace(id=in_tenant_id)

        async def execute(self, stmt):
            active_rows = [
                SimpleNamespace(user_id=user_id, role=data["role"], status=data["status"])
                for user_id, data in membership_store.items()
                if data["status"] == "active"
            ]
            return _ExecuteResult(active_rows)

    class _SessionCtx:
        async def __aenter__(self):
            return _Session()

        async def __aexit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(admin, "AuthUserRepository", _Repo)
    monkeypatch.setattr(admin, "create_tenant", _fake_create_tenant)
    monkeypatch.setattr(admin, "add_tenant_member", _fake_add_tenant_member)
    monkeypatch.setattr(admin, "update_tenant_member_role", _fake_update_tenant_member_role)
    monkeypatch.setattr(admin, "get_session_factory", lambda: (lambda: _SessionCtx()))

    app = _create_app()
    with TestClient(app) as client:
        created = client.post(
            "/api/admin/tenants",
            headers={"x-user-role": "admin", "x-user-id": "u-admin"},
            json={"name": "tenant-flow", "owner_user_id": "u-owner", "owner_role": "tenant_admin"},
        )
        assert created.status_code == 200

        membership_store["u-owner"] = {"role": "member", "status": "inactive"}

        recovered = client.post(
            f"/api/admin/tenants/{tenant_id}/members/reset-admin",
            headers={"x-user-role": "admin", "x-user-id": "u-admin"},
            json={"user_id": "u-recovery", "demote_other_active_admins": True},
        )

    assert recovered.status_code == 200
    recovered_payload = recovered.json()
    assert recovered_payload["status"] == "success"
    assert recovered_payload["user_id"] == "u-recovery"
    assert membership_store["u-recovery"]["role"] == "admin"
    assert membership_store["u-recovery"]["status"] == "active"


def test_tenant_audit_logs_requires_tenant_admin(monkeypatch):
    monkeypatch.setattr(admin, "read_audit_events", lambda **kwargs: [])
    app = _create_app()
    with TestClient(app) as client:
        response = client.get(
            "/api/admin/tenant-audit/logs",
            headers={"x-user-role": "user", "x-tenant-role": "tenant_member", "x-tenant-id": "tenant-a"},
        )
    assert response.status_code == 403


def test_tenant_audit_logs_isolated_by_current_tenant(monkeypatch):
    captured = {}

    def _fake_read_audit_events(**kwargs):
        captured.update(kwargs)
        return [
            {
                "ts": "2026-03-30T00:00:00Z",
                "event_type": "tenant.member.added",
                "severity": "info",
                "tenant_id": "tenant-a",
                "scope": "tenant",
                "metadata": {},
            }
        ]

    monkeypatch.setattr(admin, "read_audit_events", _fake_read_audit_events)

    app = _create_app()
    with TestClient(app) as client:
        response = client.get(
            "/api/admin/tenant-audit/logs?limit=10",
            headers={"x-user-role": "user", "x-tenant-role": "tenant_admin", "x-tenant-id": "tenant-a"},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["tenant_id"] == "tenant-a"
    assert len(payload["events"]) == 1
    assert payload["events"][0]["tenant_id"] == "tenant-a"
    assert captured["tenant_id"] == "tenant-a"


def test_tenant_audit_logs_tenant_member_forbidden(monkeypatch):
    monkeypatch.setattr(admin, "read_audit_events", lambda **kwargs: [])
    app = _create_app()
    with TestClient(app) as client:
        response = client.get(
            "/api/admin/tenant-audit/logs",
            headers={"x-user-role": "user", "x-tenant-role": "tenant_member", "x-tenant-id": "tenant-a"},
        )
    assert response.status_code == 403


def test_admin_global_models_list_returns_rows(monkeypatch):
    class _Row:
        name = "gpt-global"
        model = "gpt-5"
        display_name = "GPT 5"
        description = "platform"
        settings = {"enabled": True}

    async def _fake_list_platform_global_models():
        return [_Row()]

    monkeypatch.setattr(admin, "list_platform_global_models", _fake_list_platform_global_models)

    app = _create_app()
    with TestClient(app) as client:
        response = client.get("/api/admin/models/global", headers={"x-user-role": "admin"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["models"][0]["name"] == "gpt-global"
    assert payload["models"][0]["enabled"] is True


def test_admin_assign_global_model_to_tenant(monkeypatch):
    class _Row:
        name = "gpt-global"

    async def _fake_assign_platform_model_to_tenant(tenant_id: str, model_name: str, *, enabled: bool):
        assert tenant_id == "tenant-a"
        assert model_name == "gpt-global"
        assert enabled is True
        return _Row()

    calls = []
    monkeypatch.setattr(admin, "assign_platform_model_to_tenant", _fake_assign_platform_model_to_tenant)
    monkeypatch.setattr(admin, "record_audit_event", lambda *args, **kwargs: calls.append((args, kwargs)))

    app = _create_app()
    with TestClient(app) as client:
        response = client.post(
            "/api/admin/tenants/tenant-a/models/assign",
            headers={"x-user-role": "admin", "x-user-id": "u-admin"},
            json={"model_name": "gpt-global", "enabled": True},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "success"
    assert payload["tenant_id"] == "tenant-a"
    assert payload["model_name"] == "gpt-global"
    assert calls and calls[0][0][0] == "platform.tenant.model.assigned"


def test_admin_list_assigned_models_for_tenant(monkeypatch):
    class _Row:
        name = "gpt-global"
        model = "gpt-5"
        display_name = "GPT 5"
        description = "assigned"
        settings = {"enabled": True, "assigned_from_global": True}

    async def _fake_list_platform_assigned_models_for_tenant(tenant_id: str):
        assert tenant_id == "tenant-a"
        return [_Row()]

    monkeypatch.setattr(
        admin,
        "list_platform_assigned_models_for_tenant",
        _fake_list_platform_assigned_models_for_tenant,
    )

    app = _create_app()
    with TestClient(app) as client:
        response = client.get(
            "/api/admin/tenants/tenant-a/models/assigned",
            headers={"x-user-role": "admin"},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["tenant_id"] == "tenant-a"
    assert len(payload["models"]) == 1
    assert payload["models"][0]["name"] == "gpt-global"


def test_admin_skill_and_tool_routes_are_removed() -> None:
    app = _create_app()

    with TestClient(app) as client:
        tool_response = client.get("/api/admin/tools/global", headers={"x-user-role": "admin"})
        skill_response = client.get("/api/admin/skills/global", headers={"x-user-role": "admin"})
        assign_tool_response = client.post(
            "/api/admin/tenants/tenant-a/tools/assign",
            headers={"x-user-role": "admin", "x-user-id": "u-admin"},
            json={"tool_name": "jira", "enabled": True},
        )
        assign_skill_response = client.post(
            "/api/admin/tenants/tenant-a/skills/assign",
            headers={"x-user-role": "admin", "x-user-id": "u-admin"},
            json={"skill_name": "incident-triage", "enabled": True},
        )

    assert tool_response.status_code == 404
    assert skill_response.status_code == 404
    assert assign_tool_response.status_code == 404
    assert assign_skill_response.status_code == 404


def test_admin_create_global_model(monkeypatch):
    class _Row:
        name = "gpt-global"
        model = "gpt-5"
        display_name = "GPT 5"
        description = "platform"
        settings = {"enabled": True}

    calls = {}

    async def _fake_create_user_model(user_id: str, payload: dict, *, tenant_id: str | None = None):
        calls["user_id"] = user_id
        calls["tenant_id"] = tenant_id
        calls["payload"] = payload
        return _Row()

    monkeypatch.setattr(admin, "create_user_model", _fake_create_user_model)

    app = _create_app()
    with TestClient(app) as client:
        response = client.post(
            "/api/admin/models/global",
            headers={"x-user-role": "admin", "x-user-id": "u-admin"},
            json={"name": "gpt-global", "model": "gpt-5", "display_name": "GPT 5"},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["name"] == "gpt-global"
    assert calls["user_id"] == admin.PLATFORM_MODEL_OWNER_ID
    assert calls["tenant_id"] is None


def test_admin_delete_global_model(monkeypatch):
    calls = {}

    async def _fake_delete_global_model_with_assignments(model_name: str):
        calls["model_name"] = model_name
        return ["tenant-a", "tenant-b"]

    monkeypatch.setattr(admin, "delete_global_model_with_assignments", _fake_delete_global_model_with_assignments)

    app = _create_app()
    with TestClient(app) as client:
        response = client.delete(
            "/api/admin/models/global/gpt-global",
            headers={"x-user-role": "admin", "x-user-id": "u-admin"},
        )

    assert response.status_code == 200
    assert calls == {"model_name": "gpt-global"}
    assert response.json() == {
        "status": "success",
        "model_name": "gpt-global",
        "affected_tenants": ["tenant-a", "tenant-b"],
    }

def test_admin_create_user_writes_valid_scrypt_hash(tmp_path, monkeypatch):
    from app.gateway.auth_crypto import verify_password
    db_file = tmp_path / "auth.db"
    # Create tables
    with sqlite3.connect(db_file) as conn:
        conn.execute("""
            CREATE TABLE user (
                id TEXT PRIMARY KEY,
                name TEXT,
                email TEXT,
                emailVerified INTEGER,
                image TEXT,
                createdAt TEXT,
                updatedAt TEXT,
                role TEXT,
                status TEXT,
                mustChangePassword INTEGER,
                isBootstrapAdmin INTEGER
            )
        """)
        conn.execute("""
            CREATE TABLE account (
                id TEXT PRIMARY KEY,
                accountId TEXT,
                providerId TEXT,
                userId TEXT,
                password TEXT,
                createdAt TEXT,
                updatedAt TEXT
            )
        """)
        conn.commit()

    _patch_auth_db(monkeypatch, db_file)

    app = _create_app()
    with TestClient(app) as client:
        response = client.post(
            "/api/admin/users",
            headers={"x-user-id": "u-admin", "x-user-role": "admin"},
            json={
                "email": "scrypt-test@local.dev",
                "name": "Test User",
                "password": "Password123!",
                "role": "user",
                "status": "active",
                "must_change_password": True
            }
        )
    
    assert response.status_code == 200, response.text
    user_data = response.json()
    assert user_data["email"] == "scrypt-test@local.dev"
    
    with sqlite3.connect(db_file) as c:
        c.row_factory = sqlite3.Row
        acc = c.execute("SELECT password FROM account WHERE userId = ?", (user_data["id"],)).fetchone()
        
    assert acc is not None
    hashed_pwd = dict(acc)["password"]
    
    assert ":" in hashed_pwd
    assert verify_password(hashed_pwd, "Password123!") is True


def test_bootstrap_status_strict_mode_rejects_global_admin_without_tenant_admin(tmp_path, monkeypatch):
    db_path = tmp_path / "auth.db"
    _create_auth_db_with_credentials(db_path)
    _patch_auth_db(monkeypatch, db_path)
    monkeypatch.setenv("DEERFLOW_ADMIN_REQUIRE_TENANT_ROLE", "true")

    app = _create_app()
    with TestClient(app) as client:
        response = client.get(
            "/api/admin/bootstrap-status",
            headers={"x-user-id": "u-admin", "x-user-role": "admin", "x-tenant-role": "member"},
        )

    assert response.status_code == 403


def test_bootstrap_status_strict_mode_allows_tenant_admin(tmp_path, monkeypatch):
    db_path = tmp_path / "auth.db"
    _create_auth_db_with_credentials(db_path)
    _patch_auth_db(monkeypatch, db_path)
    monkeypatch.setenv("DEERFLOW_ADMIN_REQUIRE_TENANT_ROLE", "true")

    app = _create_app()
    with TestClient(app) as client:
        response = client.get(
            "/api/admin/bootstrap-status",
            headers={"x-user-id": "u-admin", "x-user-role": "user", "x-tenant-role": "admin"},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["is_bootstrap_admin"] is False


def test_change_initial_password_strict_mode_allows_bootstrap_global_admin(tmp_path, monkeypatch):
    db_path = tmp_path / "auth.db"
    _create_auth_db_with_credentials(db_path)
    _patch_auth_db(monkeypatch, db_path)
    monkeypatch.setenv("DEERFLOW_ADMIN_REQUIRE_TENANT_ROLE", "true")

    calls = []
    monkeypatch.setattr(admin, "record_audit_event", lambda *args, **kwargs: calls.append((args, kwargs)))

    app = _create_app()
    with TestClient(app) as client:
        response = client.post(
            "/api/admin/change-initial-password",
            headers={
                "x-user-id": "u-admin",
                "x-user-role": "admin",
                "x-tenant-role": "member",
                "x-must-change-password": "true",
            },
            json={"new_password": "AdminNewPassword123!"},
        )

    assert response.status_code == 200
    assert calls and calls[0][1]["metadata"]["is_initial"] is True
