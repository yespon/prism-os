# Contributing to PrismOS

Thank you for helping shape PrismOS. This is an independent repository. Please
improve the platform foundation without turning a validation scenario into a
hidden architectural dependency.

## Before you start

Read the [README](./README.md), [architecture guide](./backend/docs/ARCHITECTURE.md),
and [security policy](./SECURITY.md). PrismOS is alpha software: mark unfinished
behavior as unfinished, preserve compatibility boundaries, and do not present
roadmap items as delivered capabilities.

Intentional boundaries:

- Keep the `deerflow` import path and LangGraph/DeerFlow adapter intact.
- Do not change existing API paths, database tables, or Alembic migrations as
  part of a branding or documentation change.
- Preserve existing data directories and compatibility environment variables.
- Keep AI operations optional as a validation scenario.
- Do not commit credentials, populated local configuration, runtime data, or
  generated dependency directories.

## Development environment

### Docker development

Prerequisites are Docker Desktop or Docker Engine with Compose v2, a working
Docker daemon, and pnpm if you want host cache optimization.

```bash
make config
make docker-init
make docker-start
```

The development entry point is <http://localhost:2026>:

```text
prismos-dev
  ├── nginx      :2026  reverse proxy
  ├── frontend   :3000  Next.js development server
  ├── gateway    :8001  FastAPI API gateway
  ├── langgraph  :2024  LangGraph server with DeerFlow-compatible harness
  └── provisioner:8002  optional Kubernetes sandbox provisioner
```

The provisioner is only needed for Kubernetes sandbox mode. Review
[docker/provisioner/README.md](./docker/provisioner/README.md) before enabling
it. On Linux, fix Docker daemon permissions on the host rather than weakening
container boundaries.

### Local development

```bash
make check
make install
make dev
```

The local stack uses Nginx on port 2026 and hot reload for frontend and backend.
For manual service control:

```bash
# LangGraph / Agent runtime
cd backend && make dev

# API gateway, in another terminal
cd backend && make gateway

# Frontend, in another terminal
cd frontend && pnpm dev
```

## Repository layout

```text
prism-os/
├── config.example.yaml       configuration template
├── scripts/                   bootstrap, environment, deployment, and checks
├── docker/                    Compose, Nginx, PostgreSQL, provisioner
├── backend/
│   ├── app/gateway/           PrismOS API gateway and management routes
│   ├── packages/harness/deerflow/
│   │                            DeerFlow-compatible Agent/LangGraph runtime
│   ├── alembic/               database migrations
│   └── tests/                 backend tests
├── frontend/                  Next.js / React application
├── skills/                    public and custom Skills
├── docs/                      release notes and design documents
└── .github/                   CI and issue templates
```

## Branches and pull requests

There is no required upstream fork or upstream remote. If you have repository
access:

```bash
git clone https://github.com/yespon/prism-os.git
cd prism-os
git checkout -b codex/short-description
```

Use a focused branch and pull request. Explain user-facing behavior,
compatibility impact, and verification evidence. For architectural work, link
the relevant whitepaper/design section and state whether the change is
implemented, partial, or roadmap-only.

Do not rewrite history, delete the legacy `b20c668` tag, remove runtime data, or
rename `deerflow` imports without an explicit migration design.

## Commit convention

Use [Conventional Commits](https://www.conventionalcommits.org/):

| Prefix | Use |
| --- | --- |
| `feat:` | User-visible capability |
| `fix:` | Bug fix |
| `refactor:` | Behavior-preserving structure change |
| `docs:` | Documentation only |
| `test:` | Test changes |
| `chore:` | Maintenance |
| `ci:` | Build or workflow changes |

## Verification checklist

Run relevant checks and report exact results in the pull request:

```bash
git diff --check
bash -n scripts/*.sh
docker compose config
docker compose -f docker/docker-compose.yaml config

cd backend
uv run pytest --collect-only -q
uv run pytest -q

cd ../frontend
pnpm check
pnpm test:unit
```

If a dependency is unavailable or the full suite contains pre-existing failures,
state that explicitly with counts. Successful collection is not the same as a
fully passing suite.

## Documentation and API changes

Public documentation must use PrismOS and the canonical URL
`https://github.com/yespon/prism-os`. Keep real upstream references for
DeerFlow, LangGraph, and other dependencies. Update English and Chinese public
docs together when behavior changes.

Existing gateway routes are part of the alpha compatibility surface. Prefer
additive changes, preserve response fields, and update API docs and tests when a
route genuinely changes.

## License

By contributing, you agree that contributions are licensed under the
[MIT License](./LICENSE), subject to existing attribution and third-party
license obligations.
