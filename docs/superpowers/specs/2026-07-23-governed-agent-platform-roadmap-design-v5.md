# Governed Agent Platform — Roadmap Design (v5)

> **Legacy / Historical:** This document records an earlier project state and may contain superseded product names or compatibility decisions.

**Date**: 2026-07-23
**Status**: Approved
**Authors**: yespon, Claude
**Previous**: [v4](./2026-07-23-governed-agent-platform-roadmap-design-v4.md) | [v3](./2026-07-23-governed-agent-platform-roadmap-design-v3.md) | [v2](./2026-07-23-governed-agent-platform-roadmap-design-v2.md) | [v1](./2026-07-19-governed-agent-platform-roadmap-design.md)

---

## 1. Positioning & Principles

### 1.1 Platform Positioning

**Governed Agent Platform** — enabling any organization to securely create, deploy, and manage its own digital workforce. Governance is not a feature layer; it is the structural guarantee that every tool call, every data access, and every agent action is intercepted, evaluated, and audited at the deterministic code level — not at the probabilistic prompt level.

### 1.2 Core Principles

| Principle | Description |
|-----------|-------------|
| **Governance First** | Governance is deterministic, not probabilistic. RBAC, audit, policy enforcement, and tool-call interception are **builtin** — not optional plugins. Policy Engine is always on; only policy strictness is configurable. |
| **Extension Architecture** | The platform core is minimal. Capabilities are extended through five levers: Builtin SPIs (always-on governance), Extension SPIs (optional capabilities), Event Hooks, Skills (lazy-loaded), and Prompt Templates. |
| **Dual-Track Users** | Serves both bottom-up individual productivity and top-down enterprise provisioning. |
| **Context Engineering** | Context determines agent capability ceiling. Prompt templates, compression, window management, and retrieval strategies are platform-level concerns. |
| **Harness over Model** | Engineering around the model (tools, context, memory, evaluation, governance) outlasts any single model generation. The harness is the moat. |
| **Defense in Depth** | Perimeter security (RBAC, audit) + Compliance (policy engine, OWASP) + Runtime security (sandbox, capability tokens). No single layer is sufficient. |
| **Layered Independence** | Each architectural layer is independently usable. The Agent Loop can be used standalone (SDK mode). Policy Engine is embedded in the Agent Loop at SDK level, and gateway-level at platform level. Governance is everywhere; the deployment topology varies. |
| **Open Evolution** | From single-organization governance to cross-organization federation. Governance capabilities should be open-sourced to build community trust and set standards. |

### 1.3 Explicit Non-Goals

To prevent scope creep, these are explicitly out of scope for all versions:

| Non-Goal | Rationale | Alternative |
|----------|-----------|-------------|
| Building proprietary LLM | We consume models, not train them | Model management (v1.0) already supports 20+ third-party providers |
| Replacing Kubernetes / container orchestration | Existing infrastructure is mature | Sandbox layer integrates with Docker/K8s |
| General-purpose BI tool | AI Analysis Workbench is agent-scoped, not standalone BI | Use dedicated BI tools for BI needs |
| Prompt-level safety | Governance is at deterministic code layer, not probabilistic prompt layer | Policy Engine (v1.3) enforces at tool-call interception |
| Building a cloud hosting service | Self-hosted platform | Docker one-command deploy; edge deployment in v2.0 |
| Chatbot / conversational AI as primary product | Platform is agent governance, not chat UI | Chat workspace is one interface among many |

### 1.4 Strategic Pivot

v1.1 completed the "de-ops" transition. v1.2 extracts the Agent Loop as a standalone primitive and builds the workflow engine. v1.3 introduces the compliance layer with deterministic Policy Engine. v1.4 delivers the digital employee framework, extension system, and data connectivity. v1.5 adds enterprise security, session DAG, and multi-run modes. v1.6 establishes context engineering. v1.7 adds evaluation, SRE governance, and feedback loops. v2.0 achieves architectural independence with identity mesh and federation.

### 1.5 Industry Context

