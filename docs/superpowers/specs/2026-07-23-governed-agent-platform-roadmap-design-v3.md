# Governed Agent Platform — Roadmap Design (v3)

> **Legacy / Historical:** This document records an earlier project state and may contain superseded product names or compatibility decisions.

**Date**: 2026-07-23
**Status**: Approved
**Authors**: yespon, Claude
**Previous**: [v2](./2026-07-23-governed-agent-platform-roadmap-design-v2.md) | [v1](./2026-07-19-governed-agent-platform-roadmap-design.md)

---

## 1. Positioning & Principles

### 1.1 Platform Positioning

**Governed Agent Platform** — enabling any organization to securely create, deploy, and manage its own digital workforce. Governance is not a feature layer; it is the structural guarantee that every tool call, every data access, and every agent action is intercepted, evaluated, and audited at the deterministic code level — not at the probabilistic prompt level.

### 1.2 Core Principles

| Principle | Description |
|-----------|-------------|
| **Governance First** | Governance is deterministic, not probabilistic. RBAC, audit, policy enforcement, and tool-call interception are the platform foundation, not add-ons. |
| **Plugin Architecture** | Vertical capabilities are pluggable "scenario packs"; the platform core remains generic. Plugins are first-class citizens with defined SPIs. |
| **Dual-Track Users** | Serves both bottom-up individual productivity and top-down enterprise provisioning. |
| **Context Engineering** | Context determines agent capability ceiling. Prompt templates, compression, window management, and retrieval strategies are platform-level concerns. |
| **Harness over Model** | Engineering around the model (tools, context, memory, evaluation, governance) outlasts any single model generation. The harness is the moat. |
| **Defense in Depth** | Perimeter security (RBAC, audit) + Runtime security (policy engine, sandbox, capability tokens) + Compliance automation (OWASP, policy lint). No single layer is sufficient. |
| **Open Evolution** | From single-organization governance to cross-organization federation. Governance capabilities should be open-sourced to build community trust and set standards. |

### 1.3 Strategic Pivot

v1.1 completed the "de-ops" transition. v1.2 builds the workflow engine with Saga resilience patterns. v1.3 delivers the digital employee framework with data connectivity. v1.3.5 introduces agent compliance as a standalone layer. v1.4 reinforces enterprise security. v1.4.5 establishes context engineering. v1.5 adds evaluation, SRE governance, and feedback loops. v2.0 achieves architectural independence with identity mesh and federation.

### 1.4 Industry Context

The platform is informed by analysis of multiple industry frameworks:

| Source | Key Insight Adopted | Roadmap Impact |
|--------|-------------------|----------------|
| **Microsoft Agent Governance Toolkit** | Governance at deterministic code layer, not prompt level; Policy-as-Code (YAML); OWASP Top 10 coverage; Merkle-tree audit; MCP security gateway; Saga orchestration; kill switch; SLO/error budgets; identity mesh (SPIFFE/DID/mTLS); trust scoring for marketplace | v1.2 Saga + kill switch; v1.3 marketplace trust; v1.3.5 compliance layer; v1.5 SRE governance; v2.0 identity mesh |
| NVIDIA Enterprise AI Factory | Two-phase security (perimeter + runtime); short-lived capability tokens; GitOps-driven agent config; default-deny outbound | v1.4 runtime security; v1.4 Agent as Code |
| Google Gemini Managed Agents | Dual-plane API (Control Plane / Data Plane); A2A protocol; four-tier stack | v1.3 A2A protocol |
| LangChain Governed Agents | Hard budget caps with automatic circuit breakers | v1.5 cost attribution + circuit breaker |
| AI Agent Book (bojieli) | Agent = LLM + Context + Tools; Harness engineering is core competency | v1.4.5 context engineering |
| Alibaba Cloud 2025 AI Architecture | Evaluation as full-lifecycle capability; data flywheel | v1.5 evaluation framework |

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

### v1.2 — Generic Workflow Engine + Resilience

| Scope | Content |
|-------|---------|
| Event Source Abstraction | Webhook / Scheduled / File change / Message queue (Kafka/RabbitMQ interface reserved) |
| Workflow Orchestration | DAG steps, conditional branches, parallel/serial, human approval nodes, retry/timeout |
| **Saga Transaction Pattern** | **Compensating rollback, idempotency guarantee, retry with exponential backoff** |
| **Kill Switch** | **Emergency stop all in-flight workflows per tenant/agent/workflow level** |
| **Circuit Breaker** | **Auto-pause workflow after N consecutive failures; manual or time-based reset** |
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
| Failure Recovery | Restart = lost context | Resume from database state |
| Audit | Single conversation | Full-chain, replayable |

