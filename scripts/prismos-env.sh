#!/usr/bin/env bash
# Resolve PrismOS runtime settings while accepting legacy OPSINTECH_* inputs.
#
# Source this file before invoking local scripts or Docker Compose.  Every
# setting follows the same precedence: PRISMOS_* -> OPSINTECH_* -> default.

prismos_resolve_environment() {
    local script_root default_home

    script_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

    export PRISMOS_REPO_ROOT="${PRISMOS_REPO_ROOT:-${OPSINTECH_REPO_ROOT:-${OPSINTECH_ROOT:-$script_root}}}"

    if [ -n "${PRISMOS_HOME:-}" ]; then
        : # An explicit PrismOS home always wins, including for an empty directory.
    elif [ -n "${OPSINTECH_HOME:-}" ]; then
        export PRISMOS_HOME="$OPSINTECH_HOME"
    else
        default_home="$PRISMOS_REPO_ROOT/backend/.prismos"
        if [ ! -e "$default_home" ] && [ -e "$PRISMOS_REPO_ROOT/backend/.opsintech" ]; then
            # Existing deployments keep using their data in place.  Do not copy,
            # rename, delete, or otherwise mutate the legacy directory here.
            export PRISMOS_HOME="$PRISMOS_REPO_ROOT/backend/.opsintech"
        else
            export PRISMOS_HOME="$default_home"
        fi
    fi

    export PRISMOS_CONFIG_PATH="${PRISMOS_CONFIG_PATH:-${OPSINTECH_CONFIG_PATH:-$PRISMOS_REPO_ROOT/config.yaml}}"
    export PRISMOS_DOCKER_SOCKET="${PRISMOS_DOCKER_SOCKET:-${OPSINTECH_DOCKER_SOCKET:-/var/run/docker.sock}}"
    export PRISMOS_HOST_BASE_DIR="${PRISMOS_HOST_BASE_DIR:-${OPSINTECH_HOST_BASE_DIR:-$PRISMOS_HOME}}"
    export PRISMOS_HOST_SKILLS_PATH="${PRISMOS_HOST_SKILLS_PATH:-${OPSINTECH_HOST_SKILLS_PATH:-$PRISMOS_REPO_ROOT/skills}}"
    export PRISMOS_COMPOSE_PROJECT="${PRISMOS_COMPOSE_PROJECT:-${OPSINTECH_COMPOSE_PROJECT:-prismos}}"
    export PRISMOS_K8S_NAMESPACE="${PRISMOS_K8S_NAMESPACE:-${OPSINTECH_K8S_NAMESPACE:-prismos}}"
    export PRISMOS_POSTGRES_USER="${PRISMOS_POSTGRES_USER:-${OPSINTECH_POSTGRES_USER:-${POSTGRES_USER:-prismos}}}"
    export PRISMOS_POSTGRES_PASSWORD="${PRISMOS_POSTGRES_PASSWORD:-${OPSINTECH_POSTGRES_PASSWORD:-${POSTGRES_PASSWORD:-prismos}}}"
    export PRISMOS_POSTGRES_DB="${PRISMOS_POSTGRES_DB:-${OPSINTECH_POSTGRES_DB:-${POSTGRES_DB:-prismos}}}"

    # DeerFlow currently consumes the historic names.  Export resolved aliases
    # so its imports, API routes, schemas, and existing configuration remain
    # untouched while callers move to the PrismOS interface.
    export OPSINTECH_REPO_ROOT="$PRISMOS_REPO_ROOT"
    export OPSINTECH_ROOT="$PRISMOS_REPO_ROOT"
    export OPSINTECH_HOME="$PRISMOS_HOME"
    export OPSINTECH_CONFIG_PATH="$PRISMOS_CONFIG_PATH"
    export OPSINTECH_DOCKER_SOCKET="$PRISMOS_DOCKER_SOCKET"
    export OPSINTECH_HOST_BASE_DIR="$PRISMOS_HOST_BASE_DIR"
    export OPSINTECH_HOST_SKILLS_PATH="$PRISMOS_HOST_SKILLS_PATH"
    export OPSINTECH_COMPOSE_PROJECT="$PRISMOS_COMPOSE_PROJECT"
    export OPSINTECH_K8S_NAMESPACE="$PRISMOS_K8S_NAMESPACE"
    export OPSINTECH_POSTGRES_USER="$PRISMOS_POSTGRES_USER"
    export OPSINTECH_POSTGRES_PASSWORD="$PRISMOS_POSTGRES_PASSWORD"
    export OPSINTECH_POSTGRES_DB="$PRISMOS_POSTGRES_DB"
}

prismos_resolve_environment
unset -f prismos_resolve_environment

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    for variable in \
        PRISMOS_REPO_ROOT PRISMOS_HOME PRISMOS_CONFIG_PATH PRISMOS_DOCKER_SOCKET \
        PRISMOS_HOST_BASE_DIR PRISMOS_HOST_SKILLS_PATH PRISMOS_COMPOSE_PROJECT \
        PRISMOS_K8S_NAMESPACE PRISMOS_POSTGRES_USER PRISMOS_POSTGRES_PASSWORD \
        PRISMOS_POSTGRES_DB; do
        printf 'export %s=%q\n' "$variable" "${!variable}"
    done
fi