| Source | Key Insight Adopted | Roadmap Impact |
|--------|-------------------|----------------|
| **Pi-Agent (64K+ Stars)** | Three-layer architecture; Agent Loop as standalone primitive; five-lever extension system; skills lazy-loading; session DAG; four run modes; "subtraction philosophy" | v1.2 Agent Loop + Tool Registry; v1.4 extension system; v1.5 session DAG + multi-run modes; v1.6 context compression engine |
| **Microsoft Agent Governance Toolkit** | Governance at deterministic code layer; Policy-as-Code (YAML); OWASP Top 10; Merkle-tree audit; MCP security gateway; Saga; kill switch; SLO/error budgets; identity mesh (SPIFFE/DID/mTLS); trust scoring | v1.2 Saga + kill switch; v1.3 compliance layer; v1.4 marketplace trust; v1.7 SRE governance; v2.0 identity mesh |
| NVIDIA Enterprise AI Factory | Two-phase security (perimeter + runtime); capability tokens; GitOps-driven agent config; default-deny outbound | v1.5 runtime security; v1.5 Agent as Code |
| Google Gemini Managed Agents | Dual-plane API (Control Plane / Data Plane); A2A protocol; four-tier stack | v1.4 A2A protocol |
| LangChain Governed Agents | Hard budget caps with automatic circuit breakers | v1.7 cost attribution + circuit breaker |
| AI Agent Book (bojieli) | Agent = LLM + Context + Tools; Harness engineering is core competency | v1.6 context engineering |
| Alibaba Cloud 2025 AI Architecture | Evaluation as full-lifecycle capability; data flywheel | v1.7 evaluation framework |

---

## 2. Version Planning

Each version lists capabilities with priority tags:
- **(P0)** — Must deliver for this version to ship
- **(P1)** — Can slip to the next version if needed

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

| Priority | Scope | Content |
|----------|-------|---------|
| **P0** | **Agent Loop Primitive** | **Extract think→act→observe→think loop from DeerFlow as standalone reusable module. Independent of LangGraph orchestration. First step toward v2.0 autonomous runtime.** |
| **P0** | **Tool Registry** | **Unified tool definition schema (JSON Schema validation), tool discovery API, tool lifecycle (register/discover/deprecate).** |
| **P0** | **Message System** | **Conversation history representation and passing. Multi-turn state machine. Independent of any specific Agent implementation.** |
| **P0** | Event Source Abstraction | Webhook / Scheduled / File change / Message queue |
| **P0** | Workflow Orchestration | DAG steps, conditional branches, parallel/serial, human approval nodes, retry/timeout |
| **P0** | **Saga Pattern** | **Compensating rollback, idempotency guarantee, retry with exponential backoff** |
| **P0** | **Kill Switch (Infrastructure)** | **Emergency stop all in-flight workflows per tenant/workflow level. Foundation for per-agent kill switch in v1.7.** |
| **P1** | **Circuit Breaker** | **Auto-pause workflow after N consecutive failures; manual or time-based reset. Foundation for SLO-driven circuit breaker in v1.7.** |
| **P0** | Executor Interface | Agent dialogue / Code sandbox / HTTP call / Terminal (as plugin executor) |
| **P0** | Audit Closure | Event → Workflow → Execution → Result, full-chain traceable and replayable |
| **P1** | Built-in Workflow Templates | Scheduled reports, data sync, multi-Agent collaboration |

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
│            │ Policy Engine │ ← [optional, v1.3+]        │
│            │ (Deterministic│   When present: intercept  │
│            │  intercept)   │   When absent: direct pass │
│            └──────────────┘                            │
└─────────────────────────────────────────────────────────┘
```

**Agent Loop vs Workflow Engine coexistence:**

| Aspect | Agent Loop (v1.2) | Workflow Engine (v1.2) |
|--------|-------------------|------------------------|
| Role | "Employee" — single Agent's brain | "Project Manager" — cross-system orchestration |
| Duration | Minutes to hours | Hours to days |
| State | In-memory (checkpoint) | Database persistent, recoverable |
| Human Intervention | In-conversation | Async approval nodes, suspend/resume |
| Cross-System | None | Saga pattern, compensating rollback |
| Failure Recovery | Restart = lost context | Resume from database state |
| Audit | Single conversation | Full-chain, replayable |
| Deployment | Standalone SDK or platform-embedded | Requires platform infrastructure |

**DeerFlow deprecation timeline:**

```
v1.2: Agent Loop extracted (parallel to DeerFlow loop, feature flag toggles between them)
v1.3: Agent Loop becomes default; DeerFlow loop marked deprecated
v1.5: DeerFlow loop removed; only Agent Loop remains
v2.0: LangGraph orchestration replaced; DeerFlow dependency fully removed
```

### v1.3 — Agent Compliance Layer

| Priority | Scope | Content |
|----------|-------|---------|
| **P0** | **Policy Engine (Builtin)** | **Deterministic tool-call interception engine. Always on — not optional, not a plugin. Policy strictness is configurable; the engine itself is not.** |
| **P0** | **Policy as Code** | **YAML-based declarative policies. `default_action: deny` with explicit `allow` rules.** |
| **P0** | **OWASP Agentic AI Top 10** | **Built-in compliance rule set covering all 10 categories. Enabled by default for high-severity rules.** |
| **P1** | Policy Lint & Validation | Static analysis of policy files — catch misconfigurations before deployment. |
| **P0** | **Tamper-Evident Audit Log** | **Merkle-tree structured audit trail. Decision BOM (active policy, agent request, allow/deny reason).** |
| **P1** | MCP Security Gateway | Tool poisoning detection, drift monitoring, typosquatting detection, hidden instruction scanning. |
| **P1** | Shadow AI Discovery | Cross-process/config/repo discovery of unregistered agents. |

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

**Policy Engine is always-on — how it works during migration:**

```
v1.2 → v1.3 upgrade:
  ├─ Policy Engine activated (builtin, cannot be disabled)
  ├─ OWASP high-severity rules: default deny (platform-managed, tenant cannot override)
  ├─ Custom policies: default allow (tenant writes their own policies)
  ├─ agt verify command shows tenant their current policy coverage gaps
  └─ No breaking change: existing tool calls pass through with default-allow custom policies
