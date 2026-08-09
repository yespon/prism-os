import sqlite3

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.gateway import auth_db
from app.gateway.auth_crypto import verify_password
from app.gateway.authorization import require_platform_admin
from app.gateway.routers.admin import router


def _create_app():
    app = FastAPI()
    app.include_router(router)
    return app

def test_admin_create_user_writes_valid_scrypt_hash(tmp_path, monkeypatch):
    db_file = tmp_path / "auth.db"
    monkeypatch.setenv("AUTH_DB_URL", f"sqlite+pysqlite:///{db_file}")
    auth_db.reset_auth_engine()
    
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

    app = _create_app()
    app.dependency_overrides[require_platform_admin] = lambda: None
    client = TestClient(app)

    response = client.post(
        "/api/admin/users",
        headers={"x-user-role": "admin"},
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
