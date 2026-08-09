from datetime import UTC, datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.gateway.auth_crypto import hash_password
from app.gateway.auth_db import (
    _row_to_dict,
    auth_connection,
    column_exists,
    table_exists,
)


class AuthUserRepository:
    def has_user_status_column(self) -> bool:
        with auth_connection() as conn:
            return column_exists(conn, "user", "status")

    def list_users(self, keyword: str = None, limit: int = 50, offset: int = 0) -> list[dict[str, Any]]:
        with auth_connection() as conn:
            query = "SELECT * FROM \"user\""
            params: dict = {}
            if keyword:
                query += " WHERE email LIKE :kw OR name LIKE :kw"
                params["kw"] = f"%{keyword}%"

            query += " ORDER BY \"createdAt\" DESC LIMIT :lim OFFSET :off"
            params["lim"] = limit
            params["off"] = offset

            result = conn.execute(text(query), params)
            return [_row_to_dict(row) for row in result.fetchall()]

    def get_user_by_id(self, user_id: str) -> dict[str, Any] | None:
        with auth_connection() as conn:
            result = conn.execute(
                text("SELECT * FROM \"user\" WHERE id = :uid LIMIT 1"),
                {"uid": user_id},
            )
            row = result.fetchone()
            return _row_to_dict(row) if row else None

    def get_users_by_role(self, role: str) -> list[dict[str, Any]]:
        with auth_connection() as conn:
            result = conn.execute(
                text("SELECT id FROM \"user\" WHERE role = :role"),
                {"role": role},
            )
            return [_row_to_dict(row) for row in result.fetchall()]

    def update_user_status(self, user_id: str, new_status: str, updated_at: str) -> dict[str, Any] | None:
        if not self.has_user_status_column():
            raise NotImplementedError("User status column not available")

        with auth_connection() as conn:
            result = conn.execute(
                text(
                    "UPDATE \"user\" SET status = :status, \"updatedAt\" = :updated_at WHERE id = :uid"
                ),
                {"status": new_status, "updated_at": updated_at, "uid": user_id},
            )
            if result.rowcount == 0:
                return None

            select_result = conn.execute(
                text(
                    "SELECT id, email, name, role, status, \"createdAt\", \"updatedAt\" "
                    "FROM \"user\" WHERE id = :uid LIMIT 1"
                ),
                {"uid": user_id},
            )
            row = select_result.fetchone()
            return _row_to_dict(row) if row else None

    def update_user(self, user_id: str, name: str, email: str, role: str, updated_at: str) -> dict[str, Any] | None:
        """Update a user's profile (name, email, role)."""
        with auth_connection() as conn:
            # Check if email is already taken by another user
            existing = conn.execute(
                text("SELECT id FROM \"user\" WHERE email = :email AND id != :uid LIMIT 1"),
                {"email": email, "uid": user_id},
            ).fetchone()
            if existing:
                raise ValueError("Email already in use by another user")

            result = conn.execute(
                text(
                    "UPDATE \"user\" SET name = :name, email = :email, role = :role, \"updatedAt\" = :updated_at WHERE id = :uid"
                ),
                {"name": name, "email": email, "role": role, "updated_at": updated_at, "uid": user_id},
            )
            if result.rowcount == 0:
                return None
            conn.commit()

            return self.get_user_by_id(user_id)

    def get_account_by_user_id(self, user_id: str) -> dict[str, Any] | None:
        with auth_connection() as conn:
            result = conn.execute(
                text("SELECT * FROM account WHERE \"userId\" = :uid LIMIT 1"),
                {"uid": user_id},
            )
            row = result.fetchone()
            return _row_to_dict(row) if row else None

    def update_user_password(self, user_id: str, new_password: str, must_change_password: bool = False) -> bool:
        hashed = hash_password(new_password)
        now = datetime.now(UTC).isoformat().replace("+00:00", "Z")

        with auth_connection() as conn:
            result = conn.execute(
                text(
                    "UPDATE account SET password = :pw, \"updatedAt\" = :updated_at WHERE \"userId\" = :uid"
                ),
                {"pw": hashed, "updated_at": now, "uid": user_id},
            )
            if result.rowcount == 0:
                return False

            must_change_val = 1 if must_change_password else 0
            try:
                conn.execute(
                    text(
                        "UPDATE \"user\" SET \"mustChangePassword\" = :mcp, \"updatedAt\" = :updated_at WHERE id = :uid"
                    ),
                    {"mcp": must_change_val, "updated_at": now, "uid": user_id},
                )
            except SQLAlchemyError:
                pass
            conn.commit()
            return True

    def create_user(self, email: str, name: str, password: str, role: str = "user", status: str = "active", must_change_password: bool = True) -> dict[str, Any]:
        import secrets

        user_id = f"usr_{secrets.token_hex(8)}"
        account_id = f"acc_{secrets.token_hex(8)}"
        now = datetime.now(UTC).isoformat().replace("+00:00", "Z")
        hashed_pwd = hash_password(password)

        with auth_connection() as conn:
            existing = conn.execute(
                text("SELECT id FROM \"user\" WHERE email = :email"),
                {"email": email},
            ).fetchone()
            if existing:
                raise ValueError("Email already in use")

            conn.execute(
                text(
                    "INSERT INTO \"user\" ("
                    "id, name, email, \"emailVerified\", image, \"createdAt\", \"updatedAt\", "
                    "role, status, \"mustChangePassword\", \"isBootstrapAdmin\""
                    ") VALUES (:id, :name, :email, :ev, :img, :ca, :ua, :role, :status, :mcp, :iba)"
                ),
                {
                    "id": user_id,
                    "name": name,
                    "email": email,
                    "ev": 1,
                    "img": None,
                    "ca": now,
                    "ua": now,
                    "role": role,
                    "status": status,
                    "mcp": 1 if must_change_password else 0,
                    "iba": 0,
                },
            )

            conn.execute(
                text(
                    "INSERT INTO account ("
                    "id, \"accountId\", \"providerId\", \"userId\", "
                    "password, \"createdAt\", \"updatedAt\""
                    ") VALUES (:id, :aid, :pid, :uid, :pw, :ca, :ua)"
                ),
                {
                    "id": account_id,
                    "aid": email,
                    "pid": "credential",
                    "uid": user_id,
                    "pw": hashed_pwd,
                    "ca": now,
                    "ua": now,
                },
            )

            conn.commit()

            return {
                "id": user_id,
                "email": email,
                "name": name,
                "role": role,
                "status": status,
                "createdAt": now,
                "updatedAt": now,
                "mustChangePassword": must_change_password,
                "isBootstrapAdmin": False,
            }

    def delete_user_cascade(self, user_id: str) -> dict[str, Any]:
        deleted_counts: dict[str, int] = {
            "sessions": 0,
            "accounts": 0,
        }

        with auth_connection() as conn:
            user_row = conn.execute(
                text("SELECT id FROM \"user\" WHERE id = :uid LIMIT 1"),
                {"uid": user_id},
            ).fetchone()
            if not user_row:
                return {"deleted": False, "counts": deleted_counts}

            if table_exists(conn, "session"):
                result = conn.execute(
                    text("DELETE FROM session WHERE \"userId\" = :uid"),
                    {"uid": user_id},
                )
                deleted_counts["sessions"] = result.rowcount

            if table_exists(conn, "account"):
                result = conn.execute(
                    text("DELETE FROM account WHERE \"userId\" = :uid"),
                    {"uid": user_id},
                )
                deleted_counts["accounts"] = result.rowcount

            result = conn.execute(
                text("DELETE FROM \"user\" WHERE id = :uid"),
                {"uid": user_id},
            )
            deleted = result.rowcount > 0

            conn.commit()
            return {"deleted": deleted, "counts": deleted_counts}