```

**Design rationale:** Following Microsoft AGT's core philosophy: "Model-layer defenses are probabilistic by construction." Governance intercepts at the deterministic application code layer — the moment the model's intent reaches the wire. The Policy Engine is **builtin**, not a plugin, because governance is a structural guarantee, not an optional feature. What is configurable is policy strictness, not the engine's existence.

### v1.4 — Digital Employee Framework + Extension System + Data Connectivity

| Priority | Scope | Content |
|----------|-------|---------|
| **P0** | Custom Agent Enhancement | system_prompt templating (variable injection) + tool group whitelisting + skill binding + memory policy configuration |
| **P0** | Agent Lifecycle | Draft → Sandbox test → Publish → Version management → Usage statistics → Retirement |
| **P0** | Agent-to-Agent (A2A) Protocol | Intra-tenant Agent discovery, capability advertisement, and direct invocation |
| **P0** | Multi-Agent Collaboration | Sequential (pipeline), Parallel (fan-out), Debate (multi-perspective) modes |
| **P0** | **Extension System** | **Five-lever architecture: Builtin SPIs, Extension SPIs, Event Hooks, Skills (lazy-load), Prompt Templates** |
| **P0** | **Skill Lazy Loading** | **Progressive disclosure — metadata always visible, full instructions + tools loaded only on invocation.** |
| **P0** | Skill Marketplace Phase 1 | Git repository import + Official skill library + Tenant-internal sharing |
| **P1** | Skill Trust Scoring | Download count, user ratings, security scan results, source verification |
| **P0** | **Data Connector Layer** | **Structured + Unstructured data access for Agents** |
| **P1** | AI Analysis Workbench | Data connection → Chart generation → Report/PPT export |
| **P0** | Admin Perspective | Agent provisioning, usage statistics, cost control, permission approval |

**Extension System — Two SPI Categories:**

| Category | SPIs | Toggle | Examples |
|----------|------|--------|----------|
| **Builtin SPIs** | PolicyEnforcer | Always on, strictness configurable | Policy Engine, MCP Security Gateway |
| **Extension SPIs** | EventSource, Executor, Notifier, DataConnector | Optional, config-toggle | ops-alerting, data-connector-pg, approval-engine |

**Extension System — Five Levers:**

| Lever | Mechanism | Hot Reload | Distribution |
|-------|-----------|------------|-------------|
| **Builtin SPIs** | PolicyEnforcer — always on, not optional | Configurable strictness | Platform core |
| **Extension SPIs** | EventSource, Executor, Notifier, DataConnector | Via config toggle | Built-in registry |
| **Event Hooks** | Agent lifecycle hooks: `tool_call_before/after`, `turn_start/end`, `error`, `session_start/end` | Hot reload | Extension packages |
| **Skills** | Lazy-loaded "instruction + tools" packs. Progressive disclosure. Metadata always visible, full content on invocation. | Hot reload | Git import + marketplace |
| **Prompt Templates** | Reusable markdown templates with parameter substitution. Slash-command loadable. Version-controlled. | Hot reload | Template marketplace |

**Event Hooks vs Policy Engine — execution order:**

```
Agent Intent → Tool Call Request
                    │
                    ▼
            ┌──────────────┐
            │ Event Hooks   │  ← tool_call_before hooks (v1.4)
            │ (extensible,  │     Pre-processing: logging, rate limiting, context augmentation
            │  can augment  │     CANNOT veto — only Policy Engine can deny
            │  but not veto)│
            └──────┬───────┘
                   │
                   ▼
            ┌──────────────┐
            │ Policy Engine │  ← Deterministic YAML evaluation (v1.3, builtin)
            │ (always on,   │     FINAL authority: allow / deny / require_approval
            │  can veto)    │
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
            │ Event Hooks   │  ← tool_call_after hooks (v1.4)
            │ (post-        │     Post-processing: metrics, notifications, auto-save
            │  processing)  │
            └──────┬───────┘
                   │
                   ▼
            ┌──────────────┐
            │ Audit Log     │  ← Merkle-tree, tamper-evident
            │ Decision BOM  │
            └──────────────┘
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

