# Governed Agent Platform — Roadmap Design (v2)

> **Legacy / Historical:** This document records an earlier project state and may contain superseded product names or compatibility decisions.

**Date**: 2026-07-23
**Status**: Approved
**Authors**: yespon, Claude
**Previous**: [v1](./2026-07-19-governed-agent-platform-roadmap-design.md)

---

## 1. Positioning & Principles

### 1.1 Platform Positioning

**Governed Agent Platform** — enabling any organization to securely create, deploy, and manage its own digital workforce.

### 1.2 Core Principles

| Principle | Description |
|-----------|-------------|
| **Governance First** | RBAC, audit, model control, and runtime policy enforcement are the platform foundation, not add-ons |
| **Plugin Architecture** | Vertical capabilities are pluggable "scenario packs"; the platform core remains generic. Plugins are first-class citizens with defined SPIs. |
| **Dual-Track Users** | Serves both bottom-up individual productivity and top-down enterprise provisioning |
| **Context Engineering** | Context determines agent capability ceiling. Prompt templates, compression, window management, and retrieval strategies are platform-level concerns, not per-agent hacks. |
| **Harness over Model** | Engineering around the model (tools, context, memory, evaluation) outlasts any single model generation. The harness is the moat. |
| **Open Evolution** | From single-organization governance to cross-organization federation, gradually expanding trust boundaries. Governance capabilities should be open-sourced to build community trust. |

### 1.3 Strategic Pivot

v1.1 completed the "de-ops" transition. v1.2–v1.3 build generic automation, data connectivity, and multi-agent collaboration. v1.4 reinforces enterprise security. v1.4.5 introduces context engineering as a platform layer. v1.5 adds evaluation and feedback loops. v2.0 achieves architectural independence and federation.

### 1.4 Industry Context

The platform is informed by analysis of multiple industry frameworks:

| Source | Key Insight Adopted |
|--------|-------------------|
| NVIDIA Enterprise AI Factory | Two-phase security model (perimeter + runtime), short-lived capability tokens, GitOps-driven agent config |
| Google Gemini Managed Agents | Dual-plane API (Control Plane / Data Plane), A2A protocol, four-tier stack |
| LangChain Governed Agents | Hard budget caps with automatic circuit breakers |
| Microsoft Agent Governance Toolkit | Governance as open-source community leverage |
| AI Agent Book (bojieli) | Agent = LLM + Context + Tools; Harness engineering is the core competency |
| Alibaba Cloud 2025 AI Architecture | Evaluation framework as full-lifecycle capability; data flywheel |

---

## 2. Version Planning

### v1.0 — Governed Agent Platform (Current)

```
✅ Multi-tenancy + RBAC + Audit
✅ 20+ model provider templates, database-backed
✅ Visual admin dashboards (platform + tenant)
✅ Skill System with sandbox testing
✅ Docker one-command deploy
```

### v1.1 — Platform Slimming & Repositioning (Completed)

| Scope | Content |
|-------|---------|
| Architecture Decoupling | Alerting pipeline, terminal governance, asset management → optional plugins |
| Interface Definition | Plugin SPIs: `EventSource`, `Executor`, `Notifier` |
| Narrative Rewrite | "AI-Native Operations" → "Governed Agent Platform" |
| tenant_type Rename | Default "ops" → "general" |
| Plugin API | `GET /api/plugins` endpoint; frontend `usePlugins()` hook; nav filtering |

### v1.2 — Generic Workflow Engine

| Scope | Content |
|-------|---------|
| Event Source Abstraction | Webhook / Scheduled / File change / Message queue (Kafka/RabbitMQ interface reserved) |
| Workflow Orchestration | DAG steps, conditional branches, parallel/serial, human approval nodes, retry/timeout |
| Executor Interface | Agent dialogue / Code sandbox / HTTP call / Terminal (as plugin executor) |
| Audit Closure | Event → Workflow → Execution → Result, full-chain traceable and replayable |
| Built-in Templates | Scheduled reports, data sync, multi-Agent collaboration |

