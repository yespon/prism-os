# Dependency Security Governance Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Establish an evidence-based dependency security baseline, remediate actionable high-risk findings without uncontrolled major upgrades, and make future dependency risk visible through repository automation.

**Architecture:** Preserve the existing `frontend` pnpm lockfile and `backend` uv workspace as sources of truth. Collect local advisory evidence first, classify production reachability, then update only confirmed vulnerable packages. Add Dependabot, a scheduled security workflow, and operating guidance.

**Tech Stack:** pnpm 10, Next.js/TypeScript, Python 3.12+, uv workspace, pip-audit, GitHub Actions, Docker Compose.

## Global Constraints

- Preserve `frontend/pnpm-lock.yaml` and `backend/uv.lock`; CI installs must remain frozen/locked.
- Do not perform broad refreshes or major upgrades unless a confirmed vulnerability has no compatible non-major fix.
- Prioritize critical/high findings with a patched release, production dependencies, and direct dependencies.
- Every dependency change requires locked install, focused tests, frontend typecheck/build, and Compose validation as applicable.
- Do not present GitHub’s aggregate `221 vulnerabilities` as locally reproduced; private Dependabot details require unavailable authentication.
- Do not add a CI security tool unless its installation, command, output, and failure behavior are executable here.

---

### Task 1: Capture the security baseline

**Files:**
- Create: `docs/security/dependency-management.md`
- Inspect: `frontend/package.json`, `frontend/pnpm-lock.yaml`, `backend/pyproject.toml`, `backend/uv.lock`, `.github/workflows/*.yml`

**Interfaces:**
- Consumes: current manifests, lockfiles, CI conventions, and local audit tooling.
- Produces: dated advisory records with package, installed version, severity, patched version, scope, and limitations.

- [x] **Step 1: Verify the branch is clean**

Run:

```bash
git status --short --branch
git diff --exit-code
```

Expected: `codex/dependency-security-governance`, no changes.

- [x] **Step 2: Audit frontend dependencies**

Run from `frontend`:

```bash
pnpm audit --prod --json
pnpm audit --json
```

Record package, installed range, severity, patched range, and production/development scope.

- [x] **Step 3: Audit backend dependencies**

Check tooling:

```bash
command -v pip-audit || true
python3 -m pip_audit --version 2>/dev/null || true
uv tool list 2>/dev/null || true
```

Use an existing `pip-audit --strict --format=json` executable from `backend`; otherwise use `uvx pip-audit --strict --format=json` only when it does not alter project environments. Record exact network/tooling limitations if it cannot run.

- [x] **Step 4: Write the baseline report**

In `docs/security/dependency-management.md`, record commands, results, residual findings, and this boundary: GitHub reported 221 vulnerabilities (86 high, 106 moderate, 29 low), but `gh` and GitHub credentials are unavailable, so private-repository alert details cannot be retrieved and local results are not an exact substitute.

### Task 2: Remediate confirmed findings

**Files:**
- Modify: `frontend/package.json` and `frontend/pnpm-lock.yaml` only for confirmed frontend fixes
- Modify: `backend/pyproject.toml` and `backend/uv.lock` only for confirmed backend fixes
- Modify: `docs/security/dependency-management.md`

**Interfaces:**
- Consumes: Task 1 advisory records.
- Produces: minimal compatible fixes or documented residual risk.

- [x] **Step 1: Classify each advisory**

Mark it production/direct, production/transitive, development-only, unreachable in the shipped image, or unresolved because source details are unavailable. Upgrade only a known patched version with a compatible path.

- [x] **Step 2: Apply targeted updates**

Use package-manager targeted update commands, preserving current package-manager majors and workspace constraints. Never use an unconstrained full update.

- [x] **Step 3: Verify lockfile reproducibility and rescan**

Run:

```bash
cd frontend && pnpm install --frozen-lockfile
cd ../backend && uv sync --locked
```

Re-run the affected ecosystem audit and document before/after severity plus deferred items.

- [x] **Step 4: Run focused regression checks**

Run:

```bash
cd frontend && pnpm typecheck
cd frontend && pnpm build
cd frontend && pnpm exec vitest run src/core/config/index.test.ts src/app/setup/page.test.tsx
cd backend && PYTHONPATH=. uv run pytest tests/test_frontend_docker_config.py -q
```

### Task 3: Add continuous governance

**Files:**
- Create: `.github/dependabot.yml`
- Create: `.github/workflows/dependency-security.yml`
- Modify: `docs/security/dependency-management.md`

**Interfaces:**
- Consumes: validated commands and existing workspace locations.
- Produces: weekly update proposals and deterministic push/PR/scheduled security checks.

- [x] **Step 1: Configure Dependabot**

Add weekly version-2 entries for `npm` `/frontend`, `pip` `/backend`, and `github-actions` `/`, each with five open PRs and security-update grouping where supported.

- [x] **Step 2: Add the security workflow**

Trigger on pull requests, pushes to `main`, and a weekly schedule. Check out; install pinned Node/pnpm; run frontend frozen install and `pnpm audit --prod --audit-level=high`; install uv using the existing action; run `uv sync --locked`; run the validated backend audit deterministically; and validate `docker compose -f docker/docker-compose.yaml config --quiet`. Do not silently skip backend coverage.

- [x] **Step 3: Document failure handling**

State that non-zero security checks block merges, Dependabot PRs use the same build/test gates, and residual advisories require an owner, rationale, and reassessment trigger.

### Task 4: Verify and deliver

**Files:**
- Inspect: all files changed by Tasks 1–3

**Interfaces:**
- Consumes: complete governance branch.
- Produces: verified commit ready to push with audit and residual-risk summary.

- [x] **Step 1: Validate configuration and diff**

Run:

```bash
git diff --check
docker compose -f docker/docker-compose.yaml config --quiet
git status --short
git diff --stat
```

- [x] **Step 2: Run fresh frontend and backend gates**

Run:

```bash
cd frontend && pnpm install --frozen-lockfile && pnpm typecheck && pnpm build && pnpm exec vitest run src/core/config/index.test.ts src/app/setup/page.test.tsx
cd ../backend && uv sync --locked && PYTHONPATH=. uv run pytest tests/test_frontend_docker_config.py -q
```

- [x] **Step 3: Review and commit only planned changes**

Inspect `git diff` and commit:

```bash
git add .github/dependabot.yml .github/workflows/dependency-security.yml docs/security/dependency-management.md docs/superpowers/plans/2026-08-10-dependency-security-governance.md frontend/package.json frontend/pnpm-lock.yaml backend/pyproject.toml backend/uv.lock
git commit -m "chore: establish dependency security governance"
```

- [x] **Step 4: Push after fresh verification**

Run:

```bash
git status --short --branch
git push -u origin codex/dependency-security-governance
```

Final reporting must state exact commit, audit results, remaining advisories, tests/build output, and GitHub-authentication limitations. Do not claim all GitHub findings are resolved without authenticated alert data.

## Self-Review Checklist

- [x] Baseline, remediation, lockfile discipline, automation, Dependabot, verification, and delivery gates are covered.
- [x] No `TBD`, `TODO`, or “fill in details” placeholders.
- [x] Paths and commands match the current frontend/backend workspace layout.
- [x] Local audit evidence is explicitly separated from unavailable private GitHub alert details.