**Skill Lazy Loading — transition plan:**

```
v1.3 and earlier: Skills are preloaded (all instructions + tools loaded at session start)
v1.4 upgrade:
  ├─ Existing skills: preload by default (opt-out flag available)
  ├─ New skills: lazy-load by default (metadata always visible, content on invocation)
  ├─ System detects cross-skill tool references and warns if lazy-loading would break them
  └─ v1.5: all skills lazy-load by default; preload flag deprecated
```

### v1.5 — Enterprise Security, Session DAG & Multi-Run Modes

| Priority | Scope | Content |
|----------|-------|---------|
| **P0** | Open API | REST + Webhook: Agent dialogue, workflow trigger, result query; rate limiting, API key management |
| **P0** | Third-Party Integration | Feishu/DingTalk/WeCom/Slack/Teams bidirectional |
| **P0** | SSO/LDAP | Enterprise identity integration, auto-sync org structure to tenants/roles |
| **P1** | Multi-Model Routing | Auto-select model by task type/cost/latency |
| **P0** | **Runtime Security** | **Agent workspace isolation, network policy (default-deny outbound), capability tokens (Agent never sees raw API keys)** |
| **P0** | **Declarative Agent Config** | **Agent as Code (YAML/JSON), GitOps-friendly, version-controlled** |
| **P0** | **Session DAG** | **Tree/DAG-structured conversation sessions. Fork at any point, explore alternative branches, merge or discard.** |
| **P0** | **Multi-Run Modes** | **Interactive (UI), Batch/CI (print/JSON), RPC (cross-process), SDK (embedded). Agent Loop is callable from any mode.** |
| **P1** | **Tool Marketplace** | **Tool discovery, distribution, versioning. Tools are platform assets, not per-agent code. Distinct from v1.2 Tool Registry (which handles registration/validation).** |

**Runtime Security — three-layer model:**

| Layer | Capability | Version |
|-------|-----------|---------|
| Perimeter | RBAC, audit trail, user auth, password rotation | v1.0 |
| Compliance | Policy-as-Code, OWASP Top 10, deterministic tool-call interception, tamper-evident audit | v1.3 |
| Runtime | Agent workspace isolation (sandbox per tenant) | v1.5 |
| Runtime | Network policy (default-deny outbound, allowlist) | v1.5 |
| Runtime | Short-lived capability tokens (Agent never sees raw API keys) | v1.5 |
| Runtime | Policy Engine integration with sandbox (permissions verified before every tool call) | v1.5 |
| Runtime | Unified event output (OCSF-compatible for SIEM integration) | v1.5 |

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

**Multi-Run Modes:**

| Mode | Interface | Use Case |
|------|-----------|----------|
| **Interactive** | Web UI + WebSocket | Daily use, conversation, exploration |
| **Batch/CI** | CLI `--print` / `--json` | Scripts, CI/CD pipelines, automated reports |
| **RPC** | gRPC / REST endpoint | Cross-process integration, microservices |
| **SDK** | `createAgentSession()` | Embedded in third-party applications |

### v1.6 — Context Engineering

| Priority | Scope | Content |
|----------|-------|---------|
| **P0** | Prompt Template System | Variable injection, version management, per-tenant defaults |
| **P0** | Context Window Management | Token budget visualization, overflow warnings, automatic truncation |
| **P1** | **Context Compression Engine** | **Pluggable compression algorithms: summarization, sliding window, semantic pruning. Configurable per agent. Auto-trigger on token threshold.** |
| **P1** | **Conversation DAG Storage** | **Non-linear conversation tree persistence. Each branch independently stored and queryable.** |
| **P1** | **Token Budget Monitor** | **Current consumption, remaining budget, projected exhaustion. Auto-trigger compression.** |
| **P0** | Memory Strategy | Short-term (session), long-term (persistent), semantic (vector retrieval) — configurable per agent |
| **P1** | Cross-Session Continuity | "Continue from last conversation" — context inheritance with decay |
| **P0** | Retrieval Formatting | Structured results → Markdown table / JSON / natural language, configurable formatting |
| **P1** | Prompt Template A/B Branching | Compare prompt variants, data-driven selection |

### v1.7 — Observability, SRE Governance & Evaluation

