# SDD ledger — plan: docs/superpowers/plans/2026-08-09-prismos-verification-debt-cleanup.md

## Workspace

- Worktree: `/Users/yespon/Documents/AgentOS/prism-platform/.worktrees/prismos-brand-root-migration`
- Branch: `codex/prismos-brand-root-migration`
- Base at baseline capture: `9af18f816022b1d29ea89b0b064bae0ba9eddfcf`
- Subagent dispatch: attempted, but the available dispatcher rejected valid calls with `Provide either message or items, but not both`; execution continues locally with task-scoped commits and reviews, without claiming independent subagent findings.

## Global gate

The final gate remains blocked until all commands in the plan exit `0`; no directory rename or merge is permitted before then. `backend/opsintech.db`, schema history, persistence IDs, API paths, `deerflow` imports, and LangGraph interfaces are protected.

## Task 1: complete

Baseline artifacts:

- `baseline/README.md`
- `baseline/exit-codes.txt`
- `baseline/backend-exit-codes.txt`
- `baseline/frontend-typecheck.log`
- `baseline/frontend-unit.log`
- `baseline/frontend-lint.log`
- `baseline/frontend-build.log`
- `baseline/backend-collection.log`
- `baseline/backend-pytest.log`
- `baseline/backend-ruff.log`

Fresh baseline results:

- Frontend typecheck: exit `1`; 13 diagnostics covering file navigation, translation contract, and skill mode.
- Frontend unit: exit `1`; `32 failed`, `54 passed`, `86 total` tests across `17 failed`, `18 passed` files. Dominant first failure is missing `I18nProvider`, followed by missing query/router/provider contracts.
- Frontend lint: exit `1`; `558 errors`, `192 warnings` (`750 problems` total).
- Frontend build: exit `1`; compilation stopped on the same TypeScript translation-contract diagnostics.
- Backend collection: exit `0`; `1205 tests collected`.
- Backend pytest: exit `1`; `179 failed`, `1009 passed`, `18 skipped`, `29 warnings` in `29.93s`.
- Backend Ruff: exit `1`; `234 errors`, `186 fixable with `--fix`.

Environment notes:

- `uv run` was blocked in the sandbox while resolving `/Users/yespon/.cache/uv/sdists-v9/.git`; the backend baseline was captured with the existing worktree `backend/.venv` executables and this limitation remains recorded for the final strict `uv run` gate.
- No production database was modified. The existing `backend/.opsintech` test-side artifact was not staged.

## Task 2: complete

Reviewed files:

- `frontend/src/app/workspace/files/page.tsx`
- `frontend/src/app/workspace/skills/[name]/page.tsx`
- `frontend/src/core/i18n/locales/en-US.ts`

Changes were limited to the diagnosed frontend type/build contracts: safe empty folder-stack navigation, the canonical upload translation owner, the supported terminal-agent mode, and the canonical tenant-shaped English locale keys. No protected database, schema, API path, Deerflow import, or LangGraph interface was changed.

Verification evidence:

- `cd frontend && pnpm typecheck`: exit `0`.
- `cd frontend && pnpm build`: exit `0` when rerun with the approved escalated environment; Next.js 16.1.7 compiled, passed TypeScript, and generated 42 pages.
- `cd frontend && pnpm build` in the normal sandbox: environment failure before compilation because the Turbopack child process could not bind a port (`Operation not permitted (os error 1)`); this was not treated as a product failure.
- `cd frontend && pnpm test:unit`: still `32 failed`, `54 passed` across `86` tests and `17`/`18` failing/passing files. The failures are the pre-existing provider/fixture/mock clusters assigned to Task 3, not new failures from the Task 2 files.

Task 2 is committed independently as `fix: restore frontend type and build gates`; Task 3 owns the remaining frontend unit-test debt.

Failure inventory and ownership:

| Domain | Evidence | Root-cause hypothesis | Owner task | Verification |
|---|---|---|---|---|
| Frontend type/build | `frontend-typecheck.log`, `frontend-build.log` | stale shared translation shape, unsafe parent-folder indexing, unsupported skill mode | Task 2 | `pnpm typecheck`, `pnpm build` |
| Frontend unit providers | `frontend-unit.log` | tests render consumers without the production provider boundary; partial mocks omit required exports | Task 3 | focused Vitest, `pnpm test:unit` |
| Frontend lint | `frontend-lint.log` | accumulated import, promise, type-safety, hook, and accessibility debt | Task 4 | `pnpm lint` plus all frontend gates |
| Backend test infrastructure | `backend-pytest.log` | stale client/harness contract and incomplete tenant/auth test database setup | Task 5 | focused pytest, full pytest |
| Backend business behavior | `backend-pytest.log` | model factory, task tool, router/service and middleware contracts diverged from tests | Task 6 | focused pytest, full pytest |
| Backend Ruff | `backend-ruff.log` | accumulated import/unused/formatting and type-safety debt | Task 7 | `uv run ruff check app packages/harness/deerflow tests scripts` |

## Review record

- Task 1 is locally reviewed for reproducibility, artifact completeness, protected-file boundaries, and exact exit-code recording.
- Task 2 is locally reviewed for the diagnosed type/build contracts and protected-file boundaries; `pnpm typecheck` and the approved escalated `pnpm build` both exited `0`.

## Task 3: complete

Root causes confirmed from focused Vitest failures:

- Test consumers were rendered without the production `I18nProvider` and React Query provider boundaries.
- Partial module mocks omitted newly consumed hooks and router exports.
- Several assertions encoded removed UI labels or layout structure instead of the current component contract.
- `BackofficeShellLayout` accepted `bottomItems` but discarded them, which was a real production navigation regression exposed by the shell test.

Changes:

- Added `frontend/src/test/utils.tsx` with a real `I18nProvider`, isolated non-retrying `QueryClientProvider`, and the shared `render` wrapper.
- Migrated the affected unit tests to the shared provider boundary and completed their hook/router mocks.
- Updated stale assertions to current overview, skills, tools, admin navigation, and shell layout contracts.
- Restored rendering of `bottomItems` in `BackofficeShellLayout`, preserving active state and collapsed-sidebar behavior.

Verification evidence:

- Focused affected cluster: `7` test files, `12` tests passed; exit `0`.
- Full frontend unit suite: `35` test files, `86` tests passed; exit `0`.
- `git diff --check`: exit `0`.
- No `any`, `@ts-ignore`, or `@ts-expect-error` added in the Task 3 scope.

Task 3 is committed independently as `test: restore frontend provider and fixture contracts`.

## Review record

- Task 1 is locally reviewed for reproducibility, artifact completeness, protected-file boundaries, and exact exit-code recording.
- Task 2 is locally reviewed for the diagnosed type/build contracts and protected-file boundaries; `pnpm typecheck` and the approved escalated `pnpm build` both exited `0`.
- Task 3 is locally reviewed for provider boundaries, mock completeness, assertion intent, and the `bottomItems` production fix; focused and full unit verification exited `0`.
- No task is marked complete without fresh command evidence in this ledger.