**Key clarification — Agent Runtime vs Workflow Engine coexistence:**

| Aspect | Agent Runtime | Workflow Engine |
|--------|---------------|-----------------|
| Role | "Employee" — single Agent's brain | "Project Manager" — cross-system orchestration |
| Duration | Minutes to hours | Hours to days |
| State | In-memory (LangGraph checkpoint) | Database persistent, recoverable |
| Human Intervention | In-conversation | Async approval nodes, suspend/resume |
| Cross-System | None | Saga pattern, compensating rollback |
| Audit | Single conversation | Full-chain, replayable |

```
Workflow: Trigger → Step1(HTTP) → Step2(Agent) → Step3(Approve) → Step4(Agent) → Done
                              │                  │                 │
                              ▼                  ▼                 ▼
                         Agent Runtime      Human waits        Agent Runtime
                         (inference+tools)  (hours/days)      (inference+tools)
```

The relationship is NOT competitive — it is complementary. The Workflow Engine calls Agent Runtime as one of its executor types. If the Agent process crashes, the Workflow reschedules it. If the Workflow process crashes, it recovers from database state.

### v1.3 — Digital Employee Framework + Data Connectivity

| Scope | Content |
|-------|---------|
| Custom Agent Enhancement | system_prompt templating (variable injection) + tool group whitelisting + skill binding + memory policy configuration |
| Agent Lifecycle | Draft → Sandbox test → Publish → Version management → Usage statistics → Retirement |
| Agent-to-Agent (A2A) Protocol | Intra-tenant Agent discovery, capability advertisement, and direct invocation |
| Multi-Agent Collaboration | Sequential (pipeline), Parallel (fan-out), Debate (multi-perspective) modes |
| Skill Marketplace Phase 1 | Git repository import + Official skill library + Tenant-internal sharing |
| AI Analysis Workbench | Data connection → Chart generation → Report/PPT export |
| **Data Connector Layer** | **Structured + Unstructured data access for Agents** |
| Admin Perspective | Agent provisioning, usage statistics, cost control, permission approval |

**Data Connector Layer (new in v1.3):**

```
┌─────────────────────────────────────────────────────────────┐
│                    Data Connector Layer                      │
│                                                             │
│  Unstructured Data              Structured Data              │
│  ├─ Document ingestion          ├─ DB connectors             │
│  │  (PDF/Word/Markdown/HTML)    │  (MySQL/PG/ClickHouse/     │
│  ├─ Chunking + Embedding        │   SQLite)                  │
│  ├─ Vector store (per-tenant)   ├─ API data sources          │
│  ├─ RAG retrieval pipeline      │  (REST/GraphQL, declarative│
│  │  (semantic + keyword hybrid  │   config)                  │
│  │   + reranking)               ├─ Data catalog              │
│  ├─ Knowledge base management   │  (schema discovery, samples)│
│  │  (tenant-isolated, ACL)      ├─ Text-to-SQL pipeline      │
│  └─ Context injection strategy  │  (NL → SQL → result → ctx) │
│     (prepend/append/dynamic)    └─ Structured result fmt      │
└─────────────────────────────────────────────────────────────┘
```

Data connectors are implemented as a **plugin type**, extending the Executor SPI. Each connector is tenant-configurable. Vector stores are infrastructure-level (per-tenant isolation). The RAG pipeline is a platform service, not a per-agent implementation.

### v1.4 — Integration & Enterprise Security

| Scope | Content |
|-------|---------|
| Open API | REST + Webhook: Agent dialogue, workflow trigger, result query; rate limiting, API key management |
| Third-Party Integration | Feishu/DingTalk/WeCom/Slack/Teams bidirectional |
| SSO/LDAP | Enterprise identity integration, auto-sync org structure to tenants/roles |
| Multi-Model Routing | Auto-select model by task type/cost/latency |
| **Runtime Security** | **Agent workspace isolation, network policy, capability tokens, runtime policy enforcement** |
| **Declarative Agent Config** | **Agent as Code (YAML/JSON), GitOps-friendly, version-controlled** |

