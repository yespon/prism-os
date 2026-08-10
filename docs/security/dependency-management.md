# Dependency Security Management

## Baseline

This document records the dependency-security baseline and remediation for
PrismOS on 2026-08-10.

| Field | Value |
| --- | --- |
| Repository | `yespon/prism-os` |
| Branch | `codex/dependency-security-governance` |
| Frontend manifest | `frontend/package.json` |
| Frontend lockfile | `frontend/pnpm-lock.yaml` |
| Backend manifests | `backend/pyproject.toml`, `backend/packages/harness/pyproject.toml` |
| Backend lockfile | `backend/uv.lock` |
| Package managers | pnpm 10.26.2; uv 0.6.11 locally |

The lockfiles remain the source of truth. Dependency changes must update the
corresponding manifest and lockfile together, and CI must continue to use
`pnpm install --frozen-lockfile` and `uv sync --locked`.

## Evidence collected

### Frontend

The repository's configured npm registry is `https://registry.npmmirror.com`.
Its npm audit endpoint is unavailable:

```text
ERR_PNPM_AUDIT_ENDPOINT_NOT_EXISTS
The audit endpoint at https://registry.npmmirror.com/-/npm/v1/security/audits doesn't exist.
```

Therefore the audit was repeated against the npm advisory service explicitly:

```bash
cd frontend
pnpm audit --registry=https://registry.npmjs.org --prod --json
pnpm audit --registry=https://registry.npmjs.org --json
```

The initial results were:

| Scope | Dependencies | Critical | High | Moderate | Low | Advisory records |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Production | 787 | 0 | 31 | 54 | 9 | 87 |
| Complete tree | 1,157 | 0 | 54 | 67 | 11 | 121 |

The audit command exits with status 1 when advisories are present; that is
expected and is not evidence of an audit-tool failure.

The principal production-scope high findings were:

| Package | Reachability | Installed version | Patched floor reported by npm | Initial disposition |
| --- | --- | --- | --- | --- |
| `next` | Direct | 16.1.7 | 16.2.11 for the most restrictive advisory | Targeted same-line upgrade and build verification |
| `sharp` | Via `next` | 0.34.5 | 0.35.0 | Expected to move with the Next.js upgrade; verify lockfile |
| `nanoid` | Direct | 5.1.6 | 5.1.16 | Targeted patch upgrade |
| `nanoid` | Via `next > postcss` | 3.3.11 | 3.3.17 | Resolved through patched PostCSS/Next dependency graph |
| `postcss` | Via Next.js and tooling | 8.4.31 / 8.5.x | 8.5.18 for the most restrictive advisory | Targeted compatible update; verify all paths |
| `langsmith` | Via `@langchain/core` | 0.5.2 | 0.6.0 | Upgrade the compatible LangChain core line and test imports |
| `lodash-es` | Via `streamdown > mermaid` | 4.17.21 / 4.17.23 | 4.18.0 | Re-evaluate after the markdown/diagram dependency graph update |
| `nuxt-og-image` chain | Direct but unused | `image-size` 2.0.2 | No patched version reported | Remove the unused package rather than override an unpatched transitive dependency |

`nuxt-og-image` has no source import in the frontend. It is a Nuxt-oriented
package in this Next.js application, and its dependency chain introduces
`image-size`, for which npm reported no patched version. Its removal is the
preferred remediation unless a real product requirement is identified.

### Backend baseline

The first backend scan used an isolated `uvx` environment and incorrectly
reported only the tool's own project context. A validation pass against the
actual environment after `uv sync --locked` found 119 advisory records in the
installed dependency closure before remediation. That closure contained 29
vulnerable distributions, including `cryptography`, `langchain`, `starlette`,
`pygments`, and `pytest`.

The auditable runtime list is generated from installed distribution metadata,
with the local editable workspace package `deerflow-harness` excluded because
it is not a PyPI distribution:

```bash
cd backend
uv sync --locked
uv run python - <<'PY'
import importlib.metadata as metadata
from pathlib import Path

excluded = {"deerflow-harness"}
packages = []
for distribution in metadata.distributions():
    name = distribution.metadata.get("Name")
    if name and name.lower() not in excluded:
        packages.append(f"{name}=={distribution.version}")
Path("/tmp/prismos-backend-installed.txt").write_text(
    "\n".join(sorted(set(packages))) + "\n"
)
PY
uv run --with pip-audit pip-audit \
  --strict --disable-pip --no-deps --progress-spinner off --format=json \
  -r /tmp/prismos-backend-installed.txt
```

After remediation, the scan covers 200 public-index distributions and reports:

```text
No known vulnerabilities found
```

The scan boundary is intentional: code in `deerflow-harness` is covered by the
repository's source review, tests, and its declared/locked dependencies, while
the package itself cannot be mapped to a public advisory database as an
editable local distribution.

An earlier `uv export` experiment expanded the lock into cross-platform and
optional dependency records and returned advisory records for packages that
were not installed in the shipped backend runtime. It is retained as a
coverage signal, not as the shipped-runtime finding count. The blocking
workflow now audits the environment after `uv sync --locked`, using the same
editable-aware requirements-list procedure documented above.

### Remediation result

The frontend changes were deliberately limited to compatible patched releases:

| Change | Result |
| --- | --- |
| `next` | `16.1.7` → `16.2.11` |
| `sharp` via `next` | `0.34.5` → `0.35.3` |
| `nanoid` | `5.1.6` → `5.1.16` |
| `@langchain/core` / `langsmith` | `1.1.x` / `0.5.2` → `1.2.5` / `0.6.0` |
| `postcss` | pinned to `8.5.23`, including the Next.js path |
| `uuid` | `13.0.0` → `13.0.1` |
| unused `nuxt-og-image` | removed, including its unpatched `image-size` chain |

The post-remediation production audit against the official npm registry is:

```text
0 critical / 0 high / 0 moderate / 0 low
```

The complete development tree was not used as the merge gate because the
reported objective is shipped production risk; it remains available as a
diagnostic scan. The exact private GitHub alert list still requires an
authenticated Dependabot review.

The backend remediation remains within the current Python 3.12+ service
contract while moving the LangGraph runtime to its compatible maintained line:

| Change | Result |
| --- | --- |
| `fastapi` / `starlette` | `0.128.0` / `0.50.0` → `0.141.1` / `1.6.0` |
| `langchain` | `1.2.10` → `1.3.14` (修复线 `>=1.3.9`) |
| `langgraph` | `1.0.10` → `1.2.10` |
| `langgraph-api` / CLI / in-memory runtime | `0.7.65` / `0.4.14` / `0.26.0` → `0.12.2` / `0.4.31` / `0.32.2` |
| `cryptography` | `46.0.7` → `50.0.0` |
| `pygments` / `pytest` | `2.19.2` / `9.0.2` → `2.20.0` / `9.1.1` |

The post-remediation backend scan reports zero known vulnerabilities. Because
the LangGraph runtime update crosses several minor releases, import checks,
focused backend tests, and the Docker Compose configuration check are required
merge gates for this change.

## GitHub alert boundary

GitHub previously displayed an aggregate count of 221 vulnerabilities: 86 high,
106 moderate, and 29 low. The exact Dependabot alert records could not be
retrieved during this baseline because the GitHub CLI is unavailable and no
`GITHUB_TOKEN` or `GH_TOKEN` is present. Unauthenticated API access to this
private repository returned 404.

The GitHub aggregate and the local npm/pip-audit results are different evidence
sets. The local counts above do not reproduce or dismiss the GitHub count, and
this document does not claim that all GitHub alerts are resolved. Once an
authenticated GitHub review is available, each remaining alert must be mapped
to a locked package path and disposition.

## Remediation rules

1. Address critical and high advisories first, prioritizing direct and shipped
   production dependencies.
2. Prefer the smallest compatible release that reaches the reported patched
   floor; do not run an unconstrained `pnpm audit --fix`.
3. Do not use a blanket override to suppress an advisory with no patched
   release. Remove the unused dependency or isolate the affected feature.
4. Every update requires a frozen install, frontend typecheck, production build,
   focused unit tests, backend lock verification, and Compose validation.
5. A dependency may remain temporarily when it is development-only or
   unreachable in the shipped image, but the reason, owner, and reassessment
   trigger must be recorded here.

## Continuous controls

Dependabot is configured for the frontend npm tree, the uv-managed backend,
and GitHub Actions. The repository security workflow runs on pull requests,
pushes to `main`, a weekly schedule, and manual dispatch. It covers locked
frontend installation and production audit, frontend typechecking, locked
backend installation, editable-aware runtime audit, a backend regression test,
and Compose configuration. Security checks fail on unresolved high-severity
production findings unless a documented exception is explicitly approved.

## Residual risk policy

Residual advisories are not silently ignored. Each exception must state the
affected package path, whether it is production-reachable, exploitability in
the PrismOS deployment model, the compensating control, an owner, and a date or
event that triggers reassessment. A new upstream release, a change in feature
reachability, or an authenticated Dependabot review reopens the exception.
