"""Authentication endpoints: login, logout, session, signup, and bootstrap setup."""

import secrets
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import text

from app.gateway.auth_crypto import hash_password, verify_password
from app.gateway.auth_db import _row_to_dict, auth_connection, column_exists
from app.gateway.bootstrap_admin import bootstrap_admin

router = APIRouter(prefix="/api/auth", tags=["auth"])

SESSION_COOKIE = "better-auth.session_token"
SESSION_MAX_AGE_DAYS = 30


def _to_iso(dt: datetime) -> str:
    return dt.isoformat().replace("+00:00", "Z")


def _user_row_to_dict(row) -> dict:
    d = _row_to_dict(row)
    d["mustChangePassword"] = bool(d.get("mustChangePassword", False))
    d["isBootstrapAdmin"] = bool(d.get("isBootstrapAdmin", False))
    d["emailVerified"] = bool(d.get("emailVerified", False))
    return d


def _resolve_session(token: str) -> dict | None:
    """Look up session + user by token. Returns combined dict or None."""
    with auth_connection() as conn:
        if column_exists(conn, "user", "mustChangePassword"):
            result = conn.execute(
                text(
                    "SELECT s.id AS session_id, s.token, s.\"expiresAt\", "
                    "s.\"userId\", s.\"createdAt\" AS session_created, "
                    "u.id AS user_id, u.name, u.email, u.\"emailVerified\", u.image, "
                    "u.role, u.\"createdAt\", u.\"updatedAt\", "
                    "u.\"mustChangePassword\", u.\"isBootstrapAdmin\" "
                    "FROM session s "
                    "JOIN \"user\" u ON u.id = s.\"userId\" "
                    "WHERE s.token = :token LIMIT 1"
                ),
                {"token": token},
            )
        else:
            result = conn.execute(
                text(
                    "SELECT s.id AS session_id, s.token, s.\"expiresAt\", "
                    "s.\"userId\", s.\"createdAt\" AS session_created, "
                    "u.id AS user_id, u.name, u.email, u.\"emailVerified\", u.image, "
                    "u.role, u.\"createdAt\", u.\"updatedAt\" "
                    "FROM session s "
                    "JOIN \"user\" u ON u.id = s.\"userId\" "
                    "WHERE s.token = :token LIMIT 1"
                ),
                {"token": token},
            )
        row = result.fetchone()
        if row is None:
            return None
        return _row_to_dict(row)


def _extract_token(request: Request) -> str | None:
    """Extract session token from Authorization header, query param, or cookie."""
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        return auth_header.split(" ", 1)[1]
    token = request.query_params.get("token")
    if token:
        return token
    return request.cookies.get(SESSION_COOKIE) or request.cookies.get(
        f"__Secure-{SESSION_COOKIE}"
    )


# ---------- request / response models ----------

class LoginRequest(BaseModel):
    email: str
    password: str
    remember_me: bool = True


class SignupRequest(BaseModel):
    name: str
    email: str
    password: str


class UserInfo(BaseModel):
    id: str
    name: str | None = None
    email: str | None = None
    emailVerified: bool = False
    image: str | None = None
    role: str = "user"
    createdAt: str | None = None
    updatedAt: str | None = None
    mustChangePassword: bool = False
    isBootstrapAdmin: bool = False


class SessionInfo(BaseModel):
    token: str
    expiresAt: str
    userId: str
    createdAt: str


class AuthResponse(BaseModel):
    session: SessionInfo
    user: UserInfo


class SessionResponse(BaseModel):
    session: SessionInfo | None = None
    user: UserInfo | None = None


class BootstrapStatusResponse(BaseModel):
    needs_setup: bool
    bootstrap_user_id: str | None = None


class SetupBootstrapAdminRequest(BaseModel):
    user_id: str = Field(..., description="User ID from bootstrap-status")
    email: str = Field(..., description="Email address to set")
    password: str = Field(..., description="Password to set")


class SetupBootstrapAdminResponse(BaseModel):
    success: bool
    email: str


# ---------- auth endpoints ----------

