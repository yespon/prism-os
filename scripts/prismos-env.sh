#!/usr/bin/env bash
# Resolve PrismOS runtime settings while accepting legacy OPSINTECH_* inputs.
#
# This is the host-boundary compatibility adapter.  It reads legacy names,
# exports only PRISMOS_* names, and records which legacy inputs were selected.

prismos_record_legacy_input() {
    local legacy_name="$1"
    case ",${PRISMOS_LEGACY_INPUTS:-}," in
        *,"$legacy_name",*)
            return
            ;;
    esac
    if [ -n "${PRISMOS_LEGACY_INPUTS:-}" ]; then
        PRISMOS_LEGACY_INPUTS="${PRISMOS_LEGACY_INPUTS},${legacy_name}"
    else
        PRISMOS_LEGACY_INPUTS="$legacy_name"
    fi
    export PRISMOS_LEGACY_INPUTS
    printf 'WARNING: %s is deprecated; migrate before PrismOS 0.3.0\n' "$legacy_name" >&2
}

prismos_warn_conflict() {
    local canonical_name="$1"
    local legacy_name="$2"
    printf 'WARNING: %s overrides conflicting legacy input %s; migrate before PrismOS 0.3.0\n' \
        "$canonical_name" "$legacy_name" >&2
}

prismos_resolve_setting() {
    local canonical_name="$1"
    local default_value="$2"
    shift 2
    local legacy_name legacy_value canonical_value

    canonical_value="${!canonical_name:-}"
    if [ -n "$canonical_value" ]; then
        for legacy_name in "$@"; do
            legacy_value="${!legacy_name:-}"
            if [ -n "$legacy_value" ]; then
                prismos_warn_conflict "$canonical_name" "$legacy_name"
            fi
        done
        printf -v "$canonical_name" '%s' "$canonical_value"
        export "$canonical_name"
        return
    fi

    for legacy_name in "$@"; do
        legacy_value="${!legacy_name:-}"
        if [ -n "$legacy_value" ]; then
            printf -v "$canonical_name" '%s' "$legacy_value"
            export "$canonical_name"
            prismos_record_legacy_input "$legacy_name"
            return
        fi
    done

    printf -v "$canonical_name" '%s' "$default_value"
    export "$canonical_name"
}

prismos_resolve_environment() {
    local script_root default_home

    script_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

    prismos_resolve_setting PRISMOS_REPO_ROOT "$script_root" OPSINTECH_REPO_ROOT OPSINTECH_ROOT
    default_home="$PRISMOS_REPO_ROOT/backend/.prismos"
    prismos_resolve_setting PRISMOS_HOME "$default_home" OPSINTECH_HOME
    prismos_resolve_setting PRISMOS_CONFIG_PATH "$PRISMOS_REPO_ROOT/config.yaml" OPSINTECH_CONFIG_PATH
    prismos_resolve_setting PRISMOS_DOCKER_SOCKET /var/run/docker.sock OPSINTECH_DOCKER_SOCKET
    prismos_resolve_setting PRISMOS_HOST_BASE_DIR "$PRISMOS_HOME" OPSINTECH_HOST_BASE_DIR
    prismos_resolve_setting PRISMOS_HOST_SKILLS_PATH "$PRISMOS_REPO_ROOT/skills" OPSINTECH_HOST_SKILLS_PATH
    prismos_resolve_setting PRISMOS_COMPOSE_PROJECT prismos OPSINTECH_COMPOSE_PROJECT
    prismos_resolve_setting PRISMOS_K8S_NAMESPACE prismos OPSINTECH_K8S_NAMESPACE
    prismos_resolve_setting PRISMOS_POSTGRES_USER prismos OPSINTECH_POSTGRES_USER POSTGRES_USER
    prismos_resolve_setting PRISMOS_POSTGRES_PASSWORD prismos OPSINTECH_POSTGRES_PASSWORD POSTGRES_PASSWORD
    prismos_resolve_setting PRISMOS_POSTGRES_DB prismos OPSINTECH_POSTGRES_DB POSTGRES_DB

    if [ ! -e "$PRISMOS_HOME" ] && [ -e "$PRISMOS_REPO_ROOT/backend/.opsintech" ]; then
        printf 'WARNING: legacy data detected at %s; run:\n' \
            "$PRISMOS_REPO_ROOT/backend/.opsintech" >&2
        printf '  cd backend && uv run python scripts/migrate_prismos_home.py --source .opsintech --target .prismos\n' >&2
    fi

    # Do not leak old aliases into child processes.  Their values have already
    # been consumed and, when selected, recorded in PRISMOS_LEGACY_INPUTS.
    unset OPSINTECH_REPO_ROOT OPSINTECH_ROOT OPSINTECH_HOME OPSINTECH_CONFIG_PATH \
        OPSINTECH_DOCKER_SOCKET OPSINTECH_HOST_BASE_DIR OPSINTECH_HOST_SKILLS_PATH \
        OPSINTECH_COMPOSE_PROJECT OPSINTECH_K8S_NAMESPACE OPSINTECH_POSTGRES_USER \
        OPSINTECH_POSTGRES_PASSWORD OPSINTECH_POSTGRES_DB
}

prismos_resolve_environment
unset -f prismos_resolve_environment prismos_resolve_setting prismos_record_legacy_input prismos_warn_conflict

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    for variable in \
        PRISMOS_REPO_ROOT PRISMOS_HOME PRISMOS_CONFIG_PATH PRISMOS_DOCKER_SOCKET \
        PRISMOS_HOST_BASE_DIR PRISMOS_HOST_SKILLS_PATH PRISMOS_COMPOSE_PROJECT \
        PRISMOS_K8S_NAMESPACE PRISMOS_POSTGRES_USER PRISMOS_POSTGRES_PASSWORD \
        PRISMOS_POSTGRES_DB PRISMOS_LEGACY_INPUTS; do
        printf 'export %s=%q\n' "$variable" "${!variable:-}"
    done
fi
