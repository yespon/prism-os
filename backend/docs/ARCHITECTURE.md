# Architecture Overview

## System Architecture

```
                              ┌─────────────────────┐
                              │   Browser / Client   │
                              └──────────┬──────────┘
                                         │
                              ┌──────────▼──────────┐
                              │   Nginx (Port 2026) │
                              │  Reverse Proxy       │
                              │  /api/langgraph/* → LangGraph (2024) │
                              │  /api/*           → Gateway (8001)   │
                              │  /*               → Frontend (3000)  │
                              └──┬────────────┬──┘
                                 │            │
                    ┌────────────▼──┐  ┌──────▼──────────┐
                    │ Gateway API   │  │ LangGraph Server │
                    │ (FastAPI:8001)│  │ (Port 2024)      │
                    └──┬───┬───┬───┘  └──────┬───────────┘
                       │   │   │             │
          ┌────────────┘   │   └───────┐     │
          ▼                ▼           ▼     ▼
    ┌──────────┐  ┌───────────────┐  ┌──────────────────────────┐
    │ Auth DB  │  │  Tenant DB    │  │  File / Object Storage   │
    │──────────│  │───────────────│  │──────────────────────────│
    │ Better   │  │  SQLModel     │  │  v1.0: Local FS          │
    │ Auth     │  │  SQLAlchemy   │  │  .prismos/threads/     │
    │ ──────── │  │  + Alembic    │  │  .prismos/data/        │
    │ user     │  │  ──────────   │  │                          │
    │ account  │  │  tenants      │  │  📋 v2.0: MinIO (S3)     │
    │ session  │  │  memberships  │  │  tn-{id}/ → per-tenant   │
    │          │  │  model_configs│  │  bucket isolation        │
    │          │  │  mcp_servers  │  │  user/ prefix scoping    │
    │          │  │  skills       │  │  quota at bucket level   │
    │          │  │  user_configs │  │  presigned URL access    │
    │          │  │  announcements│  │                          │
    └──────────┘  └───────────────┘  └──────────────────────────┘
```