@router.post("/login", response_model=AuthResponse)
def login(body: LoginRequest, response: Response) -> AuthResponse:
    email = body.email.strip().lower()
    if not email or "@" not in email:
        raise HTTPException(status_code=400, detail="Valid email is required")

    with auth_connection() as conn:
        account_row = conn.execute(
            text(
                "SELECT a.id, a.password, a.\"userId\" "
                "FROM account a WHERE a.\"accountId\" = :email AND a.\"providerId\" = 'credential' LIMIT 1"
            ),
            {"email": email},
        ).fetchone()

        if account_row is None:
            raise HTTPException(status_code=401, detail="Invalid email or password")

        acc = _row_to_dict(account_row)
        if not verify_password(str(acc["password"]), body.password):
            raise HTTPException(status_code=401, detail="Invalid email or password")

        user_row = conn.execute(
            text("SELECT * FROM \"user\" WHERE id = :uid LIMIT 1"),
            {"uid": acc["userId"]},
        ).fetchone()

        if user_row is None:
            raise HTTPException(status_code=401, detail="User not found")

        user = _user_row_to_dict(user_row)

        status = str(user.get("status") or "active")
        if status == "suspended":
            raise HTTPException(status_code=403, detail="User account suspended")

        # Create session
        now = datetime.now(UTC)
        expires = now + timedelta(days=SESSION_MAX_AGE_DAYS)
        session_token = secrets.token_hex(32)
        session_id = f"sess_{secrets.token_hex(8)}"

        conn.execute(
            text(
                "INSERT INTO session (id, token, \"expiresAt\", \"userId\", \"createdAt\", \"updatedAt\") "
                "VALUES (:id, :token, :exp, :uid, :ca, :ua)"
            ),
            {
                "id": session_id,
                "token": session_token,
                "exp": _to_iso(expires),
                "uid": user["id"],
                "ca": _to_iso(now),
                "ua": _to_iso(now),
            },
        )
        conn.commit()

        response.set_cookie(
            key=SESSION_COOKIE,
            value=session_token,
            max_age=int(timedelta(days=SESSION_MAX_AGE_DAYS).total_seconds()),
            secure=False,
            samesite="lax",
            path="/",
        )

    return AuthResponse(
        session=SessionInfo(
            token=session_token,
            expiresAt=_to_iso(expires),
            userId=str(user["id"]),
            createdAt=_to_iso(now),
        ),
        user=UserInfo(
            id=str(user["id"]),
            name=user.get("name"),
            email=user.get("email"),
            emailVerified=bool(user.get("emailVerified", False)),
            image=user.get("image"),
            role=str(user.get("role") or "user"),
            createdAt=str(user.get("createdAt") or ""),
            updatedAt=str(user.get("updatedAt") or ""),
            mustChangePassword=bool(user.get("mustChangePassword", False)),
            isBootstrapAdmin=bool(user.get("isBootstrapAdmin", False)),
        ),
    )


@router.post("/logout")
def logout(request: Request, response: Response) -> dict:
    token = _extract_token(request)
    if token:
        with auth_connection() as conn:
            conn.execute(text("DELETE FROM session WHERE token = :token"), {"token": token})
            conn.commit()
    response.delete_cookie(SESSION_COOKIE, path="/")
    response.delete_cookie(f"__Secure-{SESSION_COOKIE}", path="/")
    return {"success": True}


@router.get("/session", response_model=SessionResponse)
def get_session(request: Request) -> SessionResponse:
    token = _extract_token(request)
    if not token:
        return SessionResponse()

    row = _resolve_session(token)
    if row is None:
        return SessionResponse()

    expires_at = row.get("expiresAt")
    if expires_at:
        try:
            exp = datetime.fromisoformat(str(expires_at).replace("Z", "+00:00"))
            if exp <= datetime.now(UTC):
                return SessionResponse()
        except ValueError:
            pass

    return SessionResponse(
        session=SessionInfo(
            token=token,
            expiresAt=str(row.get("expiresAt") or ""),
            userId=str(row.get("userId") or ""),
            createdAt=str(row.get("session_created") or ""),
        ),
        user=UserInfo(
            id=str(row.get("user_id") or ""),
            name=row.get("name"),
            email=row.get("email"),
            emailVerified=bool(row.get("emailVerified", False)),
            image=row.get("image"),
            role=str(row.get("role") or "user"),
            createdAt=str(row.get("createdAt") or ""),
            updatedAt=str(row.get("updatedAt") or ""),
            mustChangePassword=bool(row.get("mustChangePassword", False)),
            isBootstrapAdmin=bool(row.get("isBootstrapAdmin", False)),
        ),
    )