| Priority | Scope | Content |
|----------|-------|---------|
| **P0** | Agent Runtime Metrics | Success rate, latency, token consumption, user satisfaction |
| **P0** | Workflow Analytics | Bottleneck identification, failure hotspots, optimization suggestions |
| **P0** | **Evaluation Framework** | **Offline eval (test suites), online eval (production sampling), human annotation pipeline** |
| **P0** | **Feedback Loop** | **User rating → auto sample collection → prompt/model iteration** |
| **P1** | **SLO & Error Budgets** | **Per-agent SLO (latency p95, success rate, token efficiency). Budget exhaustion → auto-degradation.** |
| **P1** | **Chaos Testing** | **Agent fault injection, tool timeout simulation, model hallucination testing, network partition drills** |
| **P1** | **Kill Switch (Per-Agent)** | **Extends v1.2 infrastructure kill switch to per-agent granularity.** |
| **P1** | **Circuit Breaker (SLO-driven)** | **Extends v1.2 circuit breaker: auto-throttle agents exceeding error budget. SLO-driven, not failure-count-driven.** |
| **P0** | A/B Testing | Compare different prompts/models/processes, data-driven iteration |
| **P0** | Cost Attribution | Tenant/user/agent/workflow four-level cost allocation, budget alerts with auto circuit-breaker |

**Kill Switch & Circuit Breaker — version evolution:**

| Version | Kill Switch | Circuit Breaker |
|---------|-------------|-----------------|
| v1.2 | Infrastructure-level: stop all workflows per tenant/workflow | Failure-count-based: pause after N consecutive failures |
| v1.7 | Extended to per-agent granularity | Extended to SLO-driven: throttle when error budget exhausted |

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
│  ├─ Kill switch (per-agent, extends v1.2)    │
│  └─ Circuit breaker (SLO-driven, extends v1.2)│
│                                              │
│  Data Flywheel                               │
│  Feedback → Samples → Retrain/Refine → Deploy│
└──────────────────────────────────────────────┘
```

### v2.0 — Autonomous Runtime + Identity Mesh + Federation

| Priority | Scope | Content |
|----------|-------|---------|
| **P0** | Autonomous Agent Runtime | Replace DeerFlow dependency entirely. Agent Loop (v1.2), Tool Registry (v1.2), Message System (v1.2), Policy Engine (v1.3) are already independent. Only LangGraph orchestration remains to be replaced. |
| **P0** | **Identity Mesh** | **SPIFFE/DID/mTLS credentials for every agent. Trust scoring and delegation chain management.** |
| **P1** | Central Skill Registry | Cross-tenant/cross-organization skill sharing and trading (npm-like, enterprise-grade permissions) |
| **P1** | Agent Federation | Cross-organization Agent interoperability: discovery, auth, permission boundaries, billing, versioning |
| **P1** | Low-Code Workflow Designer | Visual orchestration for non-technical users (drag-and-drop nodes, parameter configuration) |
| **P0** | **Open Governance Toolkit** | **RBAC, audit, policy engine, cost attribution, and compliance capabilities released as standalone open-source libraries** |
| **P1** | Edge Deployment | Lightweight runtime deployed to customer environments, data stays on-premises, cloud unified management |

**Incremental migration strategy:**

```
v1.2: Agent Loop extracted (parallel to DeerFlow, feature-flag toggle)
v1.3: Agent Loop becomes default; DeerFlow loop marked deprecated
v1.5: DeerFlow loop removed; only Agent Loop remains
v1.3: Policy Engine independent
v2.0: LangGraph orchestration replaced (last DeerFlow component)
      → DeerFlow dependency fully removed
```

---

## 3. Technical Architecture

### 3.1 Layered Architecture

Version annotations `[vX.Y]` indicate when each module is introduced. Unmarked modules are present from v1.0.

```
┌──────────────────────────────────────────────────────────┐
│  Access Layer     │ Web Console │ Open API [v1.5] │ A2A  │
│                   │ IM Bot │ CLI [v1.5] │ RPC [v1.5]     │
│                   │ SDK [v1.5] │ Batch [v1.5]            │
├──────────────────────────────────────────────────────────┤
│  Context Layer    │ Prompt Templates [v1.4]               │
│  [v1.6]           │ Window Mgmt │ Compression Engine     │
│                   │ Memory Strategy │ DAG Storage        │
├──────────────────────────────────────────────────────────┤
│  Core Layer       │ Agent Loop [v1.2] │ Workflow Engine  │
│                   │ Tool Registry [v1.2] │ Saga [v1.2]   │
│                   │ Message System [v1.2] │ Kill Switch  │
│                   │ Skill System │ Model Router          │
├──────────────────────────────────────────────────────────┤
│  Extension Layer  │ Event Hooks [v1.4] │ Skills (lazy)    │
│  [v1.4]           │ Templates │ Builtin SPI (PolicyEnf) │
│                   │ Extension SPI (EventSrc/Exec/Notif/  │
│                   │  DataConn)                           │
├──────────────────────────────────────────────────────────┤
│  Data Layer       │ RAG Pipeline │ DB Connectors [v1.4]  │
│  [v1.4]           │ Vector Store │ Text-to-SQL           │
│                   │ Knowledge Base│ API Sources          │
├──────────────────────────────────────────────────────────┤
│  Compliance Layer │ Policy Engine [v1.3] (builtin)       │
│  [v1.3]           │ OWASP Rules │ Tool-Call Interception │
│                   │ Tamper-Evident Audit (Merkle)        │
├──────────────────────────────────────────────────────────┤
│  Governance Layer │ RBAC │ Audit │ Cost │ Quota          │
├──────────────────────────────────────────────────────────┤
│  Infrastructure   │ DB │ Sandbox │ Storage │ MCP │ Vector│
└──────────────────────────────────────────────────────────┘
```

### 3.2 Extension System — Full Architecture

**Two SPI categories:**

| Category | SPI | Toggle | Introduced |
|----------|-----|--------|------------|
| **Builtin** | PolicyEnforcer | Always on, strictness configurable | v1.3 |
| Extension | EventSource | Config toggle | v1.1 |
| Extension | Executor | Config toggle | v1.1 |
| Extension | Notifier | Config toggle | v1.1 |
| Extension | DataConnector | Config toggle | v1.4 |
| Extension | EventHook | Hot reload | v1.4 |

**Plugin SPIs:**

```python
# === BUILTIN (always on, not optional) ===