```
Workflow: Trigger → Step1(HTTP) → Step2(Agent) → Step3(Approve) → Step4(Agent) → Done
                              │                  │                 │
                              ▼                  ▼                 ▼
                         Agent Runtime      Human waits        Agent Runtime
                         (inference+tools)  (hours/days)      (inference+tools)
                              │                                    │
                         ┌────▼────┐                          ┌────▼────┐
                         │ Policy  │  ← every tool call        │ Policy  │
                         │ Engine  │     intercepted here      │ Engine  │
                         └─────────┘                          └─────────┘
```

The relationship is NOT competitive — it is complementary. The Workflow Engine calls Agent Runtime as one of its executor types. The Policy Engine wraps every executor. If the Agent process crashes, the Workflow reschedules it. If the Workflow process crashes, it recovers from database state. If a workflow fails N times in a row, the circuit breaker opens.

### v1.3 — Digital Employee Framework + Data Connectivity

| Scope | Content |
|-------|---------|
| Custom Agent Enhancement | system_prompt templating (variable injection) + tool group whitelisting + skill binding + memory policy configuration |
| Agent Lifecycle | Draft → Sandbox test → Publish → Version management → Usage statistics → Retirement |
| Agent-to-Agent (A2A) Protocol | Intra-tenant Agent discovery, capability advertisement, and direct invocation |
| Multi-Agent Collaboration | Sequential (pipeline), Parallel (fan-out), Debate (multi-perspective) modes |
| Skill Marketplace Phase 1 | Git repository import + Official skill library + Tenant-internal sharing |
| **Skill Trust Scoring** | **Download count, user ratings, security scan results, source verification — displayed in marketplace UI** |
| AI Analysis Workbench | Data connection → Chart generation → Report/PPT export |
| **Data Connector Layer** | **Structured + Unstructured data access for Agents** |
| Admin Perspective | Agent provisioning, usage statistics, cost control, permission approval |

**Data Connector Layer:**

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

### v1.3.5 — Agent Compliance & Security (New Version)

| Scope | Content |
|-------|---------|
| **Policy as Code** | **YAML-based declarative policies defining agent behavior boundaries. `default_action: deny` with explicit `allow` rules.** |
| **Deterministic Tool-Call Interception** | **Every tool call is intercepted by the policy engine before execution. Denied = structurally impossible (raises `GovernanceDenied`). Not prompt-level safety.** |
| **OWASP Agentic AI Top 10** | **Built-in compliance rule set covering all 10 categories. `agt verify --strict` equivalent.** |
| **Policy Lint & Validation** | **Static analysis of policy files — catch misconfigurations before deployment.** |
| **Tamper-Evident Audit Log** | **Merkle-tree structured audit trail. Every decision record includes: active policy, agent request, allow/deny reason. Decision BOM (Bill of Materials).** |
| **MCP Security Gateway** | **Tool poisoning detection, drift monitoring, typosquatting detection, hidden instruction scanning for MCP servers.** |
| **Shadow AI Discovery** | **Cross-process/config/repo discovery of unregistered agents. Visibility into unauthorized agent usage.** |

**Policy as Code example:**

```yaml
apiVersion: governance.opsintech.io/v1
name: finance-agent-policy
default_action: deny
rules:
  - name: allow-read-only-db
    condition: "tool_name == 'db_query' && action == 'SELECT'"
    action: allow
  - name: require-approval-write
    condition: "tool_name == 'db_query' && action in ['INSERT', 'UPDATE', 'DELETE']"
    action: require_approval
    approvers: ["tenant_admin"]
  - name: deny-external-network
    condition: "tool_name == 'http_request' && !target_host.endswith('.internal')"
    action: deny
```

**Design rationale:** Following Microsoft AGT's core philosophy: "Model-layer defenses are probabilistic by construction." Governance intercepts at the deterministic application code layer — the moment the model's intent reaches the wire — not at the prompt level. This is a structural guarantee, not a probabilistic one.

### v1.4 — Integration & Enterprise Security