@router.post("/signup", response_model=AuthResponse)
def signup(body: SignupRequest, response: Response) -> AuthResponse:
    email = body.email.strip().lower()
    if not email or "@" not in email:
        raise HTTPException(status_code=400, detail="Valid email is required")
    if not body.password or len(body.password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")
    name = body.name.strip() or email.split("@")[0]

    now = datetime.now(UTC)
    expires = now + timedelta(days=SESSION_MAX_AGE_DAYS)
    hashed_pwd = hash_password(body.password)
    user_id = f"usr_{secrets.token_hex(8)}"
    account_id = f"acc_{secrets.token_hex(8)}"
    session_token = secrets.token_hex(32)
    session_id = f"sess_{secrets.token_hex(8)}"

    with auth_connection() as conn:
        existing = conn.execute(
            text("SELECT id FROM \"user\" WHERE email = :email"),
            {"email": email},
        ).fetchone()
        if existing is not None:
            raise HTTPException(status_code=409, detail="Email already in use")

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
                "ca": _to_iso(now),
                "ua": _to_iso(now),
                "role": "user",
                "status": "active",
                "mcp": 1,
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
                "ca": _to_iso(now),
                "ua": _to_iso(now),
            },
        )

        conn.execute(
            text(
                "INSERT INTO session (id, token, \"expiresAt\", \"userId\", \"createdAt\", \"updatedAt\") "
                "VALUES (:id, :token, :exp, :uid, :ca, :ua)"
            ),
            {
                "id": session_id,
                "token": session_token,
                "exp": _to_iso(expires),
                "uid": user_id,
                "ca": _to_iso(now),
                "ua": _to_iso(now),
            },
        )
        conn.commit()

    response.set_cookie(
        key=SESSION_COOKIE,
        value=session_token,
        max_age=int(timedelta(days=SESSION_MAX_AGE_DAYS).total_seconds()),
        secure=False,
        samesite="lax",
        path="/",
    )

    return AuthResponse(
        session=SessionInfo(
            token=session_token,
            expiresAt=_to_iso(expires),
            userId=user_id,
            createdAt=_to_iso(now),
        ),
        user=UserInfo(
            id=user_id,
            name=name,
            email=email,
            emailVerified=True,
            role="user",
            createdAt=_to_iso(now),
            updatedAt=_to_iso(now),
            mustChangePassword=True,
            isBootstrapAdmin=False,
        ),
    )


# ---------- bootstrap endpoints ----------

@router.get("/bootstrap-status", response_model=BootstrapStatusResponse)
def get_bootstrap_status() -> BootstrapStatusResponse:
    # On PostgreSQL, tables are created by Better Auth. bootstrap_admin
    # runs at gateway startup but may fail because the tables don't exist yet.
    # Retry here — by now the frontend has started and tables should exist.
    bootstrap_admin()
    with auth_connection() as conn:
        row = conn.execute(
            text(
                "SELECT u.id FROM \"user\" u "
                "WHERE u.\"isBootstrapAdmin\" = 1 AND u.status = 'active' "
                "AND NOT EXISTS (SELECT 1 FROM account a WHERE a.\"userId\" = u.id) "
                "LIMIT 1"
            ),
        ).fetchone()

        if row is None:
            return BootstrapStatusResponse(needs_setup=False)

        row_dict = dict(row._mapping)
        return BootstrapStatusResponse(
            needs_setup=True,
            bootstrap_user_id=str(row_dict["id"]),
        )


@router.post("/setup-bootstrap-admin", response_model=SetupBootstrapAdminResponse)
def setup_bootstrap_admin(body: SetupBootstrapAdminRequest) -> SetupBootstrapAdminResponse:
    email = body.email.strip().lower()
    if not email or "@" not in email:
        raise HTTPException(status_code=400, detail="Valid email is required")
    if not body.password or len(body.password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")

    with auth_connection() as conn:
        user_row = conn.execute(
            text(
                "SELECT id, name, \"isBootstrapAdmin\" FROM \"user\" "
                "WHERE id = :uid AND status = 'active' LIMIT 1"
            ),
            {"uid": body.user_id},
        ).fetchone()

        if user_row is None:
            raise HTTPException(status_code=404, detail="User not found")

        user_dict = dict(user_row._mapping)
        if not bool(user_dict.get("isBootstrapAdmin", False)):
            raise HTTPException(status_code=403, detail="Not a bootstrap admin")

        existing = conn.execute(
            text("SELECT id FROM \"user\" WHERE email = :email AND id != :uid"),
            {"email": email, "uid": body.user_id},
        ).fetchone()
        if existing:
            raise HTTPException(status_code=409, detail="Email already in use")

        account_row = conn.execute(
            text("SELECT id FROM account WHERE \"userId\" = :uid LIMIT 1"),
            {"uid": body.user_id},
        ).fetchone()
        if account_row is not None:
            raise HTTPException(status_code=400, detail="Account already set up")

        now = datetime.now(UTC).isoformat().replace("+00:00", "Z")
        hashed = hash_password(body.password)
        account_id = f"acc_{secrets.token_hex(8)}"

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
                "uid": body.user_id,
                "pw": hashed,
                "ca": now,
                "ua": now,
            },
        )

        conn.execute(
            text(
                "UPDATE \"user\" SET email = :email, \"emailVerified\" = 1, "
                "\"mustChangePassword\" = 0, \"isBootstrapAdmin\" = 0, \"updatedAt\" = :ua WHERE id = :uid"
            ),
            {"email": email, "ua": now, "uid": body.user_id},
        )

        conn.commit()

    return SetupBootstrapAdminResponse(success=True, email=email)
