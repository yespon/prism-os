# PrismOS verification debt baseline

## Identity

- Plan: `docs/superpowers/plans/2026-08-09-prismos-verification-debt-cleanup.md`
- Worktree: `/Users/yespon/Documents/AgentOS/prism-platform/.worktrees/prismos-brand-root-migration`
- Branch: `codex/prismos-brand-root-migration`
- Base SHA: `9af18f816022b1d29ea89b0b064bae0ba9eddfcf`
- Captured: 2026-08-09 (Asia/Shanghai)

## Toolchain

| Tool | Version |
|---|---|
| Node | `v23.11.0` |
| pnpm | `10.11.0` |
| Python | `3.12.7` |
| pytest | `9.0.2` |
| Ruff | `0.14.11` |

## Commands and exit codes

| Area | Exact command | Exit code | Artifact |
|---|---|---:|---|
| Frontend | `cd frontend && pnpm typecheck` | 1 | `frontend-typecheck.log` |
| Frontend | `cd frontend && pnpm test:unit` | 1 | `frontend-unit.log` |
| Frontend | `cd frontend && pnpm lint` | 1 | `frontend-lint.log` |
| Frontend | `cd frontend && pnpm build` | 1 | `frontend-build.log` |
| Backend | `cd backend && uv run pytest --collect-only -q` | 0 | `backend-collection.log` |
| Backend | `cd backend && uv run pytest -q` | 1 | `backend-pytest.log` |
| Backend | `cd backend && uv run ruff check app packages/harness/deerflow tests scripts` | 1 | `backend-ruff.log` |

The backend commands were initially attempted with `uv run`, but the sandbox denied access to the existing uv cache repository at `/Users/yespon/.cache/uv/sdists-v9/.git`. The captured backend execution used the worktree's already-installed `backend/.venv/bin/pytest` and `backend/.venv/bin/ruff` with identical command arguments; the final gate must still execute the exact `uv run` commands and record their own exit codes.

## Summary

- Frontend typecheck: 13 TypeScript diagnostics. The build stops on these same diagnostics.
- Frontend unit: 32 failed and 54 passed tests (86 total), across 17 failed and 18 passed files.
- Frontend lint: 558 errors and 192 warnings, 750 problems total.
- Backend collection: 1205 tests collected.
- Backend pytest: 179 failed, 1009 passed, 18 skipped, 29 warnings.
- Backend Ruff: 234 errors; 186 reported as fixable with `--fix`.

## Failure inventory

| Domain | Failing nodes/files | Root-cause hypothesis | Owner task | Verification |
|---|---|---|---|---|
| Frontend type/build | `src/app/workspace/files/page.tsx:108`, `:418`; `src/app/workspace/skills/[name]/page.tsx:73`; 10 stale keys in `src/core/i18n/locales/en-US.ts` | parent-folder stack is indexed without an empty guard; `uploadingFiles` belongs to `uploads`; skill hook only supports `cmd | agent`; shared translation interface lags the canonical locale shape | Task 2 | `pnpm typecheck`; `pnpm build` |
| Frontend unit/provider | 17 test files, led by admin/tenant/workspace components | consumer components now require `I18nProvider`, `QueryClientProvider`, router, or complete module mocks but test helpers still render partial trees | Task 3 | focused Vitest; `pnpm test:unit` |
| Frontend lint | 750 problems across source/tests | accumulated mechanical and behavior-sensitive lint debt | Task 4 | `pnpm lint` |
| Backend client/harness | large `tests/test_client.py` and `tests/test_client_e2e.py` cluster | `DeerFlowClient` public methods and module exports diverged from the test/API contract | Task 5 | client-focused pytest |
| Backend tenant/auth/schema | auth middleware, tenant context, config router tests | test DB/schema lifecycle does not provide tenant tables/config rows for isolated request tests | Task 5 | tenant/auth-focused pytest |
| Backend model/task/router | `tests/test_model_factory.py`, `tests/test_task_tool_core_logic.py`, related router/middleware nodes | call signatures and model/task contracts diverged from current implementation | Task 6 | focused pytest |
| Backend Ruff | 234 diagnostics across app, harness, tests, scripts | accumulated import, unused, formatting, and typing debt | Task 7 | exact Ruff gate |

## Protected boundaries

No database schema, Alembic history, persistent IDs, public API path, `deerflow` import, LangGraph interface, or `backend/opsintech.db` file was changed or used as a writable fixture during baseline capture.
