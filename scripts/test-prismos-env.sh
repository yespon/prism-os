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
        printf "%s|%s\n" "$PRISMOS_HOME" "${PRISMOS_LEGACY_INPUTS:-}"
    ' bash "$ENV_SCRIPT"
}

resolve_settings() {
    env -i PATH="$PATH" "$@" bash -c '
        source "$1"
        printf "%s|%s|%s\n" \
            "$PRISMOS_CONFIG_PATH" "$PRISMOS_COMPOSE_PROJECT" "$PRISMOS_POSTGRES_USER"
    ' bash "$ENV_SCRIPT"
}

# This fails if a future change lets OPSINTECH_* override an explicit PRISMOS_*.
result="$(resolve \
    PRISMOS_REPO_ROOT="$TEMP_ROOT" \
    PRISMOS_HOME=/new/home \
    OPSINTECH_HOME=/legacy/home)"
assert_equals "/new/home|" "$result" "new setting wins without exporting legacy aliases"

result="$(resolve OPSINTECH_HOME=/legacy)"
assert_equals "/legacy|OPSINTECH_HOME" "$result" "legacy input is normalized and reported"

result="$(resolve \
    PRISMOS_REPO_ROOT="$TEMP_ROOT" \
    PRISMOS_CONFIG_PATH=/new/config.yaml \
    OPSINTECH_CONFIG_PATH=/legacy/config.yaml \
    PRISMOS_COMPOSE_PROJECT=new-project \
    OPSINTECH_COMPOSE_PROJECT=legacy-project \
    PRISMOS_POSTGRES_USER=new-db-user \
    OPSINTECH_POSTGRES_USER=legacy-db-user)"
assert_equals "$TEMP_ROOT/backend/.prismos|" "$result" "PrismOS defaults are used when explicit settings are absent"

result="$(resolve_settings \
    PRISMOS_REPO_ROOT="$TEMP_ROOT" \
    PRISMOS_CONFIG_PATH=/new/config.yaml \
    OPSINTECH_CONFIG_PATH=/legacy/config.yaml \
    PRISMOS_COMPOSE_PROJECT=new-project \
    OPSINTECH_COMPOSE_PROJECT=legacy-project \
    PRISMOS_POSTGRES_USER=new-db-user \
    OPSINTECH_POSTGRES_USER=legacy-db-user)"
assert_equals "/new/config.yaml|new-project|new-db-user" "$result" "PRISMOS_* settings take precedence"

# This fails if legacy deployments can no longer supply their existing values.
result="$(resolve \
    PRISMOS_REPO_ROOT="$TEMP_ROOT" \
    OPSINTECH_HOME=/legacy/home \
    OPSINTECH_CONFIG_PATH=/legacy/config.yaml \
    OPSINTECH_COMPOSE_PROJECT=legacy-project \
    OPSINTECH_POSTGRES_USER=legacy-db-user)"
assert_equals "/legacy/home|OPSINTECH_HOME,OPSINTECH_CONFIG_PATH,OPSINTECH_COMPOSE_PROJECT,OPSINTECH_POSTGRES_USER" "$result" "OPSINTECH_* remains a reported fallback"

result="$(resolve_settings \
    PRISMOS_REPO_ROOT="$TEMP_ROOT" \
    OPSINTECH_CONFIG_PATH=/legacy/config.yaml \
    OPSINTECH_COMPOSE_PROJECT=legacy-project \
    OPSINTECH_POSTGRES_USER=legacy-db-user)"
assert_equals "/legacy/config.yaml|legacy-project|legacy-db-user" "$result" "legacy settings remain valid fallbacks"

# OPSINTECH_ROOT was the legacy repository-root spelling used by the
# development Compose setup and must remain a valid compatibility input.
result="$(resolve \
    OPSINTECH_ROOT="$TEMP_ROOT")"
assert_equals "$TEMP_ROOT/backend/.prismos|OPSINTECH_ROOT" "$result" "OPSINTECH_ROOT remains a repository-root fallback"

# This fails if a fresh deployment stops using the PrismOS defaults.
result="$(resolve PRISMOS_REPO_ROOT="$TEMP_ROOT")"
assert_equals "$TEMP_ROOT/backend/.prismos|" "$result" "PrismOS defaults are used"

# Existing legacy data must be reported for explicit migration rather than
# silently selected as the active home.
mkdir -p "$TEMP_ROOT/backend/.opsintech"
result="$(resolve PRISMOS_REPO_ROOT="$TEMP_ROOT")"
assert_equals "$TEMP_ROOT/backend/.prismos|" "$result" "existing .opsintech data is not selected automatically"

# Sourcing the adapter repeatedly must not duplicate its diagnostic list.
result="$(env -i PATH="$PATH" OPSINTECH_HOME=/legacy bash -c '
    source "$1"
    source "$1"
    printf "%s\n" "$PRISMOS_LEGACY_INPUTS"
' bash "$ENV_SCRIPT")"
assert_equals "OPSINTECH_HOME" "$result" "legacy input diagnostics remain de-duplicated"

# Legacy input names must not be re-exported into child processes after the
# host-boundary adapter has resolved them.
if env -i PATH="$PATH" OPSINTECH_HOME=/legacy bash -c 'source "$1"; env | grep -q "^OPSINTECH_"' bash "$ENV_SCRIPT"; then
    echo "FAIL: legacy aliases leaked back into the environment" >&2
    exit 1
fi

echo "PASS: PrismOS environment compatibility resolution"
