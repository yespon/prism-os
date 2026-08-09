# Governed Agent Platform — Roadmap Design (v4)

> **Legacy / Historical:** This document records an earlier project state and may contain superseded product names or compatibility decisions.

**Date**: 2026-07-23
**Status**: Approved
**Authors**: yespon, Claude
**Previous**: [v3](./2026-07-23-governed-agent-platform-roadmap-design-v3.md) | [v2](./2026-07-23-governed-agent-platform-roadmap-design-v2.md) | [v1](./2026-07-19-governed-agent-platform-roadmap-design.md)

---

## 1. Positioning & Principles

### 1.1 Platform Positioning

**Governed Agent Platform** — enabling any organization to securely create, deploy, and manage its own digital workforce. Governance is not a feature layer; it is the structural guarantee that every tool call, every data access, and every agent action is intercepted, evaluated, and audited at the deterministic code level — not at the probabilistic prompt level.

### 1.2 Core Principles

| Principle | Description |
|-----------|-------------|
| **Governance First** | Governance is deterministic, not probabilistic. RBAC, audit, policy enforcement, and tool-call interception are the platform foundation, not add-ons. |
| **Extension Architecture** | The platform core is minimal. Capabilities are added through a five-lever extension system: Plugins (SPIs), Event Hooks, Skills (lazy-loaded), Prompt Templates, and Extension Packages. |
| **Dual-Track Users** | Serves both bottom-up individual productivity and top-down enterprise provisioning. |
| **Context Engineering** | Context determines agent capability ceiling. Prompt templates, compression, window management, and retrieval strategies are platform-level concerns. |
| **Harness over Model** | Engineering around the model (tools, context, memory, evaluation, governance) outlasts any single model generation. The harness is the moat. |
| **Defense in Depth** | Perimeter security (RBAC, audit) + Compliance (policy engine, OWASP) + Runtime security (sandbox, capability tokens). No single layer is sufficient. |
| **Layered Independence** | Each architectural layer is independently usable. The Agent Loop can be used without the workflow engine. The model API can be called without the Agent Loop. The TUI/UI is independent of the Agent engine. |
| **Open Evolution** | From single-organization governance to cross-organization federation. Governance capabilities should be open-sourced to build community trust and set standards. |

### 1.3 Strategic Pivot

v1.1 completed the "de-ops" transition. v1.2 extracts the Agent Loop as a standalone primitive from DeerFlow, alongside the workflow engine — this is the first step toward v2.0's autonomous runtime. v1.3 upgrades the extension system to five levers. v1.3.5 introduces agent compliance. v1.4 adds session DAG, multi-run modes, and enterprise security. v1.4.5 establishes context engineering. v1.5 adds evaluation, SRE governance, and feedback loops. v2.0 achieves architectural independence with identity mesh and federation.

### 1.4 Industry Context

The platform is informed by analysis of multiple industry frameworks:

| Source | Key Insight Adopted | Roadmap Impact |
|--------|-------------------|----------------|
| **Pi-Agent (64K+ Stars)** | Three-layer architecture with independent layers; Agent Loop as standalone primitive; five-lever extension system (extensions/hooks, skills/lazy-load, templates, themes, packages); session DAG (fork/resume); four run modes (interactive/print/RPC/SDK); "subtraction philosophy" — core minimal, users fill in | v1.2 Agent Loop primitive + Tool Registry; v1.3 extension system upgrade; v1.4 session DAG + multi-run modes; v1.4.5 context compression engine |
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

### v1.2 — Workflow Engine + Agent Loop Primitive