**Runtime Security (new in v1.4):**

Building on v1.0's perimeter security (RBAC + audit), v1.4 adds runtime security:

| Layer | Capability | Status |
|-------|-----------|--------|
| Perimeter (v1.0) | RBAC, audit trail, user auth, password rotation | Done |
| Runtime (v1.4) | Agent workspace isolation (sandbox per tenant) | New |
| Runtime (v1.4) | Network policy (default-deny outbound, allowlist) | New |
| Runtime (v1.4) | Short-lived capability tokens (Agent never sees raw API keys) | New |
| Runtime (v1.4) | Pre-execution policy check (verify permissions before every tool call) | New |
| Runtime (v1.4) | Unified event output (OCSF-compatible for SIEM integration) | New |

This follows NVIDIA's two-phase enterprise security model, adapted for a self-hosted platform.

### v1.4.5 — Context Engineering (New Version)

| Scope | Content |
|-------|---------|
| Prompt Template System | Variable injection, version management, A/B branching, per-tenant defaults |
| Context Window Management | Token budget visualization, overflow warnings, automatic truncation strategies |
| Context Compression | Summarization, sliding window, semantic pruning |
| Memory Strategy | Short-term (session), long-term (persistent), semantic (vector retrieval) — configurable per agent |
| Cross-Session Continuity | "Continue from last conversation" — context inheritance with decay |
| Retrieval Formatting | Structured results → Markdown table / JSON / natural language, configurable formatting |

**Rationale:** "Context determines the ceiling of agent capability" (AI Agent Book). Context engineering is a long-term investment that survives model generation changes. It is a platform-level concern, not a per-agent implementation detail.

### v1.5 — Observability, Evaluation & Optimization

| Scope | Content |
|-------|---------|
| Agent Runtime Metrics | Success rate, latency, token consumption, user satisfaction |
| Workflow Analytics | Bottleneck identification, failure hotspots, optimization suggestions |
| **Evaluation Framework** | **Offline eval (test suites), online eval (production sampling), human annotation pipeline** |
| **Feedback Loop** | **User rating → auto sample collection → prompt/model iteration** |
| A/B Testing | Compare different prompts/models/processes, data-driven iteration |
| Cost Attribution | Tenant/user/agent/workflow four-level cost allocation, budget alerts with auto circuit-breaker |

**Evaluation Framework (enhanced in v1.5):**

Following the Alibaba Cloud 2025 AI Architecture's emphasis on evaluation as a full-lifecycle capability:

```
┌──────────────────────────────────────────────┐
│              Evaluation Pipeline              │
│                                              │
│  Offline                  Online             │
│  ├─ Test suites           ├─ Production      │
│  │  (scenario-based)      │   sampling       │
│  ├─ Golden dataset        ├─ User ratings    │
│  ├─ Regression checks     ├─ Anomaly detect  │
│  └─ Model comparison      └─ Drift monitor   │
│                                              │
│  Human Annotation                            │
│  ├─ Side-by-side comparison                  │
│  ├─ Rubric-based scoring                     │
│  └─ Edge case collection                     │
│                                              │
│  Data Flywheel                               │
│  Feedback → Samples → Retrain/Refine → Deploy│
└──────────────────────────────────────────────┘
```

### v2.0 — Autonomous Runtime + Federation + Open Source

| Scope | Content |
|-------|---------|
| Autonomous Agent Runtime | Replace DeerFlow dependency, full control of orchestration, state management, checkpoints |
| Central Skill Registry | Cross-tenant/cross-organization skill sharing and trading (npm-like, enterprise-grade permissions) |
| Agent Federation | Cross-organization Agent interoperability: discovery, auth, permission boundaries, billing, versioning |
| Low-Code Workflow Designer | Visual orchestration for non-technical users (drag-and-drop nodes, parameter configuration) |
| **Open Governance Toolkit** | **RBAC, audit, cost, and policy enforcement capabilities released as standalone open-source libraries** |
| Edge Deployment | Lightweight runtime deployed to customer environments, data stays on-premises, cloud unified management |