# PolicyEnforcer (v1.3): deterministic tool-call governance
class PolicyEnforcer(Protocol):
    async def evaluate(self, action: ToolAction, ctx: PolicyContext) -> PolicyDecision: ...
    def load_policy(self, policy: PolicyDocument) -> None: ...
    async def audit_log(self, decision: PolicyDecision) -> None: ...

# === EXTENSION (optional, config-toggle) ===

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

# DataConnector (v1.4): external data access
class DataConnector(Protocol):
    async def connect(self, config: DataSourceConfig) -> Connection: ...
    async def query(self, query: Query, ctx: QueryContext) -> QueryResult: ...
    async def schema(self) -> Schema: ...

# EventHook (v1.4): agent lifecycle event subscription
# NOTE: Hooks can augment/augment context but CANNOT veto tool calls.
#       Only PolicyEngine can deny. This is by design.
class EventHook(Protocol):
    async def on_tool_call_before(self, ctx: ToolContext) -> ToolContext | None: ...
    async def on_tool_call_after(self, ctx: ToolContext, result: ToolResult) -> None: ...
    async def on_turn_start(self, ctx: TurnContext) -> None: ...
    async def on_turn_end(self, ctx: TurnContext) -> None: ...
    async def on_error(self, ctx: ErrorContext) -> ErrorAction: ...
    async def on_session_start(self, ctx: SessionContext) -> None: ...
    async def on_session_end(self, ctx: SessionContext) -> None: ...
