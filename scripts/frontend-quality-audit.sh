#!/usr/bin/env bash
# Run the frontend quality suite as an auditable, non-blocking report.
# The caller decides whether the report should gate a workflow.
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FRONTEND_DIR="${1:-$REPO_ROOT/frontend}"

cd "$FRONTEND_DIR"

summary_file=frontend-quality-summary.txt
: > "$summary_file"

run_audit() {
    local name="$1"
    shift
    echo "=== $name ==="
    "$@" > "frontend-quality-${name}.log" 2>&1
    local status=$?
    printf '%s=%s\n' "$name" "$status" >> "$summary_file"
    echo "$name exit status: $status"
}

run_audit lint pnpm lint
run_audit typecheck pnpm typecheck
run_audit unit pnpm test:unit --run
run_audit build env SKIP_ENV_VALIDATION=1 pnpm build

echo 'Frontend quality is recorded as an audit artifact and does not gate backend/runtime publication.'