**Open Governance Toolkit (new in v2.0):**

Following Microsoft's Agent Governance Toolkit precedent, releasing governance capabilities as open-source libraries:
- Builds community trust and adoption
- Enables integration with other agent frameworks
- Positions OpsinTech as a governance standard, not just a platform

---

## 3. Technical Architecture

### 3.1 Layered Architecture (Updated)

```
┌──────────────────────────────────────────────────────────┐
│  Access Layer     │ Web Console │ Open API │ IM Bot │ A2A│
├──────────────────────────────────────────────────────────┤
│  Context Layer    │ Prompt Templates │ Window Mgmt        │
│                   │ Compression      │ Memory Strategy    │
├──────────────────────────────────────────────────────────┤
│  Core Layer       │ Agent Runtime │ Workflow Engine      │
│                   │ Skill System  │ Model Router         │
├──────────────────────────────────────────────────────────┤
│  Data Layer       │ RAG Pipeline  │ DB Connectors        │
│                   │ Vector Store  │ Text-to-SQL          │
│                   │ Knowledge Base│ API Sources          │
├──────────────────────────────────────────────────────────┤
│  Governance       │ RBAC │ Audit │ Cost │ Quota │ Policy │
├──────────────────────────────────────────────────────────┤
│  Plugin Layer     │ EventSource │ Executor │ Notifier    │
│                   │ DataConnector                        │
│                   │ [ops-alert] [ops-terminal] ...       │
├──────────────────────────────────────────────────────────┤
│  Infrastructure   │ DB │ Sandbox │ Storage │ MCP │ Vector│
└──────────────────────────────────────────────────────────┘
```

### 3.2 Plugin System — Full Architecture

**Plugin SPIs (v1.1 defined, v1.3 extended):**

```python
# Event source: generates workflow trigger signals
class EventSource(Protocol):
    async def subscribe(self, handler: EventHandler) -> None: ...
    async def health_check(self) -> HealthStatus: ...

# Executor: concrete action in workflow
class Executor(Protocol):
    async def execute(self, ctx: ExecutionContext) -> ExecutionResult: ...
    def capabilities(self) -> list[Capability]: ...

# Notifier: result push channel
class Notifier(Protocol):
    async def send(self, target: Target, content: Content) -> None: ...

# 🆕 DataConnector (v1.3): external data access
class DataConnector(Protocol):
    async def connect(self, config: DataSourceConfig) -> Connection: ...
    async def query(self, query: Query, ctx: QueryContext) -> QueryResult: ...
    async def schema(self) -> Schema: ...
```

**Plugin lifecycle:**

```
1. Define → PluginDefinition in registry.py (key, name, SPI type, router, nav_ids)
2. Configure → config.yaml plugins.<key>.enabled: true/false
3. Load → AppConfig(extra="allow") → GatewayConfig.plugins → load_plugin_config()
4. Activate → Backend: conditional router registration, lifespan guards
              Frontend: usePlugins() → hiddenNavIds → nav filtering
5. Discover → GET /api/plugins → PluginInfo[] to frontend
```

**Current plugins:**

| Plugin | SPI Type | Router | Frontend Nav |
|--------|----------|--------|-------------|
| `ops-alerting` | EventSource + Notifier | alerts.router | incidents, /tenant-admin/alerts, /tenant-admin/im |
| `ops-terminal` | Executor | terminal.router | terminal |
| `ops-assets` | — | assets.router | — |

**Planned plugins:**