| Scope | Content |
|-------|---------|
| Open API | REST + Webhook: Agent dialogue, workflow trigger, result query; rate limiting, API key management |
| Third-Party Integration | Feishu/DingTalk/WeCom/Slack/Teams bidirectional |
| SSO/LDAP | Enterprise identity integration, auto-sync org structure to tenants/roles |
| Multi-Model Routing | Auto-select model by task type/cost/latency |
| **Runtime Security** | **Agent workspace isolation, network policy, capability tokens, runtime policy enforcement** |
| **Declarative Agent Config** | **Agent as Code (YAML/JSON), GitOps-friendly, version-controlled** |

**Runtime Security:**

Building on v1.0's perimeter security and v1.3.5's compliance layer, v1.4 adds runtime enforcement:

| Layer | Capability | Version |
|-------|-----------|---------|
| Perimeter | RBAC, audit trail, user auth, password rotation | v1.0 |
| Compliance | Policy-as-Code, OWASP Top 10, deterministic tool-call interception, tamper-evident audit | v1.3.5 |
| Runtime | Agent workspace isolation (sandbox per tenant) | v1.4 |
| Runtime | Network policy (default-deny outbound, allowlist) | v1.4 |
| Runtime | Short-lived capability tokens (Agent never sees raw API keys) | v1.4 |
| Runtime | Pre-execution policy check (verify permissions before every tool call) | v1.4 |
| Runtime | Unified event output (OCSF-compatible for SIEM integration) | v1.4 |

This follows NVIDIA's two-phase model, enriched with Microsoft AGT's deterministic interception layer (v1.3.5).

### v1.4.5 — Context Engineering

| Scope | Content |
|-------|---------|
| Prompt Template System | Variable injection, version management, A/B branching, per-tenant defaults |
| Context Window Management | Token budget visualization, overflow warnings, automatic truncation strategies |
| Context Compression | Summarization, sliding window, semantic pruning |
| Memory Strategy | Short-term (session), long-term (persistent), semantic (vector retrieval) — configurable per agent |
| Cross-Session Continuity | "Continue from last conversation" — context inheritance with decay |
| Retrieval Formatting | Structured results → Markdown table / JSON / natural language, configurable formatting |

### v1.5 — Observability, SRE Governance & Evaluation

| Scope | Content |
|-------|---------|
| Agent Runtime Metrics | Success rate, latency, token consumption, user satisfaction |
| Workflow Analytics | Bottleneck identification, failure hotspots, optimization suggestions |
| **SLO & Error Budgets** | **Per-agent SLO definition (latency p95, success rate, token efficiency). Budget exhaustion → auto-degradation.** |
| **Chaos Testing** | **Agent fault injection, tool timeout simulation, model hallucination testing, network partition drills** |
| **Kill Switch (Per-Agent)** | **Emergency stop per agent/workflow/tenant — immediate termination of all in-flight operations** |
| **Circuit Breaker** | **Auto-throttle agents exceeding error budget; manual or time-based reset** |
| **Evaluation Framework** | **Offline eval (test suites), online eval (production sampling), human annotation pipeline** |
| **Feedback Loop** | **User rating → auto sample collection → prompt/model iteration** |
| A/B Testing | Compare different prompts/models/processes, data-driven iteration |
| Cost Attribution | Tenant/user/agent/workflow four-level cost allocation, budget alerts with auto circuit-breaker |

