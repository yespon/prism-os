#!/usr/bin/env bash
# Regression coverage for PrismOS environment compatibility resolution.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_SCRIPT="$SCRIPT_DIR/prismos-env.sh"
TEMP_ROOT="$(mktemp -d)"
trap 'rm -rf "$TEMP_ROOT"' EXIT

assert_equals() {
    local expected="$1"
    local actual="$2"
    local message="$3"

    if [ "$expected" != "$actual" ]; then
        echo "FAIL: $message" >&2
        echo "  expected: $expected" >&2
        echo "  actual:   $actual" >&2
        exit 1
    fi
}

resolve() {
    env -i PATH="$PATH" "$@" bash -c '
        source "$1"
        printf "%s|%s|%s|%s|%s\n" \
            "$PRISMOS_HOME" "$PRISMOS_CONFIG_PATH" "$PRISMOS_COMPOSE_PROJECT" \
            "$PRISMOS_POSTGRES_USER" "$OPSINTECH_HOME"
    ' bash "$ENV_SCRIPT"
}

# This fails if a future change lets OPSINTECH_* override an explicit PRISMOS_*.
result="$(resolve \
    PRISMOS_REPO_ROOT="$TEMP_ROOT" \
    PRISMOS_HOME=/new/home \
    OPSINTECH_HOME=/legacy/home \
    PRISMOS_CONFIG_PATH=/new/config.yaml \
    OPSINTECH_CONFIG_PATH=/legacy/config.yaml \
    PRISMOS_COMPOSE_PROJECT=new-project \
    OPSINTECH_COMPOSE_PROJECT=legacy-project \
    PRISMOS_POSTGRES_USER=new-db-user \
    OPSINTECH_POSTGRES_USER=legacy-db-user)"
assert_equals "/new/home|/new/config.yaml|new-project|new-db-user|/new/home" "$result" "PRISMOS_* takes precedence"

# This fails if legacy deployments can no longer supply their existing values.
result="$(resolve \
    PRISMOS_REPO_ROOT="$TEMP_ROOT" \
    OPSINTECH_HOME=/legacy/home \
    OPSINTECH_CONFIG_PATH=/legacy/config.yaml \
    OPSINTECH_COMPOSE_PROJECT=legacy-project \
    OPSINTECH_POSTGRES_USER=legacy-db-user)"
assert_equals "/legacy/home|/legacy/config.yaml|legacy-project|legacy-db-user|/legacy/home" "$result" "OPSINTECH_* remains a fallback"

# OPSINTECH_ROOT was the legacy repository-root spelling used by the
# development Compose setup and must remain a valid compatibility input.
result="$(resolve \
    OPSINTECH_ROOT="$TEMP_ROOT")"
assert_equals "$TEMP_ROOT/backend/.prismos|$TEMP_ROOT/config.yaml|prismos|prismos|$TEMP_ROOT/backend/.prismos" "$result" "OPSINTECH_ROOT remains a repository-root fallback"

# This fails if a fresh deployment stops using the PrismOS defaults.
result="$(resolve PRISMOS_REPO_ROOT="$TEMP_ROOT")"
assert_equals "$TEMP_ROOT/backend/.prismos|$TEMP_ROOT/config.yaml|prismos|prismos|$TEMP_ROOT/backend/.prismos" "$result" "PrismOS defaults are used"

# This fails if existing data is ignored or rewritten instead of being selected.
mkdir -p "$TEMP_ROOT/backend/.opsintech"
result="$(resolve PRISMOS_REPO_ROOT="$TEMP_ROOT")"
assert_equals "$TEMP_ROOT/backend/.opsintech|$TEMP_ROOT/config.yaml|prismos|prismos|$TEMP_ROOT/backend/.opsintech" "$result" "existing .opsintech data is preserved as a fallback"

echo "PASS: PrismOS environment compatibility resolution"
