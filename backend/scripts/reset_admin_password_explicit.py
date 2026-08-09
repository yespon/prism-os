"""Reset admin password via direct DB manipulation.

Supports both SQLite and PostgreSQL.

Usage:
  cd backend
  PYTHONPATH=. uv run python scripts/reset_admin_password_explicit.py
"""

import os
import secrets
import string
import sys
from datetime import datetime, timezone

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from sqlalchemy import create_engine, text

from app.gateway.auth_db import _resolve_auth_db_url


def generate_password(length=12):
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
    return "".join(secrets.choice(alphabet) for _ in range(length))


def run():
    from app.gateway.auth_crypto import hash_password

    db_url = _resolve_auth_db_url()
    now = datetime.now(timezone.utc)

    engine = create_engine(db_url)
    new_password = generate_password()
    hashed = hash_password(new_password)

    with engine.connect() as c:
        user = c.execute(
            text("SELECT id, email FROM \"user\" WHERE role = 'admin' AND isBootstrapAdmin = 1 LIMIT 1")
        ).fetchone()

        if not user:
            print("No bootstrap admin user found.")
            return

        user_id = user[0]
        admin_email = user[1] or "admin"

        if not admin_email or not admin_email.strip():
            admin_email = f"admin-{user_id[:8]}@prismos.local"
            c.execute(
                text("UPDATE \"user\" SET email = :email WHERE id = :id"),
                {"email": admin_email, "id": user_id},
            )
            print(f"Set admin email to {admin_email}")

        has_account = c.execute(
            text("SELECT id FROM account WHERE \"userId\" = :uid"),
            {"uid": user_id},
        ).fetchone()

        if not has_account:
            import uuid
            account_id = f"acc_{uuid.uuid4().hex[:16]}"
            c.execute(
                text(
                    "INSERT INTO account(id, accountId, providerId, userId, password, createdAt, updatedAt) "
                    "VALUES (:id, :acc_id, :provider, :uid, :pwd, :now, :now)"
                ),
                {
                    "id": account_id,
                    "acc_id": admin_email,
                    "provider": "credential",
                    "uid": user_id,
                    "pwd": hashed,
                    "now": now,
                },
            )
            print(f"Created account entry for {admin_email}")
        else:
            c.execute(
                text("UPDATE account SET accountId = :email, password = :pwd WHERE \"userId\" = :uid"),
                {"email": admin_email, "pwd": hashed, "uid": user_id},
            )
            print(f"Updated account entry for {admin_email}")

        c.commit()

    print()
    print("=" * 50)
    print("ADMIN PASSWORD RESET SUCCESSFUL")
    print(f"Email:    {admin_email}")
    print(f"Password: {new_password}")
    print("=" * 50)


if __name__ == "__main__":
    run()
