"""Fix missing credential accounts and legacy bcrypt hashes in auth DB.

Supports both SQLite and PostgreSQL.

Usage:
  cd backend
  PYTHONPATH=. uv run python scripts/fix_auth_data.py
"""

import secrets
import string
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from sqlalchemy import create_engine, text

from app.gateway.auth_crypto import hash_password
from app.gateway.auth_db import _resolve_auth_db_url


def generate_random_password(length=8):
    alphabet = string.ascii_letters + string.digits + "!@#$%"
    return "".join(secrets.choice(alphabet) for _ in range(length))


def run_fix():
    db_url = _resolve_auth_db_url()
    print("Connecting to database...")

    engine = create_engine(db_url)
    fixed_count = 0
    print("Checking for missing credential accounts...\n")

    with engine.connect() as conn:
        users = conn.execute(text("SELECT id, email, name FROM \"user\"")).fetchall()

        for row in users:
            user_id = row[0]
            email = row[1]

            acc = conn.execute(
                text("SELECT id FROM account WHERE \"userId\" = :uid AND providerId = 'credential'"),
                {"uid": user_id},
            ).fetchone()

            if not acc:
                print(f"[!] User {email} has NO credential account. Fixing...")
                new_pwd = generate_random_password()
                hashed = hash_password(new_pwd)
                now = datetime.now(UTC)

                account_id = f"acc_{secrets.token_hex(8)}"

                conn.execute(
                    text(
                        "INSERT INTO account (id, accountId, providerId, userId, password, createdAt, updatedAt) "
                        "VALUES (:id, :acc_id, :provider, :uid, :pwd, :now, :now)"
                    ),
                    {
                        "id": account_id,
                        "acc_id": email,
                        "provider": "credential",
                        "uid": user_id,
                        "pwd": hashed,
                        "now": now,
                    },
                )
                print(f"    -> Created credential for {email}. Auto-generated Password: {new_pwd}")
                print("    -> Please let the user know their password, or they will be unable to login.")
                fixed_count += 1

            else:
                acc_full = conn.execute(
                    text("SELECT id, password FROM account WHERE \"userId\" = :uid AND providerId = 'credential'"),
                    {"uid": user_id},
                ).fetchone()
                if acc_full and acc_full[1] and acc_full[1].startswith("$"):
                    print(f"[*] User {email} uses legacy bcrypt. Re-hashing to scrypt...")
                    new_pwd = generate_random_password()
                    hashed = hash_password(new_pwd)
                    now = datetime.now(UTC)
                    conn.execute(
                        text("UPDATE account SET password = :pwd, updatedAt = :now WHERE id = :id"),
                        {"pwd": hashed, "now": now, "id": acc_full[0]},
                    )
                    try:
                        conn.execute(
                            text("UPDATE \"user\" SET mustChangePassword = 1 WHERE id = :uid"),
                            {"uid": user_id},
                        )
                    except Exception:
                        pass
                    print(f"    -> Legacy bcrypt replaced for {email}. New temp password: {new_pwd}")
                    fixed_count += 1

        conn.commit()

    print(f"\nFix complete. Total accounts fixed: {fixed_count}")


if __name__ == "__main__":
    run_fix()
