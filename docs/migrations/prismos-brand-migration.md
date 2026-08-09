# PrismOS brand-root migration guide

This guide moves an existing installation to the PrismOS product identity while
preserving user data and existing API/database contracts. It is deliberately a
bounded compatibility bridge, not a second permanent configuration model.

## Release boundary

- Migration release: `0.2.x`
- Runtime compatibility removal: `0.3.0`
- The offline home migration CLI remains available after `0.3.0` so an operator
  can migrate an archived installation without running the old runtime bridge.

## Local home migration

Preflight: `uv run python scripts/migrate_prismos_home.py --source ~/.opsintech --target ~/.prismos`

Run the preflight first. It validates the source, enumerates files, checks open
files and available space, and makes no filesystem changes:

```bash
uv run python scripts/migrate_prismos_home.py --source ~/.opsintech --target ~/.prismos
```

Apply: add `--apply`

Apply only after reviewing the plan and taking a backup:

```bash
uv run python scripts/migrate_prismos_home.py --source ~/.opsintech --target ~/.prismos --apply
```

The apply path copies files to a temporary target, verifies every file by size
and SHA-256, writes a manifest, and atomically activates the target. It never
deletes or overwrites the source. Rollback: set `PRISMOS_HOME` to the preserved
source, stop the service before switching paths, and restore from the backup if
the application has already written new state.

## Conflict and compatibility rules

- Conflict behavior: `PRISMOS_*` wins; invalid `PRISMOS_*` never falls back.
- Legacy variables are read-only compatibility inputs and emit deprecation
  telemetry; new code must consume only `PRISMOS_*`.
- Browser behavior: read old once, verify new, write only new. A legacy browser
  value is removed only after the canonical value can be read back and parsed.
- Object storage: detect and plan only; no automatic remote copy/delete.

### Environment aliases

The single runtime adapter in
`backend/packages/harness/deerflow/config/prismos_env.py` owns these aliases:

| Canonical input | Legacy input | Owner | 0.3.0 removal checklist |
|---|---|---|---|
| `PRISMOS_HOME` | `OPSINTECH_HOME` | Runtime Config | Remove alias and legacy-home discovery from runtime; retain offline CLI. |
| `PRISMOS_CONFIG_PATH` | `OPSINTECH_CONFIG_PATH` | Runtime Config | Remove alias; update tests and operator examples to canonical input. |
| `PRISMOS_EXTENSIONS_CONFIG_PATH` | `OPSINTECH_EXTENSIONS_CONFIG_PATH` | Runtime Config | Remove alias and compatibility test. |
| `PRISMOS_HOST_BASE_DIR` | `OPSINTECH_HOST_BASE_DIR` | Runtime Config | Remove alias and compatibility test. |
| `PRISMOS_HOST_SKILLS_PATH` | `OPSINTECH_HOST_SKILLS_PATH` | Runtime Config | Remove alias and compatibility test. |
| `PRISMOS_SANDBOX_HOST` | `OPSINTECH_SANDBOX_HOST` | Runtime Config | Remove alias and compatibility test. |
| `PRISMOS_STORAGE_BACKEND` | `OPSINTECH_STORAGE_BACKEND` | Runtime Config | Remove alias; keep canonical storage selection. |
| `PRISMOS_STORAGE_LOCAL_ROOT` | `OPSINTECH_STORAGE_LOCAL_ROOT` | Runtime Config | Remove alias and compatibility test. |
| `PRISMOS_STORAGE_S3_ENDPOINT` | `OPSINTECH_STORAGE_S3_ENDPOINT` | Runtime Config | Remove alias and compatibility test. |
| `PRISMOS_STORAGE_S3_ACCESS_KEY` | `OPSINTECH_STORAGE_S3_ACCESS_KEY` | Runtime Config | Remove alias; rotate secrets independently when required. |
| `PRISMOS_STORAGE_S3_SECRET_KEY` | `OPSINTECH_STORAGE_S3_SECRET_KEY` | Runtime Config | Remove alias; rotate secrets independently when required. |
| `PRISMOS_STORAGE_S3_BUCKET` | `OPSINTECH_STORAGE_S3_BUCKET` | Runtime Config | Remove alias; keep remote resource detection read-only. |
| `PRISMOS_STORAGE_S3_REGION` | `OPSINTECH_STORAGE_S3_REGION` | Runtime Config | Remove alias and compatibility test. |
| `PRISMOS_STORAGE_S3_USE_SSL` | `OPSINTECH_STORAGE_S3_USE_SSL` | Runtime Config | Remove alias and compatibility test. |
| `PRISMOS_STORAGE_JUICEFS_MOUNT` | `OPSINTECH_STORAGE_JUICEFS_MOUNT` | Runtime Config | Remove alias and compatibility test. |
| `PRISMOS_STORAGE_JUICEFS_SUBDIR` | `OPSINTECH_STORAGE_JUICEFS_SUBDIR` | Runtime Config | Remove alias; keep canonical prefix behavior. |

### Browser storage mappings

The frontend migration helper owns these one-time mappings:

| Legacy key | Canonical key | Owner | 0.3.0 removal checklist |
|---|---|---|---|
| `opsintech.local-settings` | `prismos_local_settings` | Frontend Settings | Remove legacy consumer and migration test. |
| `opsintech:models:disabled` | `prismos_models_disabled` | Frontend Models | Remove legacy consumer and migration test. |
| `opsintech.current_tenant_id` | `prismos_current_tenant_id` | Frontend Tenants | Remove legacy consumer and event compatibility. |
| `opsintech_terminal_chats` | `prismos_terminal_chats` | Frontend Terminal | Remove legacy consumer and migration test. |
| `opsintech_auto_approval_settings` | `prismos_auto_approval_settings` | Frontend Terminal Security | Remove legacy consumer and migration test. |
| `opsintech_terminal_security_config` | `prismos_terminal_security_config` | Frontend Terminal Security | Remove legacy consumer and migration test. |
| `opsintech_terminal_theme` | `prismos_terminal_theme` | Frontend Terminal Preferences | Remove legacy consumer and migration test. |
| `opsintech_host_sidebar_collapsed` | `prismos_host_sidebar_collapsed` | Frontend Terminal Preferences | Remove legacy consumer and migration test. |

### Remote object resources

`backend/packages/harness/deerflow/storage/legacy_resources.py` is the owner of
the legacy remote-resource detector. It detects the old `opsintech-files` S3
bucket and JuiceFS prefix, and returns operator guidance. It may validate access
with a read-only `head_bucket`, but it only detects and plans: it never copies,
renames, or deletes real remote objects. Operators must create and review an
explicit remote migration plan, then verify both old and new resources before
changing the canonical configuration.

## Verification

After migration, verify the manifest, start with canonical `PRISMOS_*` inputs,
check application logs for unexpected legacy reads, and confirm that new browser
activity and storage writes use only canonical names. Keep the source backup
until the deployment has completed an agreed observation window.