**Evaluation Pipeline:**

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
│  SRE Governance                              │
│  ├─ SLO definition + error budget tracking   │
│  ├─ Chaos testing + fault injection          │
│  ├─ Kill switch (per-agent/workflow)         │
│  └─ Circuit breaker (auto-throttle)          │
│                                              │
│  Data Flywheel                               │
│  Feedback → Samples → Retrain/Refine → Deploy│
└──────────────────────────────────────────────┘
```

### v2.0 — Autonomous Runtime + Identity Mesh + Federation

| Scope | Content |
|-------|---------|
| Autonomous Agent Runtime | Replace DeerFlow dependency, full control of orchestration, state management, checkpoints |
| **Identity Mesh** | **SPIFFE/DID/mTLS credentials for every agent. Trust scoring and delegation chain management. "Which agent did this?" traceability.** |
| Central Skill Registry | Cross-tenant/cross-organization skill sharing and trading (npm-like, enterprise-grade permissions) |
| Agent Federation | Cross-organization Agent interoperability: discovery, auth, permission boundaries, billing, versioning |
| Low-Code Workflow Designer | Visual orchestration for non-technical users (drag-and-drop nodes, parameter configuration) |
| **Open Governance Toolkit** | **RBAC, audit, policy engine, cost attribution, and compliance capabilities released as standalone open-source libraries** |
| Edge Deployment | Lightweight runtime deployed to customer environments, data stays on-premises, cloud unified management |

**Identity Mesh (new in v2.0):**

Following Microsoft AGT's Agent Mesh design: in multi-agent systems, the question "Which agent did this?" must be answered definitively. Each agent gets a SPIFFE-verifiable identity. Trust chains are explicit. Delegation is traceable. This is the foundation for cross-organization federation.

**Open Governance Toolkit (new in v2.0):**

Following Microsoft AGT's precedent of open-sourcing governance capabilities:
- Builds community trust and adoption
- Enables integration with other agent frameworks (LangChain, CrewAI, AutoGen, etc.)
- Positions OpsinTech as a governance standard, not just a platform
- Governance capabilities become a standalone value proposition

---

## 3. Technical Architecture

### 3.1 Layered Architecture

```
┌──────────────────────────────────────────────────────────┐
│  Access Layer     │ Web Console │ Open API │ IM Bot │ A2A│
├──────────────────────────────────────────────────────────┤
│  Context Layer    │ Prompt Templates │ Window Mgmt        │
│                   │ Compression      │ Memory Strategy    │
├──────────────────────────────────────────────────────────┤
│  Core Layer       │ Agent Runtime │ Workflow Engine      │
│                   │ Skill System  │ Model Router         │
│                   │ Saga Engine   │ Kill Switch          │
├──────────────────────────────────────────────────────────┤
│  Data Layer       │ RAG Pipeline  │ DB Connectors        │
│                   │ Vector Store  │ Text-to-SQL          │
│                   │ Knowledge Base│ API Sources          │
├──────────────────────────────────────────────────────────┤
│  Compliance Layer │ Policy Engine │ OWASP Rules          │
│                   │ Tool-Call     │ Tamper-Evident       │
│                   │ Interception  │ Audit (Merkle)       │
├──────────────────────────────────────────────────────────┤
│  Governance Layer │ RBAC │ Audit │ Cost │ Quota │ Policy │
├──────────────────────────────────────────────────────────┤
│  Plugin Layer     │ EventSource │ Executor │ Notifier    │
│                   │ DataConnector │ PolicyEnforcer       │
│                   │ [ops-alert] [ops-terminal] ...       │
├──────────────────────────────────────────────────────────┤
│  Infrastructure   │ DB │ Sandbox │ Storage │ MCP │ Vector│
└──────────────────────────────────────────────────────────┘
```

### 3.2 Plugin System — Full Architecture

**Plugin SPIs:**

```python
# Event source: generates workflow trigger signals
class EventSource(Protocol):
    async def subscribe(self, handler: EventHandler) -> None: ...
    async def health_check(self) -> HealthStatus: ...

# Executor: concrete action in workflow (WRAPPED by PolicyEngine)
class Executor(Protocol):
    async def execute(self, ctx: ExecutionContext) -> ExecutionResult: ...
    def capabilities(self) -> list[Capability]: ...

# Notifier: result push channel
class Notifier(Protocol):
    async def send(self, target: Target, content: Content) -> None: ...

# DataConnector (v1.3): external data access
class DataConnector(Protocol):
    async def connect(self, config: DataSourceConfig) -> Connection: ...
    async def query(self, query: Query, ctx: QueryContext) -> QueryResult: ...
    async def schema(self) -> Schema: ...

# 🆕 PolicyEnforcer (v1.3.5): deterministic tool-call governance
class PolicyEnforcer(Protocol):
    async def evaluate(self, action: ToolAction, ctx: PolicyContext) -> PolicyDecision: ...
    def load_policy(self, policy: PolicyDocument) -> None: ...
    async def audit_log(self, decision: PolicyDecision) -> None: ...
