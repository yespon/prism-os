# SDD ledger — plan: docs/superpowers/plans/2026-08-10-dependency-security-governance.md

## Status

- Task 1: complete
- Task 2: complete
- Task 3: complete
- Task 4: complete

Task 1 evidence:

- Frontend npm advisory scan via the official registry: 0 critical, 31 high,
  54 moderate, and 9 low in production; 0 critical, 54 high, 67 moderate,
  and 11 low across the complete dependency tree.
- The initial isolated `uvx` audit was rejected as an incomplete project
  context. The actual `uv sync --locked` environment contained 29 vulnerable
  distributions before remediation; the finding set is documented in the
  security report.
- GitHub's private Dependabot alert records remain unavailable without
  authentication; the local counts are documented as a separate evidence set.

Task 2 evidence:

- Frontend production audit after targeted upgrades: 0 critical, 0 high,
  0 moderate, and 0 low.
- Removed unused `nuxt-og-image` and its unpatched `image-size` dependency
  chain; upgraded `next`, `sharp`, `nanoid`, `@langchain/core`, `langsmith`,
  `postcss`, and `uuid` within compatible release lines.
- Backend runtime audit after `uv sync --locked`: 200 public-index
  distributions, no known vulnerabilities. The local editable
  `deerflow-harness` workspace package is explicitly excluded from the PyPI
  advisory mapping; its source and declared dependencies remain covered by
  tests and the lockfile. A separate cross-platform `uv export` scan is
  documented as a coverage signal and is not used as the shipped-runtime gate.

Task 3 evidence:

- Added weekly Dependabot coverage for frontend npm, backend pip/uv metadata,
  and GitHub Actions.
- Added pull-request, main-branch, weekly, and manual dependency-security
  workflow coverage for frontend, backend, and Compose checks.

Task 4 evidence so far:

- Updated the workflow to generate an editable-aware installed package list
  and run `pip-audit --disable-pip --no-deps` against that complete list.
- Updated the security report with the corrected backend baseline and
  remediation result.

Task 4 final evidence:

- Frontend frozen install, typecheck, production build, focused Vitest, and
  official-registry production audit passed; build emitted only the existing
  Turbopack NFT tracing warning.
- Backend locked sync, focused regression test, 120-test compatibility suite,
  and editable-aware runtime audit passed; the audit covered 200 public-index
  distributions and reported no known vulnerabilities.
- Docker Compose configuration validation, YAML parsing, and diff checks
  passed. The governance changes are ready to commit and push from the
  `codex/dependency-security-governance` branch.