```

**Current plugins (v1.1):**

| Plugin | Type | Router | Frontend Nav |
|--------|------|--------|-------------|
| `ops-alerting` | Extension (EventSource + Notifier) | alerts.router | incidents, /tenant-admin/alerts, /tenant-admin/im |
| `ops-terminal` | Extension (Executor) | terminal.router | terminal |
| `ops-assets` | Extension | assets.router | — |

**Planned plugins:**

| Plugin | Type | Version | Description |
|--------|------|---------|-------------|
| `policy-owasp` | Builtin (PolicyEnforcer) | v1.3 | OWASP Top 10 compliance rules |
| `mcp-security-gateway` | Builtin (PolicyEnforcer) | v1.3 | MCP tool poisoning detection, drift monitoring |
| `data-connector-pg` | Extension (DataConnector) | v1.4 | PostgreSQL connector |
| `data-connector-mysql` | Extension (DataConnector) | v1.4 | MySQL connector |
| `data-connector-clickhouse` | Extension (DataConnector) | v1.4 | ClickHouse connector |
| `knowledge-base` | Extension (DataConnector + Executor) | v1.4 | RAG retrieval, vector search |
| `approval-engine` | Extension (Executor) | v1.5 | Multi-level approval workflows |
| `compliance-scanner` | Builtin (PolicyEnforcer) | v1.5 | Sensitive data detection, policy compliance |

### 3.3 External Data Architecture

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
| Agent Loop extraction | Standalone module in v1.2, default in v1.3, DeerFlow loop removed in v1.5 | Gradual replacement reduces migration risk |
| Workflow engine | Self-developed DAG + Saga; Agent Loop as execution unit | Keep orchestration controllable; Agent Loop is independent of Workflow |
| Agent Loop vs Workflow | Coexistence, not competition | Agent = "employee", Workflow = "project manager" |
| Governance model | Three-layer: Perimeter (v1.0) + Compliance (v1.3) + Runtime (v1.5) | Defense in depth; NVIDIA + Microsoft AGT |
| Policy enforcement | Deterministic code-level interception; always-on builtin, not optional plugin | Microsoft AGT: "Model-layer defenses are probabilistic" |
| Policy Engine deployment | SDK mode: embedded in Agent Loop. Platform mode: gateway-level in Compliance Layer | Governance is everywhere; deployment topology varies |
| Event Hooks vs Policy Engine | Hooks can augment, cannot veto. Policy Engine is final authority. | Separation of concerns: extensibility ≠ governance |
| Policy language | YAML-based declarative policies | Industry standard (Microsoft AGT, Kubernetes); GitOps-friendly |
| Policy transition | OWASP high-severity: default deny. Custom: default allow → user writes policies. | Safe migration: no breaking change, progressive hardening |
| Extension system | Two SPI categories: Builtin (always on) + Extension (optional) | Governance is not optional; everything else is |
| Skill loading | Progressive disclosure (lazy-load); v1.4 upgrade: existing preload, new lazy; v1.5: all lazy | Backward compatible transition |
| Tool Registry vs Tool Marketplace | Registry (v1.2): register/discover/validate. Marketplace (v1.5): distribute/version/rate. | Different concerns: registration ≠ distribution |
| Kill Switch & Circuit Breaker | v1.2: infrastructure-level. v1.7: extended to per-agent + SLO-driven. | Progressive enhancement, not redefinition |
| Session model | DAG/tree structure, not linear list | Pi-Agent: fork/resume/compare is essential |
| Run modes | Four modes: Interactive, Batch/CI, RPC, SDK | Pi-Agent: same Agent Loop, different interfaces |
| Cross-organization federation | Identity mesh (SPIFFE/DID/mTLS) + OAuth2 REST | Microsoft AGT identity model |
| Context engineering | Platform layer, not per-agent | Context is shared concern |
| Evaluation framework | Offline + Online + Human annotation + SRE governance | Full-lifecycle quality measurement |
| Audit structure | Merkle-tree tamper-evident logs + Decision BOM | Microsoft AGT audit model |

---

## 4. Risks & Migration

### 4.1 Main Risks

| Risk | Impact | Mitigation |
|------|--------|------------|
| Agent Loop extraction breaks DeerFlow integration | Agent execution fails during transition | Parallel run with feature-flag toggle; v1.3 Agent Loop becomes default; v1.5 DeerFlow loop removed |
| Policy engine performance overhead | Tool-call latency increase | Deterministic (no LLM call); target <1ms overhead; Rust core option for hot path |
| Extension system complexity | Five levers may overwhelm users | Each lever independently usable; start with Plugins + Skills (v1.1/v1.4), add Hooks/Packages incrementally |
| Workflow engine and Agent Loop state inconsistency | Agent executing when Workflow restarts | Workflow only stores "invocation handle"; Agent Loop state managed independently; Saga compensates |
| Skill lazy-loading breaks cross-skill references | Skill A's instructions reference Skill B's tools | v1.4 auto-detects cross-skill tool references; existing skills preload by default; v1.5 all lazy |
| Context engineering scope creep | v1.6 becomes overloaded | Start with templates + window management; compression engine, DAG storage, token monitor are P1 |
| Data connector security | Tenant data leakage | Per-tenant vector store isolation; Text-to-SQL logged and schema-access controlled; Policy engine wraps all data access |
| A2A protocol fragmentation | Incompatible with Google's A2A | Monitor standardization; protocol adapter pattern for backend swap |
| Compliance rule maintenance | OWASP Top 10 evolves | Community-contributed rule packs; policy lint; versioned rule sets |
| Federated ecosystem trust model | v2.0 delayed | v1.5 first implement "cross-tenant" federation; v2.0 extend to "cross-platform" via identity mesh |
| Autonomous runtime replacement | Existing Skill/Agent incompatible | API compatibility layer; migration tools; LTS version maintained in parallel for 6 months |

### 4.2 Migration Path

```
v1.0 → v1.1: Zero migration, ops plugins enabled by default, behavior unchanged.

v1.1 → v1.2: Agent Loop extracted as standalone module (parallel to existing DeerFlow loop, feature-flag toggle).
              Tool Registry + Message System are additive. Saga + kill switch + circuit breaker are optional.

v1.2 → v1.3: Policy Engine deployed as builtin (always on).
              OWASP high-severity rules: default deny (platform-managed).
              Custom policies: default allow (tenant writes their own).
              agt verify shows policy coverage gaps. No breaking change.

v1.3 → v1.4: Custom Agent upgraded to "full framework".
              Extension system: Builtin SPIs + Extension SPIs + Event Hooks + Skills (lazy) + Templates.
              Skills: existing preload by default, new lazy by default.
              Cross-skill reference detection warns before lazy-loading.
              Data connectors, A2A, trust scoring enabled per-tenant.

