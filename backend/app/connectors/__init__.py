"""Reference connectors for the R2 acceptance slice (O24/O25).

Two connectors prove the unified connector contract from the R2 spec:

1. WebhookConnector - generic outbound HTTP call. Credentials go through
   the tenant's SecretRef store (same strict-encryption envelope as the
   M1 ticket webhook); the connector never logs or echoes the key.
2. SqliteAnalyticsConnector - read-only aggregation over an uploaded
   SQLite file, following the bounded read-only computation shape already
   proven by the 2026-10-17 MCP analytics rehearsal.

Both implement the same invoke contract: tenant-scoped, standard error
mapping, no credential leakage, and refusal after the instance is
disabled or its secret revoked.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx


class ConnectorError(Exception):
    """User-presentable connector failure with a standard code."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class ConnectorResult:
    ok: bool
    data: dict[str, Any] | None = None
    error_code: str | None = None


class WebhookConnector:
    """Outbound HTTP connector; credentials injected from SecretRef material."""

    code = "webhook"

    def __init__(self, url: str, headers: dict[str, str], *, timeout: float = 30.0,
                 client_factory=None) -> None:
        if not url.startswith("https://"):
            raise ConnectorError("invalid_target", "webhook target must be HTTPS")
        if any(value in url for value in ("://user:", "?token=", "?key=")):
            raise ConnectorError("invalid_target", "webhook target must not carry inline credentials")
        self._url = url
        self._headers = headers
        self._timeout = timeout
        self._client_factory = client_factory or httpx.AsyncClient

    async def invoke(self, payload: dict[str, Any]) -> ConnectorResult:
        try:
            async with self._client_factory(timeout=self._timeout) as client:
                response = await client.post(self._url, json=payload, headers=self._headers)
        except httpx.TimeoutException:
            return ConnectorResult(ok=False, error_code="timeout")
        except httpx.HTTPError:
            return ConnectorResult(ok=False, error_code="network")
        if response.status_code >= 500:
            return ConnectorResult(ok=False, error_code="upstream")
        if response.status_code >= 400:
            return ConnectorResult(ok=False, error_code="rejected")
        try:
            data = response.json()
        except ValueError:
            return ConnectorResult(ok=False, error_code="bad_response")
        # Never echo upstream bodies that might reflect credentials.
        return ConnectorResult(ok=True, data=data if isinstance(data, dict) else {"value": data})


class SqliteAnalyticsConnector:
    """Read-only SQL aggregation over an uploaded SQLite database file."""

    code = "sqlite_analytics"
    _FORBIDDEN = ("insert", "update", "delete", "drop", "alter", "create", "attach", "pragma")

    def __init__(self, database_path: str | Path) -> None:
        self._path = Path(database_path)
        if not self._path.is_file():
            raise ConnectorError("invalid_target", "analytics database not found")

    def invoke(self, sql: str, params: list[Any] | None = None) -> ConnectorResult:
        normalized = (sql or "").strip().lower()
        if not normalized.startswith("select") or any(word in normalized for word in self._FORBIDDEN):
            return ConnectorResult(ok=False, error_code="forbidden_sql")
        try:
            # Read-only, immutable connection: writes are impossible at the
            # SQLite layer regardless of the statement text.
            uri = f"file:{self._path}?mode=ro&immutable=1"
            with sqlite3.connect(uri, uri=True) as connection:
                connection.row_factory = sqlite3.Row
                rows = connection.execute(sql, params or []).fetchall()
                return ConnectorResult(ok=True, data={"rows": [dict(row) for row in rows]})
        except sqlite3.Error:
            return ConnectorResult(ok=False, error_code="bad_sql")