```

**Policy Enforcement Flow:**

```
Agent Intent → Tool Call Request
                    │
                    ▼
            ┌──────────────┐
            │ Policy Engine │  ← Deterministic YAML policy evaluation
            │  (v1.3.5)     │
            └──────┬───────┘
                   │
        ┌──────────┼──────────┐
        ▼          ▼          ▼
     Allow      Deny       Require Approval
        │          │          │
        ▼          ▼          ▼
   Execute    Raise        Queue for
   Tool       Governance   Human
              Denied       Approval
                   │
                   ▼
            ┌──────────────┐
            │ Audit Log     │  ← Merkle-tree, tamper-evident
            │ Decision BOM  │
            └──────────────┘
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
| `policy-owasp` | PolicyEnforcer | v1.3.5 | OWASP Top 10 compliance rules |
| `mcp-security-gateway` | PolicyEnforcer | v1.3.5 | MCP tool poisoning detection, drift monitoring |
| `approval-engine` | Executor | v1.4 | Multi-level approval workflows |
| `compliance-scanner` | PolicyEnforcer | v1.4 | Sensitive data detection, policy compliance |

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

### 3.4 Key Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Workflow engine implementation | Self-developed DAG scheduler + Saga engine; LangGraph as Agent execution unit | Keep orchestration controllable; Saga pattern from Microsoft AGT |
| Agent Runtime vs Workflow | Coexistence, not competition | Agent = "employee", Workflow = "project manager"; different state/audit/recovery requirements |
| Governance model | Three-layer: Perimeter (v1.0) + Compliance (v1.3.5) + Runtime (v1.4) | Defense in depth; follows NVIDIA + Microsoft AGT models |
| Policy enforcement | Deterministic code-level interception, not prompt-level safety | Microsoft AGT: "Model-layer defenses are probabilistic by construction" |
| Policy language | YAML-based declarative policies | Industry standard (Microsoft AGT, Kubernetes); human-readable, GitOps-friendly |
| Plugin isolation | Python namespace package + independent dependencies | Lightweight, compatible with existing uv workspace |
| Cross-organization federation | Identity mesh (SPIFFE/DID/mTLS) + OAuth2 REST | Microsoft AGT identity model; standardized, multi-language |
| Context engineering | Platform layer, not per-agent | Context is a shared concern; templates, compression, memory are reusable |
| Evaluation framework | Offline + Online + Human annotation + SRE governance | Full-lifecycle quality measurement; Microsoft AGT SRE patterns |
| Audit structure | Merkle-tree tamper-evident logs + Decision BOM | Microsoft AGT audit model; cryptographically verifiable |

---

## 4. Risks & Migration

### 4.1 Main Risks

| Risk | Impact | Mitigation |
|------|--------|------------|
| Policy engine performance overhead | Tool-call latency increase | Policy evaluation is deterministic (no LLM call); target <1ms overhead; Rust core option for hot path |
| Workflow engine and LangGraph state inconsistency | Agent executing when Workflow restarts, state lost | Workflow only stores "invocation handle"; Agent internal state managed by LangGraph; Saga compensates on failure |
| Context engineering scope creep | v1.4.5 becomes overloaded | Start with prompt templates + window management; compression and memory follow incrementally |
| Data connector security | Tenant data leakage via vector store or SQL queries | Per-tenant vector store isolation; Text-to-SQL queries logged and schema-access controlled; Policy engine wraps all data access |
| A2A protocol fragmentation | Incompatible with Google's A2A or other standards | Monitor A2A standardization; implement as protocol adapter pattern so backend can be swapped |
| Compliance rule maintenance | OWASP Top 10 evolves; new regulations emerge | Community-contributed rule packs; policy lint catches stale rules; versioned rule sets |
| Federated ecosystem cross-org trust model complex | v2.0 delayed | v1.4 first implement "cross-tenant" federation (within same platform); v2.0 extend to "cross-platform" via identity mesh |
| Autonomous runtime replacement breaks ecosystem | Existing Skill/Agent incompatible | Maintain API compatibility layer; provide migration tools; LTS version maintained in parallel for 6 months |

### 4.2 Migration Path

```
v1.0 → v1.1: Zero migration, ops plugins enabled by default, behavior unchanged
v1.1 → v1.2: New features, no migration; workflow engine optional enablement. Saga + kill switch are additive.
v1.2 → v1.3: Custom Agent upgraded from "basic config" to "full framework", auto-migrate existing Agents. Data connectors, A2A, trust scoring enabled per-tenant.
v1.3 → v1.3.5: Policy engine deployed with default-allow policies (no breaking change). OWASP rules enabled per-tenant. Tamper-evident audit is additive.
v1.3.5 → v1.4: Open API + runtime security disabled by default. Declarative Agent config is additive (UI still works). Policy engine already in place.
v1.4 → v1.4.5: Context engineering is additive — existing agents use default strategies; opt-in to advanced features.
v1.4.5 → v1.5: Observability data auto-collected. SLO definition, chaos testing, kill switch, circuit breaker enabled per-tenant. Historical data not backfilled.
v1.x → v2.0: Autonomous runtime deployed in parallel, grayscale migration. Identity mesh is additive (SPIFFE sidecar). Open governance toolkit released as separate repos.
```