v1.4 → v1.5: Session DAG is additive (linear sessions still work).
              Multi-run modes are additive (web UI still primary).
              Open API + runtime security disabled by default.
              Agent as Code is additive. Skill preload flag deprecated (all skills now lazy).

v1.5 → v1.6: Context engineering is additive. Existing agents use default strategies.
              Compression engine, DAG storage, token monitor are opt-in (P1).

v1.6 → v1.7: Observability data auto-collected.
              SLO, chaos testing, kill switch (per-agent), circuit breaker (SLO-driven) enabled per-tenant.
              Historical data not backfilled.

v1.x → v2.0: Agent Loop, Tool Registry, Message System, Policy Engine already independent from v1.2–v1.3.
              Only LangGraph orchestration remains to be replaced.
              Grayscale migration. Identity mesh is additive.
              Open governance toolkit released as separate repos.
```

### 4.3 Success Metrics

| Version | Technical | Community |
|---------|-----------|-----------|
| v1.1 | Plugin toggle test pass rate 100%; README narrative published | — |
| v1.2 | Agent Loop operates independently of DeerFlow; 5 workflow templates; 1000 concurrent workflows; Saga rollback verified; kill switch stops workflows within 5s | First external contributor PR merged |
| v1.3 | OWASP Top 10 compliance coverage 100%; policy evaluation <1ms overhead; tamper-evident audit verified | — |
| v1.4 | 20+ skills in official library; 3 data connector types; A2A verified across 2 agent types; 5 extension levers operational; trust scoring visible | Monthly active tenants > baseline |
| v1.5 | Session DAG operational (fork/resume/compare); 4 run modes operational; Open API docs complete; ≥1 IM integration launched; runtime security policies enforceable; Agent as Code operational | — |
| v1.6 | 3 compression strategies operational; prompt template versioning operational; token budget monitor real-time | — |
| v1.7 | Cost attribution accuracy 95%+; SLO definition operational; chaos testing 10+ failure modes; evaluation framework producing actionable metrics | NPS > baseline |
| v2.0 | Federation verified across 2 independent instances; identity mesh operational; DeerFlow fully replaced | Open governance toolkit has ≥3 external contributors |

---

## 5. Appendix

### 5.1 Terminology

| Term | Definition |
|------|------------|
| **Digital Employee** | A configured Agent with specific persona, skills, and tool access, serving as a virtual team member |
| **Scenario Pack** | A collection of plugins (EventSource + Executor + Notifier + DataConnector) for a specific vertical domain |
| **Builtin SPI** | A plugin interface that is always active and cannot be disabled (PolicyEnforcer). Only policy strictness is configurable. |
| **Extension SPI** | A plugin interface that is optional and config-toggleable (EventSource, Executor, Notifier, DataConnector). |
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
| **Kill Switch** | Emergency stop mechanism. v1.2: infrastructure-level (workflow/tenant). v1.7: extended to per-agent granularity. |
| **Circuit Breaker** | Auto-throttle mechanism. v1.2: failure-count-based. v1.7: extended to SLO-driven. |
| **Agent Loop** | The think→act→observe→think cycle that is the core of any Agent. A standalone, reusable primitive independent of orchestration framework. |
| **Progressive Disclosure** | Skills load metadata (name + description) eagerly, full instructions + tools only when invoked. Reduces context pollution. |
| **Session DAG** | Non-linear conversation structure: fork at any point, explore alternatives, keep or discard branches. Sessions are graphs, not lists. |

### 5.2 References

- Current README: `README.md`, `README_zh.md`
- Previous roadmaps: `docs/superpowers/specs/2026-07-19-governed-agent-platform-roadmap-design.md`, `v2`, `v3`, `v4`
- DeerFlow upstream: https://github.com/bytedance/deer-flow
- Pi-Agent (64K+ Stars): https://dg-ai-notes.pages.dev/modules/ch01-overview/
- Microsoft Agent Governance Toolkit: https://github.com/microsoft/agent-governance-toolkit
- NVIDIA Enterprise AI Factory: https://developer.nvidia.com/blog/how-to-govern-autonomous-agents-in-enterprise-ai-factories/
- Google Gemini Managed Agents: https://www.eigent.ai/zh-TW/blog/gemini-managed-agents-explained
- LangChain Governed Agents: https://www.langchain.com/blog/building-governed-agents-a-framework-for-cost-control-and-compliance
- AI Agent Book (bojieli): https://bojieli.github.io/ai-agent-book/
- Alibaba Cloud 2025 AI Architecture: https://www.aliyun.com/reports/2025-ai-architecture