| Plugin | SPI Type | Version | Description |
|--------|----------|---------|-------------|
| `data-connector-pg` | DataConnector | v1.3 | PostgreSQL connector |
| `data-connector-mysql` | DataConnector | v1.3 | MySQL connector |
| `data-connector-clickhouse` | DataConnector | v1.3 | ClickHouse connector |
| `knowledge-base` | DataConnector + Executor | v1.3 | RAG retrieval, vector search |
| `approval-engine` | Executor | v1.4 | Multi-level approval workflows |
| `compliance-scanner` | Executor | v1.4 | Sensitive data detection, policy compliance |

### 3.3 External Data Architecture

**Data flow:**

```
External Sources              Platform Layer              Agent Context
───────────────              ──────────────              ─────────────
                     ┌─────────────────────────┐
PDF/Word/Markdown → │ Document Ingestion       │
                     │ Chunking → Embedding     │
                     │ → Vector Store (per-tenant)│
                     └──────────┬──────────────┘
                                │
MySQL/PG/ClickHouse →│ DB Connector             │
                     │ Schema Discovery          │
                     │ → Data Catalog           │
                     └──────────┬──────────────┘
                                │
REST/GraphQL APIs →  │ API Connector            │
                     │ Declarative Config        │
                     │ → Normalized Results      │
                     └──────────┬──────────────┘
                                │
                                ▼
                     ┌─────────────────────────┐
                     │ Context Injection Engine │
                     │ • Token budget check     │
                     │ • Formatting strategy    │
                     │ • Priority/ordering      │
                     └──────────┬──────────────┘
                                │
                                ▼
                     ┌─────────────────────────┐
                     │ Agent System Prompt      │
                     │ + Retrieved Context      │
                     │ + User Message           │
                     └─────────────────────────┘
```

**Design decisions:**

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Vector store | Per-tenant isolation, pluggable backend (pgvector default, Milvus optional) | Data isolation is a governance requirement |
| Embedding model | Configurable per tenant, default via existing model management | Reuse existing model infrastructure |
| RAG pipeline | Platform service, not per-agent implementation | Consistency, auditability, reuse |
| Text-to-SQL | Agent skill + schema catalog, not raw SQL generation | Governance: all queries logged, schema access controlled |
| Data connectors | Plugin type extending Executor SPI | Consistent with plugin architecture |

### 3.4 Key Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Workflow engine implementation | Self-developed DAG scheduler, reuse LangGraph as Agent execution unit | Keep orchestration controllable, don't lock Agent internal implementation |
| Agent Runtime vs Workflow | Coexistence, not competition | Agent = "employee", Workflow = "project manager"; different state/audit/recovery requirements |
| Plugin isolation | Python namespace package + independent dependencies | Lightweight, compatible with existing uv workspace |
| Cross-organization federation protocol | OAuth2 + mTLS based REST, JSON Schema capability description | Standardized, easy multi-language implementation |
| Context engineering | Platform layer, not per-agent | Context is a shared concern; templates, compression, and memory are reusable |
| Evaluation framework | Offline + Online + Human annotation | Full-lifecycle quality measurement, data flywheel for continuous improvement |
| Runtime security | Two-phase: perimeter (v1.0) + runtime (v1.4) | Follows NVIDIA enterprise model; defense in depth |

---

## 4. Risks & Migration

### 4.1 Main Risks

| Risk | Impact | Mitigation |
|------|--------|------------|
| Workflow engine and LangGraph state inconsistency | Agent executing when Workflow restarts, state lost | Workflow only stores "invocation handle"; Agent internal state managed by LangGraph; reschedule after restart |
| Context engineering scope creep | v1.4.5 becomes overloaded | Start with prompt templates + window management; compression and memory follow incrementally |
| Data connector security | Tenant data leakage via vector store or SQL queries | Per-tenant vector store isolation; Text-to-SQL queries logged and schema-access controlled; tenant-context enforced at connector layer |
| Runtime security complexity | v1.4 delayed by policy engine implementation | Start with workspace isolation + network policy; capability tokens and pre-execution checks follow |
| A2A protocol fragmentation | Incompatible with Google's A2A or other standards | Monitor A2A standardization; implement as protocol adapter pattern so backend can be swapped |
| Federated ecosystem cross-org trust model complex | v2.0 delayed | v1.4 first implement "cross-tenant" federation (within same platform); v2.0 extend to "cross-platform" |
| Autonomous runtime replacement breaks ecosystem | Existing Skill/Agent incompatible | Maintain API compatibility layer; provide migration tools; LTS version maintained in parallel for 6 months |