### 4.3 Success Metrics

| Version | Metric |
|---------|--------|
| v1.1 | Plugin toggle test pass rate 100%; README new version narrative published |
| v1.2 | 5 built-in workflow templates; engine handles 1000 concurrent workflows; Saga rollback verified; kill switch stops workflows within 5s |
| v1.3 | Official skill library 20+ skills; 3 data connector types; A2A protocol verified across 2 agent types; trust scoring visible in marketplace |
| v1.3.5 | OWASP Top 10 compliance coverage 100%; policy evaluation <1ms overhead; tamper-evident audit verified |
| v1.4 | Open API documentation complete; at least 1 IM integration launched; runtime security policies enforceable; Agent as Code operational |
| v1.4.5 | Context window management covers 3 strategies; prompt template versioning operational |
| v1.5 | Cost attribution accuracy 95%+; SLO definition operational; chaos testing suite covers 10+ failure modes; evaluation framework producing actionable metrics |
| v2.0 | Federation protocol verified across 2 independent deployment instances; identity mesh operational; open governance toolkit has external contributors |

---

## 5. Appendix

### 5.1 Terminology

| Term | Definition |
|------|------------|
| **Digital Employee** | A configured Agent with specific persona, skills, and tool access, serving as a virtual team member |
| **Scenario Pack** | A collection of plugins (EventSource + Executor + Notifier + DataConnector + PolicyEnforcer) for a specific vertical domain |
| **Federation** | Cross-organization Agent interoperability with mutual authentication, permission boundaries, and billing |
| **Executor** | A workflow node implementation that performs a concrete action (call Agent, execute code, send HTTP request, etc.) |
| **Context Engineering** | The systematic design and management of what goes into an Agent's context window — templates, compression, retrieval, memory |
| **Harness** | The engineering layer around the model: tools, context, memory, evaluation, governance. The platform's core competency beyond model selection. |
| **A2A** | Agent-to-Agent protocol — standardized discovery, capability advertisement, and invocation between Agents |
| **Data Flywheel** | Feedback → sample collection → retraining/refinement → redeployment → more feedback |
| **Policy as Code** | Declarative YAML policies defining agent behavior boundaries; version-controlled, reviewable, GitOps-friendly |
| **Decision BOM** | Bill of Materials for every governance decision: active policy, agent request, allow/deny reason — cryptographically verifiable |
| **Saga** | Distributed transaction pattern: each step has a compensating action; failures trigger rollback of completed steps |
| **Identity Mesh** | SPIFFE/DID/mTLS-based identity layer answering "Which agent did this?" with cryptographic certainty |
| **Kill Switch** | Emergency stop mechanism — immediately terminates all in-flight operations for a given agent/workflow/tenant |
| **Circuit Breaker** | Auto-throttle mechanism — pauses operations after N consecutive failures; prevents cascading failures |

### 5.2 References

- Current README: `README.md`, `README_zh.md`
- Previous roadmaps: `docs/superpowers/specs/2026-07-19-governed-agent-platform-roadmap-design.md`, `2026-07-23-governed-agent-platform-roadmap-design-v2.md`
- DeerFlow upstream: https://github.com/bytedance/deer-flow
- Microsoft Agent Governance Toolkit: https://github.com/microsoft/agent-governance-toolkit
- NVIDIA Enterprise AI Factory: https://developer.nvidia.com/blog/how-to-govern-autonomous-agents-in-enterprise-ai-factories/
- Google Gemini Managed Agents: https://www.eigent.ai/zh-TW/blog/gemini-managed-agents-explained
- LangChain Governed Agents: https://www.langchain.com/blog/building-governed-agents-a-framework-for-cost-control-and-compliance
- AI Agent Book (bojieli): https://bojieli.github.io/ai-agent-book/
- Alibaba Cloud 2025 AI Architecture: https://www.aliyun.com/reports/2025-ai-architecture