| Scope | Content |
|-------|---------|
| **Agent Loop Primitive** | **Extract think→act→observe→think loop from DeerFlow as standalone reusable module. Independent of DeerFlow's LangGraph orchestration. First step toward v2.0 autonomous runtime.** |
| **Tool Registry** | **Unified tool definition schema (TypeBox-style parameter validation), tool discovery API, tool lifecycle (register/discover/deprecate). Tools are platform-managed, not scattered across DeerFlow and custom code.** |
| **Message System Abstraction** | **Conversation history representation and passing. Multi-turn conversation state machine. Independent of any specific Agent implementation.** |
| Event Source Abstraction | Webhook / Scheduled / File change / Message queue (Kafka/RabbitMQ interface reserved) |
| Workflow Orchestration | DAG steps, conditional branches, parallel/serial, human approval nodes, retry/timeout |
| **Saga Transaction Pattern** | **Compensating rollback, idempotency guarantee, retry with exponential backoff** |
| **Kill Switch** | **Emergency stop all in-flight workflows per tenant/agent/workflow level** |
| **Circuit Breaker** | **Auto-pause workflow after N consecutive failures; manual or time-based reset** |
| Executor Interface | Agent dialogue / Code sandbox / HTTP call / Terminal (as plugin executor) |
| Audit Closure | Event → Workflow → Execution → Result, full-chain traceable and replayable |
| Built-in Templates | Scheduled reports, data sync, multi-Agent collaboration |

**Agent Loop Primitive — Architecture:**

```
┌─────────────────────────────────────────────────────────┐
│                   Agent Loop Engine                      │
│  (independent of DeerFlow, independent of Workflow)      │
│                                                         │
│  User Input → ┌──────────┐    ┌──────────┐             │
│               │  Think   │ → │  Act     │             │
│               │ (LLM)    │ ← │ (Tool)   │             │
│               └──────────┘    └────┬─────┘             │
│                    │               │                    │
│                    ▼               ▼                    │
│              ┌──────────┐    ┌──────────┐             │
│              │ Observe  │ ← │ Result   │             │
│              │ (LLM)    │    │ Processing│            │
│              └────┬─────┘    └──────────┘             │
│                   │                                    │
│                   ▼                                    │
│            ┌──────────────┐                            │
│            │ Tool Registry │ ← Unified tool definition  │
│            │ (discovery,   │   & parameter validation   │
│            │  validation)  │                            │
│            └──────────────┘                            │
│                   │                                    │
│                   ▼                                    │
│            ┌──────────────┐                            │
│            │ Policy Engine │ ← Deterministic intercept  │
│            │ (v1.3.5)      │   before every tool call   │
│            └──────────────┘                            │
└─────────────────────────────────────────────────────────┘
```

**Design rationale:** Pi-Agent's pi-agent-core proves that the Agent Loop is a standalone, reusable primitive — not something that must be bundled with a specific orchestration framework. Extracting it from DeerFlow now (v1.2) rather than waiting for v2.0 reduces the eventual migration surface and gives us a clean interface to build on.

**Key clarification — Agent Runtime vs Workflow Engine coexistence:**

| Aspect | Agent Loop (v1.2) | Workflow Engine (v1.2) |
|--------|-------------------|------------------------|
| Role | "Employee" — single Agent's brain | "Project Manager" — cross-system orchestration |
| Duration | Minutes to hours | Hours to days |
| State | In-memory (checkpoint) | Database persistent, recoverable |
| Human Intervention | In-conversation | Async approval nodes, suspend/resume |
| Cross-System | None | Saga pattern, compensating rollback |
| Failure Recovery | Restart = lost context | Resume from database state |
| Audit | Single conversation | Full-chain, replayable |
| Deployment | Can be used standalone (SDK) | Requires platform infrastructure |

### v1.3 — Digital Employee Framework + Extension System Upgrade

| Scope | Content |
|-------|---------|
| Custom Agent Enhancement | system_prompt templating (variable injection) + tool group whitelisting + skill binding + memory policy configuration |
| Agent Lifecycle | Draft → Sandbox test → Publish → Version management → Usage statistics → Retirement |
| Agent-to-Agent (A2A) Protocol | Intra-tenant Agent discovery, capability advertisement, and direct invocation |
| Multi-Agent Collaboration | Sequential (pipeline), Parallel (fan-out), Debate (multi-perspective) modes |
| Skill Marketplace Phase 1 | Git repository import + Official skill library + Tenant-internal sharing |
| **Skill Trust Scoring** | **Download count, user ratings, security scan results, source verification** |
| **Skill Lazy Loading** | **Progressive disclosure — skills loaded on demand, not preloaded. Skill metadata (name + description) is always visible; full instructions + tools loaded only when invoked. Reduces context pollution.** |
| AI Analysis Workbench | Data connection → Chart generation → Report/PPT export |
| **Data Connector Layer** | **Structured + Unstructured data access for Agents** |
| **Extension System Upgrade** | **Five-lever extension architecture** |
| Admin Perspective | Agent provisioning, usage statistics, cost control, permission approval |