> **Database layer** (left two) stores identity, configuration, and metadata — structured, queried via SQL. **File/Object storage** (right) stores thread artifacts, uploads, and agent workspace — blobs, accessed via filesystem or S3 API. v1.0 uses local FS; v2.0 introduces MinIO with per-tenant bucket isolation and user-level quotas. See [Storage Evolution](#storage-evolution) below.

## Core Components

### Gateway API (FastAPI, Port 8001)

Provides REST endpoints for management and non-agent operations. All business APIs pass through the Auth middleware which extracts user identity, tenant context, and role from the session token.

**Routers**:

| Router                | Prefix                                                                   | Purpose                                                              |
| --------------------- | ------------------------------------------------------------------------ | -------------------------------------------------------------------- |
| `admin`               | `GET /api/admin/*`                                                       | Platform admin: users, tenants, model templates, audit overview      |
| `tenants`             | `GET /api/tenants`                                                       | Tenant listing, current tenant, switch tenant                        |
| `agents`              | `GET /api/agents`                                                        | Custom agent CRUD (SOUL.md, tool\_groups, model binding)             |
| `models`              | `GET /api/models`                                                        | Available models from DB (per-tenant scope)                          |
| `mcp`                 | `GET /api/mcp/*`                                                         | MCP server configuration (per-tenant)                                |
| `skills`              | `GET /api/skills`                                                        | Skills management (per-tenant)                                       |
| `threads`             | `DELETE /api/threads/{id}`                                               | Thread cleanup after LangGraph deletion                              |
| `artifacts`           | `GET /api/threads/{id}/artifacts/*`                                      | Artifact serving and download                                        |
| `uploads`             | `POST /api/threads/{id}/uploads`                                         | File upload                                                          |
| `suggestions`         | `GET /api/threads/{id}/suggestions`                                      | Follow-up suggestions                                                |
| `memory`              | `GET /api/memory`                                                        | Memory management                                                    |
| `announcements`       | `GET /api/announcements`                                                 | Platform announcements                                               |
| `channels`            | `GET /api/channels`                                                      | IM channel management                                                |
| `auth` (Auth helpers) | `POST /api/auth/resolve-username` `POST /api/auth/setup-bootstrap-admin` | Unauthenticated endpoints for username login and initial admin setup |

### Auth Middleware

Every API request (except `/health`, `/docs`, and `/api/auth/resolve-username`, `/api/auth/setup-bootstrap-admin`) passes through `AuthMiddleware`. It:

1. Extracts the Better Auth session token from headers or cookies
2. Resolves `user_id`, `user_role`, and `must_change_password`
3. Determines the active tenant and membership role via `tenant_service`
4. Creates a personal tenant if the user has none (auto-bootstrap)
5. Injects tenant context into `contextvars` for transparent propagation to config loaders

### LangGraph Server (Port 2024)

The Agent runtime. Runs via `langgraph dev` (open-source CLI). Orchestrates sub-agents, manages thread state, executes tools in sandboxes, and streams responses via SSE.

**Entry Point**: `packages/harness/deerflow/agents/lead_agent/agent.py:make_lead_agent`

### Frontend (Next.js, Port 3000)

- Workspace sidebar: Overview, Smart Workbench, Agents, Announcements
- Platform admin (`/admin`): Users, Tenants, Models, Tools, Audit, Security, Announcements
- Tenant admin (`/tenant-admin`): Members, Models, Skills, Tools, Audit, Settings
- User settings dialog: Models, Memory, Tools, Skills, Appearance, Notifications

## Multi-Tenancy Architecture

### Three-Tier Resource Model

```
global (platform level)
  └── tenant (workspace level)
       ├── user-scoped resources (personal threads, memory)
       └── tenant-shared resources (models, skills, MCP)
```

### Database Tables (Tenant DB)

| Table                         | Purpose                                                               |
| ----------------------------- | --------------------------------------------------------------------- |
| `user_configs`                | Per-user runtime config (app\_config + extensions\_config JSON blobs) |
| `tenants`                     | Tenant containers (id, name, slug, status)                            |
| `tenant_memberships`          | User-to-tenant role bindings                                          |
| `tenant_model_configs`        | Models assigned to tenants                                            |
| `tenant_mcp_servers`          | MCP server configs per tenant                                         |
| `tenant_skills`               | Skill state per tenant                                                |
| `platform_announcements`      | Operational announcements with role/tenant targeting                  |
| `platform_announcement_reads` | Per-user read/dismiss state                                           |

### Auth DB (Better Auth)

Managed by Better Auth framework. Stores `user`, `account`, `session`, `verification` tables. The user table includes custom fields: `role`, `status`, `mustChangePassword`, `isBootstrapAdmin`.

### Config Loading: contextvars Transparent Proxy

User-scoped config is loaded through a `contextvars`-based proxy pattern:

1. `AuthMiddleware` sets `user_id`, `tenant_id`, and `tenant_role` into thread-local `contextvars`
2. `get_app_config()` checks `contextvars` for a current user
3. If a user is present: loads user-scoped config from DB (`user_configs` table), merges with platform-level model templates from `tenant_model_configs`
4. If no user (system startup): falls back to file-based `config.yaml`
5. Downstream code (`factory.py`, tool loaders) calls `get_app_config()` without knowing where the config came from

This means the core Agent runtime code (model factory, tool loading) was never modified for multi-tenancy.

## Storage Evolution

### v1.0: Local Filesystem (Current)

```
.prismos/
├── threads/
│   └── {thread_id}/
│       └── user-data/
│           ├── workspace/    ← Agent working directory
│           ├── uploads/      ← User-uploaded files
│           └── outputs/      ← Agent-generated artifacts
├── data/
│   ├── auth.db              ← Better Auth (user/account/session)
│   └── tenant.db            ← SQLModel tenant configs
└── audit/
    └── events.jsonl         ← Audit log
```

Simple, zero-dependency. Suitable for single-node deployment. All tenants share the same filesystem with path-based isolation.

### v2.0: MinIO Object Storage (Planned)

```
MinIO (S3-compatible)
├── tn-{tenant_a}/               ← Tenant A bucket
│   ├── user-{user_1}/           ← User-scoped prefix
│   │   ├── threads/{id}/workspace/
│   │   ├── threads/{id}/uploads/
│   │   └── artifacts/
│   ├── user-{user_2}/
│   │   └── ...
│   └── shared/                  ← Tenant-shared files
│       └── skills/
├── tn-{tenant_b}/               ← Tenant B bucket
│   └── ...
└── global/                      ← Platform-level assets
    └── skill-templates/
```

**Design principles:**

| Aspect               | Design                                                                                                                                                            |
| -------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Bucket namespace** | `tn-{tenant_id}` per tenant, guaranteed isolation                                                                                                                 |
| **User prefix**      | `user-{user_id}/` within tenant bucket, scoped to member                                                                                                          |
| **Quota**            | Tenant-level quota configured by platform admin. User-level sub-quota managed by tenant admin. Enforced at the MinIO bucket policy level                          |
| **Lifecycle**        | Auto-expire old thread artifacts after configurable retention period via MinIO lifecycle rules                                                                    |
| **Access control**   | MinIO IAM policies bound to tenant context. Gateway proxies requests with presigned URLs — never exposes MinIO directly to the browser                            |
| **Migration**        | Existing local filesystem data can be backfilled into MinIO via `mc mirror`. Both backends coexist during transition — `config.yaml` controls the storage backend |

**Data flow with MinIO:**

```
User uploads file
  → Gateway validates + extracts tenant/user context
  → Writes to MinIO: tn-{tenant}/user-{user}/uploads/{thread}/{file}
  → Stores metadata in tenant DB (file path, size, checksum)
  → Sandbox mounts object via MinIO FUSE or S3-backed path

Agent generates artifact
  → Sandbox writes to virtual path /mnt/user-data/outputs/
  → Sandbox teardown syncs outputs to MinIO
  → Artifact URL served via Gateway presigned GET
```

**Why MinIO:**

- S3-compatible API — easy migration to AWS S3, GCS, or any S3 backend
- Self-hosted — fits PrismOS's on-prem / private deployment positioning
- Per-tenant bucket isolation prevents cross-tenant data leakage at the storage layer (defense in depth, not just application-level)
- Quota enforcement at the storage layer prevents a single tenant from starving others
- Object versioning and lifecycle policies for compliance retention

**config.yaml (v2.0):**

```yaml
storage:
  backend: minio              # local | minio
  minio:
    endpoint: minio:9000
    access_key: $MINIO_ACCESS_KEY
    secret_key: $MINIO_SECRET_KEY
    use_ssl: false
    region: us-east-1
    default_tenant_quota_gb: 10
    artifact_retention_days: 90
```

## Agent Runtime (Inherited from DeerFlow)

### Lead Agent

Entry: `make_lead_agent(config)` in `packages/harness/deerflow/agents/lead_agent/agent.py`

Creates a LangGraph agent with:

- Model from the factory (DB-driven model selection)
- Tools filtered by agent's `tool_groups` whitelist
- Middleware chain for uploads, sandbox, summarization, memory, etc.
- Skills injected into system prompt

### Middleware Chain

| Order | Middleware              | Function                                |
| ----- | ----------------------- | --------------------------------------- |
| 1     | ThreadDataMiddleware    | Set up per-thread directories           |
| 2     | UploadsMiddleware       | Inject uploaded file list into messages |
| 3     | SandboxMiddleware       | Acquire sandbox environment             |
| 4     | SummarizationMiddleware | Context reduction near token limits     |
| 5     | TitleMiddleware         | Auto-generate conversation titles       |
| 6     | TodoListMiddleware      | Task tracking (plan mode)               |
| 7     | ViewImageMiddleware     | Vision model image processing           |
| 8     | ClarificationMiddleware | Handle user clarifications              |

### Sandbox System

```
SandboxProvider (abstract)
  ├── LocalSandboxProvider (development)
  └── AioSandboxProvider (Docker/K8s, production)
```

Virtual path mapping:

| Virtual Path               | Physical Path                      |
| -------------------------- | ---------------------------------- |
| `/mnt/user-data/workspace` | `threads/{id}/user-data/workspace` |
| `/mnt/user-data/uploads`   | `threads/{id}/user-data/uploads`   |
| `/mnt/user-data/outputs`   | `threads/{id}/user-data/outputs`   |
| `/mnt/skills`              | `skills/`                          |

### Tool System

Tools come from three sources merged at runtime:

- **Built-in tools**: `present_file`, `ask_clarification`, `view_image`
- **Configured tools** (from DB): `web_search`, `web_fetch`, `bash`, `read_file`, `write_file`, `str_replace`, `ls`
- **MCP tools** (from DB per-tenant): External servers via stdio/SSE/HTTP transports

Tool groups (`web`, `file:read`, `file:write`, `bash`) are used by custom agents for tool whitelisting.

## Configuration Flow

```
┌─────────────────────────────────────────────────────────┐
│ config.yaml (platform-level fallback only)               │
│  - Sandbox, Logging, Summarization, Tool Groups         │
│  - Database connection strings                           │
│  - Storage backend (local | minio)      -- v2.0          │
└───────────────────────┬─────────────────────────────────┘
                        │
                ┌───────▼───────┐
                │  Tenant DB     │
                │  ─────────────│
                │  Models        │ ← Platform/Tenant admin via UI
                │  MCP Servers   │
                │  Skills        │
                │  User Configs  │ ← Per-user runtime overrides
                └───────┬───────┘
                        │
                ┌───────▼───────┐
                │  contextvars   │
                │  Proxy Layer   │
                │  get_app_config│
                │  get_extensions│
                └───────┬───────┘
                        │
                ┌───────▼───────┐
                │  Agent Runtime │ (unchanged)
                │  factory.py    │
                │  tool loader   │
                │  skill loader  │
                └───────────────┘
```

## Deployment Model

### Philosophy

PrismOS targets both quick onboarding and production-grade operations. We support dual deployment paths — not an either/or choice.

| Environment                 | Deployment        | Target Audience                                  |
| --------------------------- | ----------------- | ------------------------------------------------ |
| **Dev / Try-out**           | Docker Compose    | Individual developers, single-command evaluation |
| **PoC / Small team**        | Docker Compose    | Internal pilot, single-node deployment           |
| **Production / Enterprise** | Helm + Kubernetes | HA, rolling updates, horizontal scaling          |

**Docker Compose is the v1.0 default** because it minimizes friction: `docker compose up -d` gets you running. As PrismOS matures toward v1.1, a Helm chart becomes the recommended production path.

### Configuration in Each Mode

| Aspect                     | Docker Compose                    | Helm + K8s                               |
| -------------------------- | --------------------------------- | ---------------------------------------- |
| Platform settings          | `config.yaml` (file mount)        | `values.yaml` → ConfigMap + Secret       |
| Model / MCP / Skill config | Database (unchanged across modes) | Database (unchanged)                     |
| Secrets                    | `.env` file                       | K8s Secret / External Secrets Operator   |
| Storage                    | Host volume bind                  | PVC / MinIO S3                           |
| Sandbox                    | Local or Docker socket mount      | Docker socket or K8s Pod via provisioner |

### Why Helm

- PrismOS comprises 5+ services (nginx, frontend, gateway, langgraph, db-init, optionally postgres, provisioner, MinIO). Helm templates make this manageable.
- `values.yaml` maps naturally to the current `config.yaml` structure — migration is straightforward.
- Enterprise buyers expect Helm. Offering it signals production readiness.
- Helm's `--set` and values file overrides enable per-environment customization (staging vs prod) without config drift.

