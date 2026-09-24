#!/usr/bin/env bash
set -euo pipefail

uv_bin="${UV_BIN:-$(command -v uv || true)}"
if [[ -z "$uv_bin" ]]; then
  printf 'uv not found; install uv or set UV_BIN\n' >&2
  exit 1
fi

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root/backend"

"$uv_bin" run pytest tests/contracts -q
"$uv_bin" run pytest \
  tests/test_authorization_tenant_context.py \
  tests/test_guardrail_middleware.py \
  tests/test_terminal_security.py -q
alembic_heads="$("$uv_bin" run python -m alembic heads)"
printf '%s\n' "$alembic_heads"
head_count="$(printf '%s\n' "$alembic_heads" | awk '/\(head\)$/ {count++} END {print count + 0}')"
if [[ "$head_count" -ne 1 ]]; then
  printf 'expected exactly one Alembic head, found %s\n' "$head_count" >&2
  exit 1
fi
"$uv_bin" run python -m ruff check app/platform app/models/governance.py tests/contracts
