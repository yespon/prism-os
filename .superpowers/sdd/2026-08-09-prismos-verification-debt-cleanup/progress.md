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
- No task is marked complete without fresh command evidence in this ledger.