### 4.2 Migration Path

```
v1.0 → v1.1: Zero migration, ops plugins enabled by default, behavior unchanged
v1.1 → v1.2: New features, no migration; workflow engine optional enablement
v1.2 → v1.3: Custom Agent upgraded from "basic config" to "full framework", auto-migrate existing Agents. Data connectors enabled per-tenant.
v1.3 → v1.4: Open API + runtime security disabled by default; admin manual enablement. Declarative Agent config is additive (UI still works).
v1.4 → v1.4.5: Context engineering is additive — existing agents use default strategies; opt-in to advanced features.
v1.4.5 → v1.5: Observability data auto-collected; evaluation framework enabled per-tenant. Historical data not backfilled.
v1.x → v2.0: Autonomous runtime deployed in parallel, grayscale migration; DeerFlow runtime marked deprecated. Open governance toolkit released as separate repos.
```

### 4.3 Success Metrics

| Version | Metric |
|---------|--------|
| v1.1 | Plugin toggle test pass rate 100%; README new version narrative published |
| v1.2 | 5 built-in workflow templates; engine handles 1000 concurrent workflows without failure |
| v1.3 | Official skill library 20+ skills; 3 data connector types; A2A protocol verified across 2 agent types |
| v1.4 | Open API documentation complete; at least 1 IM integration launched; runtime security policies enforceable |
| v1.4.5 | Context window management covers 3 strategies; prompt template versioning operational |
| v1.5 | Cost attribution accuracy 95%+; evaluation framework producing actionable metrics; A/B testing framework available |
| v2.0 | Federation protocol verified across 2 independent deployment instances; open governance toolkit has external contributors |

---

## 5. Appendix

### 5.1 Terminology

| Term | Definition |
|------|------------|
| **Digital Employee** | A configured Agent with specific persona, skills, and tool access, serving as a virtual team member |
| **Scenario Pack** | A collection of plugins (EventSource + Executor + Notifier + DataConnector) for a specific vertical domain |
| **Federation** | Cross-organization Agent interoperability with mutual authentication, permission boundaries, and billing |
| **Executor** | A workflow node implementation that performs a concrete action (call Agent, execute code, send HTTP request, etc.) |
| **Context Engineering** | The systematic design and management of what goes into an Agent's context window — templates, compression, retrieval, memory |
| **Harness** | The engineering layer around the model: tools, context, memory, evaluation. The platform's core competency beyond model selection. |
| **A2A** | Agent-to-Agent protocol — standardized discovery, capability advertisement, and invocation between Agents |
| **Data Flywheel** | Feedback → sample collection → retraining/refinement → redeployment → more feedback |

### 5.2 References

- Current README: `README.md`, `README_zh.md`
- Previous roadmap: `docs/superpowers/specs/2026-07-19-governed-agent-platform-roadmap-design.md`
- DeerFlow upstream: https://github.com/bytedance/deer-flow
- NVIDIA Enterprise AI Factory: https://developer.nvidia.com/blog/how-to-govern-autonomous-agents-in-enterprise-ai-factories/
- Google Gemini Managed Agents: https://www.eigent.ai/zh-TW/blog/gemini-managed-agents-explained
- LangChain Governed Agents: https://www.langchain.com/blog/building-governed-agents-a-framework-for-cost-control-and-compliance
- Microsoft Agent Governance Toolkit: https://github.com/microsoft/agent-governance-toolkit
- AI Agent Book (bojieli): https://bojieli.github.io/ai-agent-book/
- Alibaba Cloud 2025 AI Architecture: https://www.aliyun.com/reports/2025-ai-architecture
