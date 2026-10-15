"""Read original Better Auth account facts; never infer authority from membership alone."""
from sqlalchemy import text

from app.gateway.auth_db import auth_connection, column_exists
from deerflow.runtime import ExecutionTrustError


def verify_current_account(actor: str) -> None:
    if not isinstance(actor, str) or not actor:
        raise ExecutionTrustError("Current account unavailable")
    try:
        with auth_connection() as connection:
            has_status = column_exists(connection, "user", "status")
            has_password_gate = column_exists(connection, "user", "mustChangePassword")
            fields = ["id"]
            if has_status:
                fields.append('status AS account_status')
            if has_password_gate:
                fields.append('"mustChangePassword" AS password_gate')
            row = connection.execute(text('SELECT ' + ', '.join(fields) + ' FROM "user" WHERE id = :actor LIMIT 1'), {"actor": actor}).mappings().first()
            if row is None:
                raise ExecutionTrustError("Current account unavailable")
            # Original deployments may lack the optional status column; account
            # existence is still mandatory and storage failures never grant access.
            if has_status and str(row["account_status"]).strip().lower() != "active":
                raise ExecutionTrustError("Current account unavailable")
            if has_password_gate and str(row["password_gate"]).strip().lower() not in {"false", "0", "none", ""}:
                raise ExecutionTrustError("Current account requires authentication renewal")
    except ExecutionTrustError:
        raise
    except Exception:
        raise ExecutionTrustError("Current account authority unavailable") from None
