"""Owned loopback MCP target: real bounded CSV/SQLite analysis, no model or host files."""

import csv
import hashlib
import hmac
import io
import json
import os
from pathlib import Path
import sqlite3

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from starlette.responses import JSONResponse
import uvicorn

STATE = Path(os.environ["PRISMOS_ANALYTICS_STATE"]).resolve()
assert STATE.is_dir() and STATE.stat().st_mode & 0o777 == 0o700
TOKEN = (STATE / "token").read_text().strip()
assert len(TOKEN) >= 32
server = FastMCP(
    "prismos-owned-analytics",
    host="127.0.0.1",
    port=18041,
    stateless_http=True,
    json_response=True,
    log_level="ERROR",
)


@server.tool(
    annotations=ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    )
)
def analyze_revenue(csv_text: str) -> dict:
    """Analyze uploaded CSV columns category, amount, marker with real SQLite aggregation. No filesystem or external business writes."""
    if len(csv_text.encode()) > 16000:
        raise ValueError("CSV input too large")
    reader = csv.DictReader(io.StringIO(csv_text))
    if reader.fieldnames != ["category", "amount", "marker"]:
        raise ValueError("CSV columns must be category,amount,marker")
    rows = list(reader)
    if not 1 <= len(rows) <= 128:
        raise ValueError("CSV row count unavailable")
    values = []
    for row in rows:
        category, amount, marker = row["category"], row["amount"], row["marker"]
        if (
            not category
            or len(category) > 100
            or not amount.isdigit()
            or not 0 <= int(amount) <= 10**9
            or len(marker) > 100
        ):
            raise ValueError("CSV row unavailable")
        values.append((category, int(amount), marker))
    with sqlite3.connect(":memory:") as db:
        db.execute("CREATE TABLE revenue(category TEXT, amount INTEGER, marker TEXT)")
        db.executemany("INSERT INTO revenue VALUES (?, ?, ?)", values)
        total, count = db.execute(
            "SELECT SUM(amount), COUNT(*) FROM revenue"
        ).fetchone()
        top = db.execute(
            "SELECT category, amount FROM revenue ORDER BY amount DESC, category LIMIT 1"
        ).fetchone()
    result = {
        "total": total,
        "row_count": count,
        "highest_category": top[0],
        "highest_amount": top[1],
        "markers": [m for _, _, m in values if m],
        "input_sha256": hashlib.sha256(csv_text.encode()).hexdigest(),
        "engine": "sqlite3",
        "external_business_writes": False,
    }
    with (STATE / "calls.jsonl").open("a") as stream:
        stream.write(json.dumps(result) + "\n")
    (STATE / "calls.jsonl").chmod(0o600)
    return result


inner = server.streamable_http_app()


async def app(scope, receive, send):
    if scope["type"] != "http":
        return await inner(scope, receive, send)
    if scope["path"] == "/health":
        return await JSONResponse({"status": "ok"})(scope, receive, send)
    auth = dict(scope["headers"]).get(b"authorization", b"").decode()
    if not hmac.compare_digest(auth, "Bearer " + TOKEN):
        return await JSONResponse({"error": "unauthorized"}, status_code=401)(
            scope, receive, send
        )
    if scope["path"] == "/stats":
        calls = STATE / "calls.jsonl"
        return await JSONResponse(
            {
                "completed_tool_calls": len(calls.read_text().splitlines())
                if calls.exists()
                else 0
            }
        )(scope, receive, send)
    await inner(scope, receive, send)


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=18041, log_level="error", access_log=False)
