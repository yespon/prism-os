# PrismOS 0.3.0 legacy bridge removal checklist

This checklist is the breaking-change work item for removing the bounded `0.2.x`
runtime compatibility bridge. Complete it only after the migration guide has
been published and supported installations have had an upgrade window.

## Runtime and deployment

- [ ] Delete `LEGACY_ENV_ALIASES` and legacy fallback reads from the Python
  runtime adapter; keep `PRISMOS_*` validation and conflict semantics.
- [ ] Delete old environment inputs from shell adapters, Compose examples and
  deployment compatibility tests.
- [ ] Delete runtime legacy-home discovery and any code path that selects the
  old home automatically.
- [ ] Keep `scripts/migrate_prismos_home.py` as an offline, explicit migration
  tool; it may still accept an old source path because archived data must remain
  recoverable.

## Frontend

- [ ] Delete all legacy localStorage consumers and one-time migration calls.
- [ ] Delete legacy browser migration tests and event compatibility listeners.
- [ ] Confirm every read and write uses the canonical `prismos_*`/`prismos:*`
  namespace.

## Storage and release gates

- [ ] Reduce the runtime brand allowlist to zero compatibility entries; retain
  only the offline tool, migration documentation and precisely marked historical
  records.
- [ ] Keep remote-resource detection read-only until a separately approved
  object-storage migration exists; do not add automatic copy/delete behavior.
- [ ] Run `bash scripts/test-prismos-product-identity.sh`.
- [ ] Run the full backend test suite and the frontend lint, typecheck, unit and
  build gates.
- [ ] Run `git diff --check` and the repository brand scanner.
- [ ] Publish release notes that name the `0.2.x` compatibility window, the
  `0.3.0` breaking boundary, migration command, rollback path, and removed
  inputs.

## Exit evidence

Attach the migration adoption report, scanner output, backend/frontend test
output, and a release note review to the `0.3.0` change record. Do not change
database tables, Alembic history, public API paths, persistent IDs, or DeerFlow
and LangGraph interfaces as part of this bridge removal.
