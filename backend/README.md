# PrismOS Platform

[中文](./README_zh.md) | English

[![Python](https://img.shields.io/badge/Python-3.12%2B-3776AB?logo=python&logoColor=white)](./backend/pyproject.toml)
[![Node.js](https://img.shields.io/badge/Node.js-22%2B-339933?logo=node.js&logoColor=white)](./Makefile)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](./LICENSE)
[![Built on DeerFlow](https://img.shields.io/badge/Built_on-DeerFlow-8A2BE2)](https://github.com/bytedance/deer-flow)

PrismOS is a **Governed Agent Platform** — the secure, multi-tenant foundation
for building and deploying your organization's digital workforce. v1.0 is built
on [DeerFlow](https://github.com/bytedance/deer-flow)'s Agent runtime (ByteDance,
GitHub Trending #1), with multi-tenancy, RBAC, audit logging, visual admin
dashboards, and database-driven configuration layered on top.

> **Our mission: enable every organization to safely create, deploy, and manage
> their own AI agents — governed, auditable, and production-ready.**

## Table of Contents

- [Platform Features](#platform-features)
- [Why PrismOS Exists](#why-prismos-exists)
- [v1.0 — What We Built](#v10--what-we-built)
- [Our Vision](#our-vision)
- [Roadmap](#roadmap)
- [Quick Start](#quick-start)
- [Supported Models](#supported-models)
- [Internationalization](#internationalization)
- [Documentation](#documentation)
- [Contributing](#contributing)
- [License](#license)
- [Acknowledgments](#acknowledgments)

## Platform Features

PrismOS transforms AI Agents into a governed production platform with the following capabilities:

### 🏠 Multi-Tenancy Workspace
A unified workspace with three-tier resource isolation (`user → tenant → global`). Each user gets a personal tenant on registration, and tenant admins manage members, models, tools, and skills independently.

**Modules:**
- **Overview** — Dashboard with key metrics and quick actions
- **Agent Gallery** — Browse and select AI agents for different tasks
- **Chat Workspace** — Conversational AI interface with artifact management
- **Skill Editor** — Create, edit, and test AI Skills with sandbox testing and AI-assisted instruction generation

### 🤖 Agent Capabilities

| Capability | Description |
|---|---|
| **Chat Agent** | Conversational AI with task decomposition, sub-agent parallelism, and artifact generation |
| **Skill System** | Reusable AI Skill templates with sandbox testing environment |
| **MCP Servers** | Configurable MCP servers per tenant (stdio/SSE/HTTP transports) |
| **Sandbox Execution** | Isolated code execution (local / Docker / Kubernetes modes) |

### 🔐 Security & Governance

| Feature | Description |
|---|---|
| **RBAC** | Three-tier roles: `platform_admin` / `tenant_admin` / `tenant_member` |
| **Audit Trail** | Full operation audit logging with per-tenant isolation |
| **User Management** | Status management (active / suspended), mandatory password rotation |

### 🌐 Platform Administration

| Dashboard | Scope |
|---|---|
| **Platform Admin** | Users, tenants, global audit, model templates, announcements |
| **Tenant Admin** | Members, models, tools, skills, MCP servers |

### 🎨 User Experience

- **4-Language i18n**: English, 中文, 日本語, 한국어
- **Model Provider Templates**: 20+ pre-configured providers with auto-filled settings
- **Docker One-Click Deploy**: `make up` to get everything running
- **Hot-Reload Dev Mode**: `make dev` for local development

---

## Why PrismOS Exists

### The Agent Gap

AI Agents can now plan, decompose tasks, execute code in isolated sandboxes,
and produce real deliverables. But there's a gap between a single-user Agent
and a platform ready for teams and organizations — governance, access control,
auditability, and lifecycle management.

### What We Built

PrismOS fills that gap. We layer governance on top of a proven Agent runtime:

| Concern | Without PrismOS | With PrismOS |
|---|---|---|
| **Team Collaboration** | Single-user mode | Multi-tenancy with `user → tenant → global` isolation |
| **Access Control** | No role-based permissions | RBAC with `platform_admin` / `tenant_admin` / `tenant_member` |
| **Model Configuration** | Hand-edited YAML files | 20+ provider templates in admin UI, database-backed, per-tenant assignment |
| **Administration** | Command-line scripts only | Visual admin dashboards for both platform and tenant levels |
| **Audit & Compliance** | No operation traceability | Full audit trail for all operations, per-tenant isolation |
| **Skills & MCP** | Functional runtime, manual setup | Per-tenant management via admin UI, lifecycle tracking |
| **Deployment** | Configuration-heavy, steep learning curve | Docker one-command deploy, admin UI-driven setup |

### Optional Vertical Plugins

The platform core is generic. Vertical capabilities — like alerting &
incident management, terminal governance, and asset management — ship as
optional plugins. Enable what you need, hide what you don't.

## v1.0 — What We Built

### Multi-Tenancy & RBAC

- **Three-tier resource isolation**: `user → tenant → global`, strict data separation
- **Two admin dashboards**: Platform admin (users, tenants, audit, model templates) + Tenant admin (members, models, tools, skills)
- **Auto-created personal tenant** on registration, zero manual setup
- Roles: `platform_admin` / `tenant_admin` / `tenant_member`

### Model Management, Done Right

- **20+ provider templates** in the admin UI — dropdown to select, auto-fills provider class, base URL, and capability flags. No LangChain class paths to memorize
- Models stored in database, assigned per-tenant, with active / deprecated / retired lifecycle
- Providers: OpenAI · Anthropic · DeepSeek · Azure OpenAI · Gemini · Ollama · OpenRouter · Groq · Together AI · SiliconFlow · DashScope · Zhipu · Moonshot · MiniMax · Baichuan · 01.AI · Volcengine Ark · Novita AI

### Skill System

- **Skill Editor**: Full-featured editor with Markdown instruction editing
- **AI-Assisted Generation**: Describe what you want, AI generates structured instructions
- **Sandbox Testing**: Test Skills in a safe mock environment before production use
- **Per-Tenant Management**: Skills scoped to personal, tenant, or global levels

### Audit & Security

- Full audit trail for all operations, per-tenant isolation
- User status management (active / suspended)
- Mandatory password change on first login

### Internationalization

- UI supports 4 languages: English, 中文, 日本語, 한국어
- Auto-detects browser language preference with manual switcher

### Deployment & Operations

- **Docker one-command deploy**: `docker compose up -d`
- Artifact management: browse, preview, download all agent-generated files
- Platform announcement system with tenant/role targeting

## Our Vision

PrismOS is not "DeerFlow with a dashboard." We're building a **secure, governed platform for your organization's digital workforce**.

On this platform, Agents don't just chat and generate code — they operate within boundaries: permission controls, audit records, execution approvals. Starting from Agent conversations, progressively extending into workflows, integrations, and observability, ultimately forming a complete chain:

> **Discover → Understand → Decide → Execute → Audit**

This space is almost entirely vacant in open source. That's why we need community voices.

**Who we're looking for**: If you work in engineering, security, compliance, or platform teams, and you're excited by AI Agents but can't use them in production because of missing governance and security — you're exactly who we're building for. Your pain points and suggestions are PrismOS's roadmap.

## Roadmap

```
✅ v1.0 (Current) — Governed Agent Platform
  ├─ Multi-tenancy + RBAC + Audit
  ├─ 20+ model provider templates, database-backed
  ├─ Visual admin dashboards (platform + tenant)
  ├─ Skill System with sandbox testing
  └─ Docker one-command deploy

🔜 v1.1 — Platform Slimming & Repositioning
  ├─ Plugin architecture: ops capabilities → optional plugins
  ├─ Plugin SPI definition (EventSource, Executor, Notifier)
  ├─ Narrative pivot: "AI-Native Operations" → "Governed Agent Platform"
  └─ tenant_type default: "ops" → "general"

🔜 v1.2 — Generic Workflow Engine
  ├─ Event source abstraction (webhook, cron, file change, message queue)
  ├─ Workflow orchestration (DAG, conditions, parallel, approval nodes)
  ├─ Agent as Executor node (Agent Runtime ↔ Workflow Engine coexistence)
  └─ Full audit closure

🔜 v1.3 — Digital Employee Framework
  ├─ Custom Agent: system_prompt templates, tool groups, skill binding, memory
  ├─ Agent lifecycle: Draft → Sandbox → Publish → Version → Retire
  ├─ Skill Marketplace Phase 1: Git import + official library + tenant sharing
  └─ AI Analysis Workbench: data → charts → reports/PPT

📋 v1.4 — Integration & Openness
  ├─ Open API (REST + Webhook)
  ├─ Third-party IM integration (Feishu, DingTalk, WeCom, Slack, Teams)
  ├─ SSO/LDAP
  └─ Multi-model routing

📋 v1.5 — Observability & Optimization
  ├─ Agent runtime metrics, workflow analytics
  ├─ A/B testing for prompts/models
  └─ Cost attribution (tenant/user/agent/workflow)

📋 v2.0 — Autonomous Runtime + Federated Ecosystem
  ├─ Self-developed Agent runtime (replace DeerFlow)
  ├─ Central Skill Registry
  ├─ Agent Federation (cross-org discovery, auth, billing)
  ├─ Low-code workflow designer
  └─ Edge deployment
```

## Quick Start

1. **Clone and configure**

   ```bash
   git clone https://github.com/yespon/prism-os.git
   cd prism-os
   make config
   ```

   Generates `config.yaml` with platform-level settings (database, sandbox, tool groups). **No model configuration needed.**

2. **Start and log in**

   ```bash
   make up
   ```

   Open http://localhost:2026. On first visit, you'll be redirected to the Setup Wizard to set your admin email and password.

   > You can also use `docker compose up -d`, but `make up` handles config initialization and secret generation automatically.

3. **Add models via admin UI**

   Log in as platform admin, go to **Settings → Models**, pick from 20+ provider templates, enter your API key.

   > Models are stored in the database. Do **not** configure models in `config.yaml` for production.

### Running Options

**Docker production**:
```bash
make up              # Build images and start all services (recommended for first deploy)
make up-nobuild      # Start services without rebuilding images
make down            # Stop and remove containers
make rebuild-images  # Remove all PrismOS images and rebuild from scratch
```

**Local development**:
```bash
make check           # Verify prerequisites (Node.js 22+, pnpm, uv, nginx)
make install         # Install dependencies
make dev             # Start dev servers (with hot-reload)
make stop            # Stop all services
```

**Docker development**:
```bash
make docker-init     # Pull sandbox image
make docker-start    # Start Docker dev services
make docker-stop     # Stop Docker dev services
make docker-logs     # View all logs
```

Access: http://localhost:2026

### China Users: Preparing Images

In China, pulling base images during Docker builds may fail due to network issues. Pre-pull before building:

```bash
# Required images
docker pull python:3.12-slim
docker pull node:22-alpine
docker pull nginx:alpine
docker pull docker:cli

# Build-stage dependency
docker pull ghcr.io/astral-sh/uv:0.9.26

# Optional images
docker pull postgres:16-alpine          # PostgreSQL mode
docker pull enterprise-public-cn-beijing.cr.volces.com/vefaas-public/all-in-one-sandbox:latest  # Sandbox
```

For mirror accelerator setup, see the [Quick Start Guide](QUICKSTART.md#china-users-preparing-images-for-local-builds).

### Advanced

#### Sandbox Mode

Three execution modes: Local / Docker containers / Docker + Kubernetes. See [Sandbox Guide](backend/docs/CONFIGURATION.md#sandbox).

#### MCP Server

Configurable MCP servers (managed per-tenant via admin UI). Supports stdio/SSE/HTTP transports with OAuth token flows.

## Supported Models

| Category | Providers |
|---|---|
| **Global Leaders** | OpenAI · Anthropic · DeepSeek · Azure OpenAI · Gemini |
| **Aggregators** | OpenRouter · Groq · Together AI |
| **Self-Hosted** | Ollama |
| **China-Based** | DashScope · Zhipu · Moonshot · MiniMax · Baichuan · 01.AI · Volcengine Ark · SiliconFlow |
| **Other** | Novita AI · Any OpenAI-compatible provider |


## Documentation

- [5-Minute Quick Start](QUICKSTART.md)
- [Configuration Guide](backend/docs/CONFIGURATION.md)
- [Architecture Overview](backend/docs/ARCHITECTURE.md)
- [API Reference](backend/docs/API.md)
- [Contributing Guide](CONTRIBUTING.md)

## Contributing

We welcome contributions — code, documentation, scenario suggestions, or real-world pain points. Open an Issue or PR.

## License

MIT License. See [LICENSE](./LICENSE).

## Acknowledgments

### DeerFlow

v1.0 is built on [DeerFlow](https://github.com/bytedance/deer-flow) (by ByteDance). DeerFlow's Agent runtime — LangGraph orchestration, sub-agent parallelism, sandboxed execution, persistent memory — is one of the best Agent infrastructures in open source. Deep gratitude to the DeerFlow team and community.

**Our relationship with DeerFlow**: In v1.x, we inherit DeerFlow's Agent runtime and add governance. As we evolve, we'll gradually replace internal dependencies and form our own architecture. PrismOS's long-term identity is not a DeerFlow fork — it's an independent, governed agent platform.

### Open-Source Community

- [LangChain](https://github.com/langchain-ai/langchain)
- [LangGraph](https://github.com/langchain-ai/langgraph)
- [Next.js](https://nextjs.org/)
