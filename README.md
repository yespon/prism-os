# PrismOS

[中文](./README_zh.md) | English

[![Python](https://img.shields.io/badge/Python-3.12%2B-3776AB?logo=python&logoColor=white)](./backend/pyproject.toml)
[![Node.js](https://img.shields.io/badge/Node.js-22%2B-339933?logo=node.js&logoColor=white)](./Makefile)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](./LICENSE)
[![Built on DeerFlow](https://img.shields.io/badge/Built_on-DeerFlow-8A2BE2)](https://github.com/bytedance/deer-flow)

PrismOS is a governed Agent operating system for enterprise teams. It provides
multi-tenant control, RBAC, model configuration, Skills, MCP integrations,
sandboxed execution, artifacts, and an extensible runtime foundation.

This repository is an early alpha. The product boundary is intentionally larger
than the current implementation: the foundation ships first, while policy,
workflow, evaluation, connector, and federation layers are developed over time.

> AI operations is a validation scenario for PrismOS, not a prerequisite for
> its core architecture. The platform must remain useful for other enterprise
> Agent scenarios without coupling it to an operations closed loop.

## Platform contract status

M1/P0 contract baseline implemented; governed execution is not yet complete.
See [Platform Contract Baseline](./backend/docs/PLATFORM_CONTRACTS.md) for the
frozen v1 boundary, migration guidance, verification evidence, and explicit
non-capabilities.

## Capability baseline

| Area | Current implementation |
| --- | --- |
| Multi-tenancy | User, tenant, and global scopes with tenant-aware storage |
| RBAC | Platform and tenant administration roles with protected routes |
| Model configuration | Database-backed provider configuration and tenant assignment |
| Skills | Scoped Skill management, editing, import, and sandbox testing |
| MCP | Tenant-scoped server configuration and health checks |
| Sandbox execution | Local, Docker, and optional Kubernetes provisioner modes |
| Artifacts and files | Uploads, thread files, generated artifacts, preview, and download |
| Administration | User/tenant management, announcements, audit views, and dashboards |
| Vertical plugins | Optional alerting, terminal, and asset capabilities |

The following are partial foundations, not complete platform contracts:

- Agent management, plugin SPI, and runtime abstraction
- A unified audit model across every execution and governance domain
- Production-grade isolation, policy enforcement, and lifecycle controls

## Architecture boundary

```text
Browser
  │
  ▼
Nginx :2026 ─────────────── unified local entry point
  ├── Frontend :3000       Next.js / React workspace and admin UI
  ├── Gateway :8001        PrismOS API, tenants, RBAC, models, Skills, MCP, files
  └── LangGraph :2024      Agent execution service
                                │
                                ├── DeerFlow-compatible harness
                                ├── LangGraph orchestration
                                └── sandbox, tools, memory, and artifacts
```

PrismOS currently uses the DeerFlow-compatible harness and LangGraph as its
execution foundation. The `deerflow` Python import path, existing API routes,
database tables, Alembic migrations, and user data paths are retained for
compatibility. This alpha is therefore a governed platform layer around an
existing Agent runtime, not an already-delivered independent runtime.

## Roadmap

The whitepaper is the long-term roadmap, ordered by platform dependency:

1. **Governance primitives** — policy model, authorization decisions, approvals,
   and a consistent audit/event contract.
2. **Execution lifecycle** — first-class Task and Run objects, state transitions,
   cancellation, retry, idempotency, and durable execution history.
3. **Workflow lifecycle** — versioned workflows, triggers, DAG execution,
   conditions, approvals, and Agent executor nodes.
4. **Evaluation and observability** — traceable evaluations, datasets, quality
   signals, cost attribution, and runtime metrics.
5. **Connectors and runtime independence** — integration contracts and a runtime
   abstraction that can evolve beyond the current DeerFlow/LangGraph dependency.
6. **Federation** — cross-organization discovery, trust, authorization, and
   policy-aware exchange after the foundations are stable.

Policy, Task/Run lifecycle, Workflow lifecycle, Evaluation, Connector
federation, runtime independence, and Federation are roadmap items. They are
not complete platform capabilities in this release.

## Quick start

See [QUICKSTART.md](./QUICKSTART.md) for the supported local path:

```bash
git clone https://github.com/yespon/prism-os.git
cd prism-os
make config
make up
curl http://localhost:2026/health
```

Open <http://localhost:2026>, complete bootstrap setup, and configure a model
from the admin UI. See [configuration](./backend/docs/CONFIGURATION.md) and
[contributing](./CONTRIBUTING.md) for advanced modes.

## Configuration and compatibility

New deployments use `PRISMOS_*` variables and default data under
`backend/.prismos`. Existing installations should follow the bounded
[PrismOS brand migration guide](./docs/migrations/prismos-brand-migration.md)
before changing their data path. Never commit populated `config.yaml`, `.env`,
API keys, credentials, or database passwords.

## Security and alpha limitations

Tenant-aware access controls, RBAC, audit views, and sandbox adapters do not
constitute a security certification. The default local filesystem sandbox runs
on the host and is not a production isolation promise. Docker and Kubernetes
modes require operator review of image provenance, privileges, network policy,
resource limits, secret handling, and host mounts.

This alpha does not promise a complete policy engine, Task/Run lifecycle,
workflow engine, evaluation system, connector federation, or independent Agent
runtime. Report security issues privately through [SECURITY.md](./SECURITY.md).

## Releases and containers

The first planned release is `v0.1.0-alpha.1`, a GitHub pre-release:

```text
ghcr.io/yespon/prism-os:v0.1.0-alpha.1
```

Use immutable version tags for review and deployment. The alpha line does not
create a `latest` tag. Local release notes are in [docs/releases](./docs/releases).

## Development checks

```bash
make check
make install
cd backend && uv run pytest --collect-only -q
cd ../frontend && pnpm check && pnpm test:unit
```

Report passed, skipped, and failed tests separately. A successful collection is
not the same as a fully passing suite.

## Documentation

- [5-minute Quick Start](./QUICKSTART.md) / [中文](./QUICKSTART_zh.md)
- [Architecture](./backend/docs/ARCHITECTURE.md)
- [Configuration](./backend/docs/CONFIGURATION.md)
- [API reference](./backend/docs/API.md)
- [Contributing](./CONTRIBUTING.md)
- [Security policy](./SECURITY.md)
- [Publishing design](./docs/superpowers/specs/2026-08-07-prismos-project-publishing-design.md)

## Contributing

PrismOS is maintained as an independent repository. Issues, design discussion,
documentation improvements, and focused pull requests are welcome from people
with project access. Read [CONTRIBUTING.md](./CONTRIBUTING.md) first.

## License and attribution

PrismOS is distributed under the [MIT License](./LICENSE). The current Agent
execution foundation includes [DeerFlow](https://github.com/bytedance/deer-flow)
and [LangGraph](https://github.com/langchain-ai/langgraph); their names and
links remain here for accurate attribution and technical context. Other major
components include [LangChain](https://github.com/langchain-ai/langchain) and
[Next.js](https://nextjs.org/).