**Extension System — Five Levers (upgraded from v1.1's 3 SPIs):**

| Lever | Mechanism | Hot Reload | Distribution |
|-------|-----------|------------|-------------|
| **Plugins (SPIs)** | EventSource, Executor, Notifier, DataConnector, PolicyEnforcer | Via config toggle | Built-in registry |
| **Event Hooks** | Agent lifecycle hooks: `tool_call_before/after`, `turn_start/end`, `error`, `session_start/end` | Hot reload | Extension packages |
| **Skills** | Lazy-loaded "instruction + tools" capability packs. Progressive disclosure — metadata always visible, full content loaded on invocation. | Hot reload | Git import + marketplace |
| **Prompt Templates** | Reusable markdown templates with parameter substitution. Slash-command loadable. Version-controlled. | Hot reload | Template marketplace |
| **Extension Packages** | Packaged extensions (hooks + skills + templates + tools). npm/git distribution. Version management. Dependency resolution. | Hot reload | npm / git registry |

**Five-lever philosophy (inspired by Pi-Agent):** The platform core is minimal. Users compose capabilities from five independent levers. Each lever is independently usable, hot-reloadable, and distributable. This is the opposite of a "monolithic agent platform" — it's a kit of parts.

**Event Hook examples:**

```typescript
// Agent lifecycle hooks
session.on("tool_call_before", async (ctx) => {
  // Pre-execution validation, logging, rate limiting
});

session.on("turn_end", async (ctx) => {
  // Auto-save context, trigger notifications, update metrics
});

session.on("error", async (ctx) => {
  // Custom error recovery, alerting, fallback
});
```

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

### v1.3.5 — Agent Compliance & Security

| Scope | Content |
|-------|---------|
| **Policy as Code** | **YAML-based declarative policies defining agent behavior boundaries. `default_action: deny` with explicit `allow` rules.** |
| **Deterministic Tool-Call Interception** | **Every tool call is intercepted by the policy engine before execution. Denied = structurally impossible (raises `GovernanceDenied`). Not prompt-level safety.** |
| **OWASP Agentic AI Top 10** | **Built-in compliance rule set covering all 10 categories.** |
| **Policy Lint & Validation** | **Static analysis of policy files — catch misconfigurations before deployment.** |
| **Tamper-Evident Audit Log** | **Merkle-tree structured audit trail. Every decision record includes: active policy, agent request, allow/deny reason. Decision BOM.** |
| **MCP Security Gateway** | **Tool poisoning detection, drift monitoring, typosquatting detection, hidden instruction scanning for MCP servers.** |
| **Shadow AI Discovery** | **Cross-process/config/repo discovery of unregistered agents.** |

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

### v1.4 — Integration, Enterprise Security, Session DAG & Multi-Run Modes

| Scope | Content |
|-------|---------|
| Open API | REST + Webhook: Agent dialogue, workflow trigger, result query; rate limiting, API key management |
| Third-Party Integration | Feishu/DingTalk/WeCom/Slack/Teams bidirectional |
| SSO/LDAP | Enterprise identity integration, auto-sync org structure to tenants/roles |
| Multi-Model Routing | Auto-select model by task type/cost/latency |
| **Runtime Security** | **Agent workspace isolation, network policy, capability tokens, runtime policy enforcement** |
| **Declarative Agent Config** | **Agent as Code (YAML/JSON), GitOps-friendly, version-controlled** |
| **Session DAG** | **Tree/DAG-structured conversation sessions. Fork at any point, explore alternative branches, merge or discard. `/tree`-equivalent navigation. Session state is a graph, not a list.** |
| **Multi-Run Modes** | **Interactive (UI), Batch/CI (print/JSON output), RPC (cross-process), SDK (embedded in third-party apps). Agent Loop is callable from any mode.** |
| **Tool Platformization** | **Unified ToolRegistry (from v1.2) extended with TypeBox/JSON Schema validation, tool marketplace, tool versioning. Tools are platform assets, not per-agent code.** |

**Runtime Security:**

| Layer | Capability | Version |
|-------|-----------|---------|
| Perimeter | RBAC, audit trail, user auth, password rotation | v1.0 |
| Compliance | Policy-as-Code, OWASP Top 10, deterministic tool-call interception, tamper-evident audit | v1.3.5 |
| Runtime | Agent workspace isolation (sandbox per tenant) | v1.4 |
| Runtime | Network policy (default-deny outbound, allowlist) | v1.4 |
| Runtime | Short-lived capability tokens (Agent never sees raw API keys) | v1.4 |
| Runtime | Pre-execution policy check (verify permissions before every tool call) | v1.4 |
| Runtime | Unified event output (OCSF-compatible for SIEM integration) | v1.4 |

**Session DAG:**

```
                    ┌──────────┐
                    │ Session  │
                    │  Root    │
                    └────┬─────┘
                         │
              ┌──────────┼──────────┐
              ▼          ▼          ▼
         ┌────────┐ ┌────────┐ ┌────────┐
         │Branch A│ │Branch B│ │Branch C│
         │(default)│ │(try X) │ │(try Y) │
         └───┬────┘ └───┬────┘ └───┬────┘
             │          │          │
         ┌───▼───┐  ┌──▼───┐  ┌──▼───┐
         │Step 3 │  │Step 3│  │Step 3│
         │(merge)│  │(disc.)│  │(keep) │
         └───────┘  └──────┘  └──────┘
```

**Design rationale (inspired by Pi-Agent):** Linear sessions force users to start over when they want to try a different approach. A DAG session model allows forking at any point, exploring alternatives, and keeping or discarding branches. This is a core productivity feature for complex agent interactions.

**Multi-Run Modes:**

| Mode | Interface | Use Case |
|------|-----------|----------|
| **Interactive** | Web UI + WebSocket | Daily use, conversation, exploration |
| **Batch/CI** | CLI `--print` / `--json` | Scripts, CI/CD pipelines, automated reports |
| **RPC** | gRPC / REST endpoint | Cross-process integration, microservices |
| **SDK** | `createAgentSession()` | Embedded in third-party applications |

### v1.4.5 — Context Engineering

| Scope | Content |
|-------|---------|
| Prompt Template System | Variable injection, version management, A/B branching, per-tenant defaults |
| Context Window Management | Token budget visualization, overflow warnings, automatic truncation strategies |
| **Context Compression Strategy Engine** | **Pluggable compression algorithms: summarization, sliding window, semantic pruning. Configurable per agent. Auto-trigger on token threshold.** |
| **Conversation DAG Storage** | **Non-linear conversation tree persistence. Each branch is independently stored and queryable. Supports fork/resume/compare.** |
| **Token Budget Real-Time Monitor** | **Current consumption, remaining budget, projected exhaustion. Auto-trigger compression when approaching limit.** |
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
| Autonomous Agent Runtime | Replace DeerFlow dependency entirely. Agent Loop (v1.2), Tool Registry (v1.2), Message System (v1.2), and Policy Engine (v1.3.5) are already independent. Only LangGraph orchestration remains to be replaced. |
| **Identity Mesh** | **SPIFFE/DID/mTLS credentials for every agent. Trust scoring and delegation chain management. "Which agent did this?" traceability.** |
| Central Skill Registry | Cross-tenant/cross-organization skill sharing and trading (npm-like, enterprise-grade permissions) |
| Agent Federation | Cross-organization Agent interoperability: discovery, auth, permission boundaries, billing, versioning |
| Low-Code Workflow Designer | Visual orchestration for non-technical users (drag-and-drop nodes, parameter configuration) |
| **Open Governance Toolkit** | **RBAC, audit, policy engine, cost attribution, and compliance capabilities released as standalone open-source libraries** |
| Edge Deployment | Lightweight runtime deployed to customer environments, data stays on-premises, cloud unified management |

**Migration strategy (incremental, not big-bang):**

```
v1.2: Agent Loop extracted as standalone module ← First step
v1.2: Tool Registry + Message System independent ← Second step
v1.3.5: Policy Engine independent ← Third step
v2.0: Replace LangGraph orchestration ← Final step
      (Agent Loop + Tool Registry + Message System + Policy Engine
       are already independent — only orchestration remains)
```

---

## 3. Technical Architecture

### 3.1 Layered Architecture

```
┌──────────────────────────────────────────────────────────┐
│  Access Layer     │ Web Console │ Open API │ IM Bot │ A2A│
│                   │ CLI │ RPC │ SDK │ Batch              │
├──────────────────────────────────────────────────────────┤
│  Context Layer    │ Prompt Templates │ Window Mgmt        │
│                   │ Compression      │ Memory Strategy    │
│                   │ Compression Engine│ DAG Storage       │
├──────────────────────────────────────────────────────────┤
│  Core Layer       │ Agent Loop │ Workflow Engine          │
│                   │ (standalone)│ Saga │ Kill Switch      │
│                   │ Tool Registry │ Message System        │
│                   │ Skill System  │ Model Router          │
├──────────────────────────────────────────────────────────┤
│  Extension Layer  │ Event Hooks │ Skills (lazy)           │
│                   │ Templates  │ Packages (npm/git)      │
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
│  Infrastructure   │ DB │ Sandbox │ Storage │ MCP │ Vector│
└──────────────────────────────────────────────────────────┘
```

### 3.2 Extension System — Full Architecture

**Extension Levers:**

```
┌─────────────────────────────────────────────────────────┐
│                  Extension System                        │
│                                                         │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐              │
│  │ Plugins  │  │  Event   │  │  Skills  │              │
│  │  (SPIs)  │  │  Hooks   │  │  (Lazy)  │              │
│  │          │  │          │  │          │              │
│  │EventSrc  │  │tool_call │  │on-demand │              │
│  │Executor  │  │_before/  │  │load of   │              │
│  │Notifier  │  │after     │  │instrs +  │              │
│  │DataConn  │  │turn_start│  │tools     │              │
│  │PolicyEnf │  │/end      │  │          │              │
│  └──────────┘  └──────────┘  └──────────┘              │
│                                                         │
│  ┌──────────┐  ┌──────────┐                            │
│  │ Prompt   │  │Extension │                            │
│  │ Templates│  │ Packages │                            │
│  │          │  │          │                            │
│  │.md +     │  │npm/git   │                            │
│  │params    │  │distrib.  │                            │
│  │+ version │  │versioned │                            │
│  └──────────┘  └──────────┘                            │
│                                                         │
│  All levers: Hot-reloadable, independently distributable│
└─────────────────────────────────────────────────────────┘
```

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

# PolicyEnforcer (v1.3.5): deterministic tool-call governance
class PolicyEnforcer(Protocol):
    async def evaluate(self, action: ToolAction, ctx: PolicyContext) -> PolicyDecision: ...
    def load_policy(self, policy: PolicyDocument) -> None: ...
    async def audit_log(self, decision: PolicyDecision) -> None: ...

# 🆕 EventHook (v1.3): agent lifecycle event subscription
class EventHook(Protocol):
    async def on_tool_call_before(self, ctx: ToolContext) -> ToolContext | None: ...
    async def on_tool_call_after(self, ctx: ToolContext, result: ToolResult) -> None: ...
    async def on_turn_start(self, ctx: TurnContext) -> None: ...
    async def on_turn_end(self, ctx: TurnContext) -> None: ...
    async def on_error(self, ctx: ErrorContext) -> ErrorAction: ...
    async def on_session_start(self, ctx: SessionContext) -> None: ...
    async def on_session_end(self, ctx: SessionContext) -> None: ...

# 🆕 ExtensionPackage (v1.3): distributable extension bundle
class ExtensionPackage(Protocol):
    def manifest(self) -> PackageManifest: ...  # name, version, dependencies
    def hooks(self) -> list[EventHook]: ...
    def skills(self) -> list[Skill]: ...
    def templates(self) -> list[PromptTemplate]: ...
    def tools(self) -> list[Tool]: ...
```

**Policy Enforcement Flow:**

```
Agent Intent → Tool Call Request
                    │
                    ▼
            ┌──────────────┐
            │ Event Hooks   │  ← tool_call_before hooks
            │ (v1.3)        │
            └──────┬───────┘
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
        │          │          │
        ▼          ▼          ▼
            ┌──────────────┐
            │ Event Hooks   │  ← tool_call_after hooks
            │ (v1.3)        │
            └──────┬───────┘
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
| Agent Loop extraction | Standalone module in v1.2, not wait for v2.0 | Pi-Agent proves Agent Loop is a reusable primitive; gradual DeerFlow replacement reduces migration risk |
| Workflow engine implementation | Self-developed DAG scheduler + Saga engine; Agent Loop as execution unit | Keep orchestration controllable; Agent Loop is independent of Workflow |
| Agent Loop vs Workflow | Coexistence, not competition | Agent = "employee", Workflow = "project manager"; different state/audit/recovery requirements |
| Extension system | Five independent levers (Plugins, Hooks, Skills, Templates, Packages) | Pi-Agent's five-lever model; each lever independently usable, hot-reloadable, distributable |
| Skill loading | Progressive disclosure (lazy-load) | Pi-Agent: "don't pollute context with unused skills"; metadata always visible, full content on invocation |
| Session model | DAG/tree structure, not linear list | Pi-Agent: fork/resume/compare is essential for complex agent interactions |
| Run modes | Four modes: Interactive, Batch/CI, RPC, SDK | Pi-Agent: same Agent Loop, different interfaces; enables embedding in any context |
| Governance model | Three-layer: Perimeter (v1.0) + Compliance (v1.3.5) + Runtime (v1.4) | Defense in depth; follows NVIDIA + Microsoft AGT models |
| Policy enforcement | Deterministic code-level interception, not prompt-level safety | Microsoft AGT: "Model-layer defenses are probabilistic by construction" |
| Policy language | YAML-based declarative policies | Industry standard (Microsoft AGT, Kubernetes); human-readable, GitOps-friendly |
| Cross-organization federation | Identity mesh (SPIFFE/DID/mTLS) + OAuth2 REST | Microsoft AGT identity model; standardized, multi-language |
| Context engineering | Platform layer, not per-agent | Context is shared concern; compression engine, DAG storage, token monitor are reusable |
| Evaluation framework | Offline + Online + Human annotation + SRE governance | Full-lifecycle quality measurement; Microsoft AGT SRE patterns |
| Audit structure | Merkle-tree tamper-evident logs + Decision BOM | Microsoft AGT audit model; cryptographically verifiable |

---

## 4. Risks & Migration

### 4.1 Main Risks

| Risk | Impact | Mitigation |
|------|--------|------------|
| Agent Loop extraction breaks DeerFlow integration | Agent execution fails during transition | Agent Loop runs in parallel with DeerFlow's existing loop; feature flag to switch between them; gradual cutover |
| Policy engine performance overhead | Tool-call latency increase | Policy evaluation is deterministic (no LLM call); target <1ms overhead; Rust core option for hot path |
| Extension system complexity | Five levers may overwhelm users | Each lever is independently usable; start with Plugins + Skills (v1.1/v1.3), add Hooks/Templates/Packages incrementally |
| Workflow engine and Agent Loop state inconsistency | Agent executing when Workflow restarts, state lost | Workflow only stores "invocation handle"; Agent Loop state managed independently; Saga compensates on failure |
| Context engineering scope creep | v1.4.5 becomes overloaded | Start with prompt templates + window management; compression engine, DAG storage, and token monitor follow incrementally |
| Data connector security | Tenant data leakage via vector store or SQL queries | Per-tenant vector store isolation; Text-to-SQL queries logged and schema-access controlled; Policy engine wraps all data access |
| A2A protocol fragmentation | Incompatible with Google's A2A or other standards | Monitor A2A standardization; implement as protocol adapter pattern so backend can be swapped |
| Compliance rule maintenance | OWASP Top 10 evolves; new regulations emerge | Community-contributed rule packs; policy lint catches stale rules; versioned rule sets |
| Federated ecosystem cross-org trust model complex | v2.0 delayed | v1.4 first implement "cross-tenant" federation (within same platform); v2.0 extend to "cross-platform" via identity mesh |
| Autonomous runtime replacement breaks ecosystem | Existing Skill/Agent incompatible | Maintain API compatibility layer; provide migration tools; LTS version maintained in parallel for 6 months |

### 4.2 Migration Path

```
v1.0 → v1.1: Zero migration, ops plugins enabled by default, behavior unchanged
v1.1 → v1.2: Agent Loop extracted as standalone module (parallel to existing DeerFlow loop). Tool Registry + Message System are additive. Saga + kill switch + circuit breaker are optional.
v1.2 → v1.3: Custom Agent upgraded to "full framework". Extension system upgraded to five levers (Hooks + Templates + Packages are additive). Skills transition to lazy-loading (backward compatible). Data connectors, A2A, trust scoring enabled per-tenant.
v1.3 → v1.3.5: Policy engine deployed with default-allow policies (no breaking change). OWASP rules enabled per-tenant. Tamper-evident audit is additive.
v1.3.5 → v1.4: Session DAG is additive (linear sessions still work). Multi-run modes are additive (web UI still primary). Open API + runtime security disabled by default. Agent as Code is additive.
v1.4 → v1.4.5: Context engineering is additive — existing agents use default strategies; opt-in to compression engine, DAG storage, token monitor.
v1.4.5 → v1.5: Observability data auto-collected. SLO definition, chaos testing, kill switch, circuit breaker enabled per-tenant. Historical data not backfilled.
v1.x → v2.0: Agent Loop, Tool Registry, Message System, Policy Engine are already independent from v1.2–v1.3.5. Only LangGraph orchestration remains to be replaced. Grayscale migration. Identity mesh is additive. Open governance toolkit released as separate repos.
```

### 4.3 Success Metrics

| Version | Metric |
|---------|--------|
| v1.1 | Plugin toggle test pass rate 100%; README new version narrative published |
| v1.2 | Agent Loop operates independently of DeerFlow; 5 built-in workflow templates; engine handles 1000 concurrent workflows; Saga rollback verified; kill switch stops workflows within 5s |
| v1.3 | Official skill library 20+ skills; 3 data connector types; A2A protocol verified across 2 agent types; trust scoring visible in marketplace; 5 extension levers operational |
| v1.3.5 | OWASP Top 10 compliance coverage 100%; policy evaluation <1ms overhead; tamper-evident audit verified |
| v1.4 | Session DAG operational (fork/resume/compare); 4 run modes operational; Open API documentation complete; at least 1 IM integration launched; runtime security policies enforceable; Agent as Code operational |
| v1.4.5 | Context window management covers 3 compression strategies; prompt template versioning operational; token budget monitor real-time |
| v1.5 | Cost attribution accuracy 95%+; SLO definition operational; chaos testing suite covers 10+ failure modes; evaluation framework producing actionable metrics |
| v2.0 | Federation protocol verified across 2 independent deployment instances; identity mesh operational; open governance toolkit has external contributors; DeerFlow dependency fully replaced |

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
| **Agent Loop** | The think→act→observe→think cycle that is the core of any Agent. A standalone, reusable primitive independent of orchestration framework. |
| **Progressive Disclosure** | Skills load metadata (name + description) eagerly, full instructions + tools only when invoked. Reduces context pollution. |
| **Session DAG** | Non-linear conversation structure: fork at any point, explore alternatives, keep or discard branches. Sessions are graphs, not lists. |
| **Extension Package** | Distributable bundle of hooks + skills + templates + tools, versioned via npm/git. |

### 5.2 References

- Current README: `README.md`, `README_zh.md`
- Previous roadmaps: `docs/superpowers/specs/2026-07-19-governed-agent-platform-roadmap-design.md`, `v2`, `v3`
- DeerFlow upstream: https://github.com/bytedance/deer-flow
- Pi-Agent (64K+ Stars): https://dg-ai-notes.pages.dev/modules/ch01-overview/
- Microsoft Agent Governance Toolkit: https://github.com/microsoft/agent-governance-toolkit
- NVIDIA Enterprise AI Factory: https://developer.nvidia.com/blog/how-to-govern-autonomous-agents-in-enterprise-ai-factories/
- Google Gemini Managed Agents: https://www.eigent.ai/zh-TW/blog/gemini-managed-agents-explained
- LangChain Governed Agents: https://www.langchain.com/blog/building-governed-agents-a-framework-for-cost-control-and-compliance
- AI Agent Book (bojieli): https://bojieli.github.io/ai-agent-book/
- Alibaba Cloud 2025 AI Architecture: https://www.aliyun.com/reports/2025-ai-architecture
