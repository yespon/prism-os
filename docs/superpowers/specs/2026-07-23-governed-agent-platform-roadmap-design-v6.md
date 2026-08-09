# Governed Agent Platform — Roadmap Design (v6)

> **Legacy / Historical:** This document records an earlier project state and may contain superseded product names or compatibility decisions.

**Date**: 2026-07-23
**Status**: Approved
**Authors**: yespon, Claude
**Previous**: [v5](./2026-07-23-governed-agent-platform-roadmap-design-v5.md) | [v4](./2026-07-23-governed-agent-platform-roadmap-design-v4.md) | [v3](./2026-07-23-governed-agent-platform-roadmap-design-v3.md) | [v2](./2026-07-23-governed-agent-platform-roadmap-design-v2.md) | [v1](./2026-07-19-governed-agent-platform-roadmap-design.md)

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
| **Governance as Foundation, Extension as Superstructure** | Policy Engine is the foundation (like an OS kernel) — builtin, always-on, non-optional. Extension SPIs are the superstructure (like user-space programs) — optional, configurable, distributable. Governance is the ground the platform stands on; everything else is built on top. This resolves the tension between "minimal core" and "always-on governance": the core is minimal in its *extension* surface, not in its *governance* surface. |
| **Layered Independence** | Each architectural layer is independently usable. In v2.0+, the Agent Loop can be used standalone (SDK mode) after LangGraph is replaced. In v1.2–v1.7, the Agent Loop is a decoupling abstraction over LangGraph — usable via SDK but not yet independent of LangGraph. Policy Engine is embedded in the Agent Loop at SDK level, and gateway-level at platform level. Governance is everywhere; the deployment topology varies. |
| **Open Evolution** | From single-organization governance to cross-organization federation. Governance capabilities should be open-sourced to build community trust and set standards. |
| **Human on the Loop** | Humans are a core component of the system, not external observers. They serve two irreplaceable functions: intent provision (the first mover — agents don't self-generate goals) and value arbitration (judging "right vs wrong" beyond logic). Humans don't intervene in every step but maintain continuous awareness, intervene at key nodes, and retain termination capability. `require_approval` in Policy Engine is its engineering realization. Rationale: Harness Engineering ch15 — operational alignment is maintained through continuous sensing + key-node intervention, not step-by-step participation. |

### 1.3 Explicit Non-Goals

To prevent scope creep, these are explicitly out of scope for all versions:

| Non-Goal | Rationale | Alternative |
|----------|-----------|-------------|
| Building proprietary LLM | We consume models, not train them | Model management (v1.0) already supports 20+ third-party providers |
| Replacing Kubernetes / container orchestration | Existing infrastructure is mature | Sandbox layer integrates with Docker/K8s |
| General-purpose BI tool | AI Analysis Workbench is agent-scoped, not standalone BI | Use dedicated BI tools for BI needs |
| Prompt-level safety | Governance is at deterministic code layer, not probabilistic prompt layer | Policy Engine (v1.4) enforces at tool-call interception |
| Building a cloud hosting service | Self-hosted platform | Docker one-command deploy; edge deployment in v2.0 |
| Chatbot / conversational AI as primary product | Platform is agent governance, not chat UI | Chat workspace is one interface among many |
| Mobile client | Desktop/server-first platform | Web UI is responsive; no native mobile app planned |

### 1.4 Strategic Pivot

v1.1 completed the "de-ops" transition. v1.2 extracts the Agent Loop as an abstraction layer over LangGraph (decoupling, not replacement) — the first step toward v2.0's autonomous runtime. v1.3 builds the workflow engine. v1.4 introduces the compliance layer. v1.5 delivers the digital employee framework and extension system. v1.6 adds the data connector layer. v1.7 adds enterprise security, session DAG, multi-run modes, and removes the DeerFlow loop. v1.8 establishes context engineering. v1.9 adds evaluation, SRE governance, and feedback loops. v2.0 replaces LangGraph entirely, achieving architectural independence with identity mesh and federation.

**Key change from v5**: Overloaded versions (v1.2 with 9 P0s, v1.4 with 9 P0s, v1.6 with 10 P0s) have been split into focused, deliverable increments. Each version now targets 3-8 P0 items.

### 1.5 Version Cadence Assumptions

These are planning assumptions, not commitments. Actual velocity depends on team size and availability.

| Version | Estimated Duration | Suggested Team |
|---------|-------------------|----------------|
| v1.2 | 2-3 months | 2 backend |
| v1.3 | 2-3 months | 2 backend + 1 frontend |
| v1.4 | 2 months | 1-2 backend |
| v1.5 | 3-4 months | 2 backend + 1 frontend |
| v1.6 | 2-3 months | 1-2 backend |
| v1.7 | 3-4 months | 2 backend + 1 frontend + 1 DevOps |
| v1.8 | 2-3 months | 1-2 backend |
| v1.9 | 2-3 months | 2 backend + 1 frontend |
| v2.0 | 4-6 months | 2 backend + 1 frontend + 1 DevOps |

**Total**: ~22-31 months from v1.2 to v2.0 with the suggested team size. A smaller team (1-2 people total) should expect 2-3x the duration.

### 1.6 Industry Context

| Source | Key Insight Adopted | Roadmap Impact |
|--------|-------------------|----------------|
| **Pi-Agent (64K+ Stars)** | Three-layer architecture; Agent Loop abstraction layer; five-lever extension system; skills lazy-loading; session DAG; four run modes | v1.2 Agent Loop + Tool Registry; v1.5 extension system; v1.7 session DAG + multi-run modes; v1.8 context compression |
| **Microsoft Agent Governance Toolkit** | Governance at deterministic code layer; Policy-as-Code (YAML); OWASP Top 10; Merkle-tree audit; MCP security gateway; Saga; kill switch; SLO/error budgets; identity mesh (SPIFFE/DID/mTLS) | v1.3 Saga + kill switch; v1.4 compliance layer; v1.5 marketplace trust; v1.9 SRE governance; v2.0 identity mesh |
| NVIDIA Enterprise AI Factory | Two-phase security (perimeter + runtime); capability tokens; GitOps-driven agent config; default-deny outbound | v1.7 runtime security; v1.7 Agent as Code |
| Google Gemini Managed Agents | Dual-plane API (Control Plane / Data Plane); A2A protocol; four-tier stack | v1.5 A2A protocol |
| LangChain Governed Agents | Hard budget caps with automatic circuit breakers | v1.9 cost attribution + circuit breaker |
| AI Agent Book (bojieli) | Agent = LLM + Context + Tools; Harness engineering is core competency | v1.8 context engineering |
| Alibaba Cloud 2025 AI Architecture | Evaluation as full-lifecycle capability; data flywheel | v1.9 evaluation framework |

### 1.7 Business Model & Sustainability

A 22-31 month roadmap requires a sustainability model. The platform is self-hosted open source; revenue comes from three streams, not from hosting:

| Stream | Description | Target Version |
|--------|-------------|----------------|
| **Open Source Core** | Full platform (v1.0–v2.0) is Apache 2.0 / MIT. No feature gates. Self-hostable at no cost. | All versions |
| **Enterprise Edition** | Advanced features for enterprise: Edge Deployment (v2.0 P1), Agent Federation (v2.0 P1), Identity Mesh (v2.0), SSO/LDAP (v1.7). Released as open source but with commercial support contracts. | v1.7+ |
| **Governance Toolkit Commercial Support** | The 4 Open Governance libraries (v2.0) are Apache 2.0. Commercial offering: SLA-backed support, custom policy packs, integration consulting. | v2.0 |
| **Hosted Option (future, not committed)** | If demand emerges post-v2.0, a managed hosted version may be considered. Not in current roadmap. | Post-v2.0 |

**Principle**: The open source core is never feature-gated. Enterprise value is in support, advanced deployment topologies, and consulting — not in withholding features. This aligns with Microsoft AGT's open governance approach and Pi-Agent's fully-open model.

**Sustainability assumption**: The platform is maintained by the author + community contributors during v1.x. Commercial revenue is expected to begin with v1.7 (Enterprise Edition features). If commercial traction is insufficient by v1.9, v2.0 scope will be reduced to match available resources.

### 1.8 Market Window Analysis

The governance and agent platform space is evolving rapidly. This analysis frames the competitive window:

| Window | Analysis | Roadmap Response |
|--------|----------|------------------|
| **Governance standardization** | Microsoft AGT (v4.1, 45→5 packages) is converging the governance toolkit space. If we wait until v2.0 to open-source, AGT may be the de facto standard. | Consider pulling Open Governance Toolkit forward to v1.4 (Policy Engine release) — but this conflicts with v1.4's focused scope. Decision deferred to v1.4 planning. |
| **DeerFlow upstream** | DeerFlow is ByteDance's project; its evolution is not under our control. If DeerFlow stops maintenance or pivots, v1.2–v1.7 are affected. | Agent Loop extraction (v1.2) is itself the hedge — the earlier we decouple, the lower the upstream risk. |
| **Agent platform consolidation** | LangChain, CrewAI, AutoGen, Google ADK are competing. By v1.7 (~15-18 months, DeerFlow removed) and v2.0 (~22+ months, full independence), the field may have consolidated. | Our differentiation is *governance* (deterministic, not probabilistic) and *self-hosted enterprise*. Neither is well-served by current competitors. v1.7 is the first major architecture milestone; v2.0 is full independence. |
| **Single-user vs enterprise** | Pi-Agent (64K stars) proved single-user demand. Enterprise agent platforms are underserved. | Our enterprise + governance positioning avoids direct competition with single-user tools. |

**Risk**: If the field consolidates before v2.0, federation (v2.0) may be solving a problem that standardization has already addressed. Monitor and adjust.

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

### v1.2 — Agent Loop Primitive

**Focus**: Extract the Agent Loop as an abstraction layer over LangGraph, decoupling platform code from DeerFlow-specific APIs. This is the first step toward v2.0's autonomous runtime (which replaces LangGraph entirely). No workflow engine yet — that comes in v1.3. Note: v1.2 is decoupling, not independence from LangGraph.

**Minimum Viable Harness (5 components)**: The Harness Engineering book (ch2) proves that any mature Harness converges to the same 5 components with the same topology: System Prompt, Context, Plan, Tool, Hook. Our Agent Loop instantiates all 5. This reference frame ensures we don't miss foundational components.

**Q/T/C Three-Axis Constraint**: Quality (output correctness), Time (latency), Cost (token budget). These are the three irreducible constraints of any Agent system (Harness Engineering ch3-4). Every operation consumes from all three axes. v1.2 introduces the budget concept; v1.4 Plan Schema carries estimated_cost (C-axis) and success_criteria (Q-axis); v1.9 SLO definitions cover the T-axis.

| Priority | Scope | Content |
|----------|-------|---------|
| **P0** | **Agent Loop Primitive** | **Extract Agent Loop abstraction layer over LangGraph, decoupling platform code from LangGraph-specific APIs. Runs in parallel with existing DeerFlow loop via feature flag. Note: v1.2 is decoupling, not replacement — LangGraph is still the underlying runtime. v2.0 replaces LangGraph entirely.** |
| **P0** | **Tool Registry** | **Unified tool definition schema (JSON Schema validation), tool discovery API, tool lifecycle (register/discover/deprecate).** |
| **P0** | **Message System** | **Conversation history representation and passing. Multi-turn state machine. Interface is implementation-agnostic; in v1.2–v1.7 the implementation still adapts to LangGraph's message model. Truly independent at v2.0.** |
| **P1** | Executor Interface | Agent dialogue / Code sandbox / HTTP call / Terminal (plugin executor). Basic interface definition; full implementation in v1.3. |

**Agent Loop Primitive — Architecture:**

```
┌─────────────────────────────────────────────────────────┐
│                   Agent Loop Engine                      │
│  (abstraction layer over LangGraph, decoupling platform  │
│   code from LangGraph-specific APIs)                     │
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
│            │ Policy Engine │ ← [optional, v1.4+]        │
│            │ (Deterministic│   When present: intercept  │
│            │  intercept)   │   When absent: direct pass │
│            └──────────────┘                            │
│                                                         │
│  ┌─────────────────────────────────────────────────┐   │
│  │  LangGraph Runtime (DeerFlow's orchestration)    │   │
│  │  v1.2-v1.7: underlying runtime (via abstraction) │   │
│  │  v2.0: replaced by autonomous runtime            │   │
│  └─────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────┘
```

**Parallel run strategy:**

```
v1.2 deployment:
  ├─ Agent Loop runs alongside DeerFlow's existing LangGraph loop
  ├─ Feature flag: OPSINTECH_AGENT_LOOP=new|legacy (default: legacy)
  ├─ Both loops share the same Tool Registry and Message System
  ├─ Automated comparison tests:
  │   ├─ Tool-call sequence match rate (allows order differences, target ≥90%)
  │   ├─ Final result success rate (human-evaluated sample, target: no statistically significant difference)
  │   └─ Latency distribution (p50/p95 comparison, target: Agent Loop within ±10% of DeerFlow)
  └─ Telemetry: track latency, success rate, divergence rate for both loops
```

**DeerFlow deprecation timeline:**

```
v1.2: Agent Loop extracted (parallel to DeerFlow, feature-flag toggle)
v1.3: Agent Loop becomes default; DeerFlow loop marked deprecated
v1.7: DeerFlow loop removed; only Agent Loop remains
v2.0: LangGraph orchestration replaced; DeerFlow dependency fully removed
```

### v1.3 — Workflow Engine

**Focus**: Build the automation layer. The Agent Loop (v1.2) is the "employee"; the Workflow Engine is the "project manager". This version assumes v1.2's Agent Loop is stable and available as an execution unit.

| Priority | Scope | Content |
|----------|-------|---------|
| **P0** | Event Source Abstraction | Webhook / Scheduled / File change / Message queue |
| **P0** | Workflow Orchestration | DAG steps, conditional branches, parallel/serial, human approval nodes, retry/timeout |
| **P0** | **Saga Pattern (Idempotent Retry + Selective Compensation)** | **Idempotent retry with exponential backoff for all steps. Selective compensation rollback for steps with reversible side effects (e.g., sent notifications can be revoked; executed SQL cannot be "un-executed"). Note: Agent workflow failure modes differ from microservice transactions — most steps support retry, not compensation.** |
| **P0** | **Kill Switch (Infrastructure)** | **Emergency stop all in-flight workflows per tenant/workflow level. Foundation for per-agent kill switch in v1.9.** |
| **P0** | Executor Interface | Full implementation: Agent dialogue / Code sandbox / HTTP call / Terminal (as plugin executor) |
| **P0** | Audit Closure | Event → Workflow → Execution → Result, full-chain traceable and replayable |
| **P1** | **Circuit Breaker** | **Auto-pause workflow after N consecutive failures; manual or time-based reset. Foundation for SLO-driven circuit breaker in v1.9.** |
| **P1** | Built-in Workflow Templates | Scheduled reports, data sync, multi-Agent collaboration |

**Agent Loop vs Workflow Engine coexistence:**

| Aspect | Agent Loop (v1.2) | Workflow Engine (v1.3) |
|--------|-------------------|------------------------|
| Role | "Employee" — single Agent's brain | "Project Manager" — cross-system orchestration |
| Duration | Minutes to hours | Hours to days |
| State | In-memory (checkpoint) | Database persistent, recoverable |
| Human Intervention | In-conversation (v1.7+) | Async approval nodes, suspend/resume |
| Cross-System | None | Saga pattern, idempotent retry + selective compensation |
| Failure Recovery | Restart = lost context | Resume from database state |
| Audit | Single conversation | Full-chain, replayable |
| Deployment | Standalone SDK or platform-embedded | Requires platform infrastructure |

```
Workflow: Trigger → Step1(HTTP) → Step2(Agent) → Step3(Approve) → Step4(Agent) → Done
                              │                  │                 │
                              ▼                  ▼                 ▼
                         Agent Loop          Human waits        Agent Loop
                         (v1.2)              (hours/days)       (v1.2)
```

### v1.4 — Agent Compliance Layer

**Focus**: Deterministic governance. Policy Engine is always-on, builtin — not optional. This is the structural guarantee that every tool call is intercepted.

| Priority | Scope | Content |
|----------|-------|---------|
| **P0** | **Policy Engine (Builtin)** | **Deterministic tool-call interception engine. Always on — not optional, not a plugin. Policy strictness is configurable; the engine itself is not.** |
| **P0** | **Policy as Code** | **YAML-based declarative policies. `default_action: deny` with explicit `allow` rules. Supports `risk_tier` field per rule: `low` (auto-allow, e.g., read-only queries — avoids approval fatigue), `medium` (require_approval, e.g., write operations), `high` (deny unless explicitly approved, e.g., destructive ops). Rationale: Pi-Agent warns that per-call approval becomes "security theater"; tiered auto-allow for low-risk operations balances governance with usability.** |
| **P0** | **Plan-before-Act** | **Agent must submit a structured Plan before executing irreversible actions. Plan Schema: goal, steps[] (action, expected_output, fallback, depends_on, estimated_cost), success_criteria, abort_conditions. Policy Engine validates Plan at submission time — verifying Q/T/C budget before execution is 1-2 orders of magnitude cheaper than inspecting execution traces. Rationale: Harness Engineering ch9 — principal-agent theory; reviewing a plan is cheaper than reviewing an execution trace.** |
| **P0** | **OWASP Agentic AI Top 10** | **Built-in compliance rule set covering all 10 categories. Enabled by default for high-severity rules.** |
| **P0** | **Tamper-Evident Audit Log** | **Merkle-tree structured audit trail. Decision BOM (active policy, agent request, allow/deny reason).** |
| **P1** | Policy Lint & Validation | Static analysis of policy files — catch misconfigurations before deployment. |
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
    risk_tier: low          # auto-allow; avoids approval fatigue
  - name: require-approval-write
    condition: "tool_name == 'db_query' && action in ['INSERT', 'UPDATE', 'DELETE']"
    action: require_approval
    approvers: ["tenant_admin"]
    risk_tier: medium
  - name: deny-external-network
    condition: "tool_name == 'http_request' && !target_host.endswith('.internal')"
    action: deny
    risk_tier: high
  - name: auto-correct-known-format
    condition: "tool_name == 'file_write' && error_type == 'format_mismatch'"
    action: auto_correct   # reversible + known pattern → Hook corrects automatically, no interruption
    risk_tier: low
  - name: abort-safety-redline
    condition: "tool_name == 'shell_exec' && command matches 'rm -rf /'"
    action: abort          # immediate task termination + alert
    risk_tier: high
```

**Escalation policy (three-tier, from Harness Engineering ch11):**

| Tier | Trigger | Response |
|------|---------|----------|
| **Auto-correct** | Reversible operation + known error pattern | Hook corrects automatically, logs decision |
| **Human confirm** | Irreversible operation / plan deviation > threshold | Suspend execution, await human approval |
| **Task abort** | Explicit safety redline triggered | Immediate termination + alert notification |

Rationale: A binary allow/deny creates approval fatigue. Three-tier escalation matches the cost structure of errors — auto-correct is cheapest (no human interruption), human confirm is for genuinely ambiguous cases, and abort is for clear safety violations.

**Policy Engine is always-on — migration strategy:**

```
v1.3 → v1.4 upgrade:
  ├─ Policy Engine activated (builtin, cannot be disabled)
  ├─ OWASP high-severity rules: default deny (platform-managed, tenant cannot override)
  ├─ Custom policies: default allow (tenant writes their own policies)
  ├─ agt verify command shows tenant their current policy coverage gaps
  └─ No breaking change: existing tool calls pass through with default-allow custom policies
```

**Policy Engine deployment modes:**

| Mode | Description | When to use |
|------|-------------|-------------|
| **Platform embedded** | Policy Engine runs in the Compliance Layer of the platform. All tool calls pass through the gateway. | Normal platform deployment |

SDK deployment modes (Embedded / Remote) are defined in v1.7 when the SDK is introduced.

### v1.5 — Digital Employee Framework + Extension System

**Focus**: Enable users to create, customize, and manage their own Agents. Introduce the full extension system. Skills become lazy-loaded. Prompt Templates are delivered as a complete system here.

| Priority | Scope | Content |
|----------|-------|---------|
| **P0** | Custom Agent Enhancement | system_prompt templating (variable injection) + tool group whitelisting + skill binding + memory policy configuration |
| **P0** | Agent Lifecycle | Draft → Sandbox test → Publish → Version management → Usage statistics → Retirement |
| **P0** | **Prompt Template System** | **Variable injection, version management, per-tenant defaults, slash-command loadable, reusable markdown templates. Includes prompt budget (token cap on system prompts; auto-downgrade or split when exceeded). Rationale: Pi-Agent achieves TerminalBench #2 with ~90-word system prompts vs Claude Code's tens of thousands of tokens — purer context yields better reasoning. Delivered as a complete system — not fragmented across versions.** |
| **P0** | **Extension System** | **Five-lever architecture: Builtin SPIs, Extension SPIs, Event Hooks, Skills (lazy-load), Prompt Templates** |
| **P0** | **Skill Lazy Loading** | **Progressive disclosure — metadata always visible, full instructions + tools loaded only on invocation.** |
| **P0** | Skill Marketplace Phase 1 | Git repository import + Official skill library + Tenant-internal sharing |
| **P0** | Agent-to-Agent (A2A) Protocol | Intra-tenant Agent discovery, capability advertisement, and direct invocation |
| **P1** | Multi-Agent Collaboration | Sequential (pipeline), Parallel (fan-out), Debate (multi-perspective) modes. Includes coordination cost accounting: each mode must evaluate specialization benefit vs coordination cost. Dec-POMDP is NEXP-complete (Harness Engineering ch14) — the theoretical lower bound for coordination cost is exponential in agent count. Swarm mode is gated behind explicit cost/benefit approval. Prefer structured message communication over natural language for agent-to-agent messages. |
| **P1** | Skill Trust Scoring | Download count, user ratings, security scan results, source verification |
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
| **Event Hooks** | Agent lifecycle hooks: `tool_call_before/after`, `turn_start/end`, `error`, `session_start/end`, `stop` (task completion verification) | Hot reload | Extension packages |

**Event Hooks — three time nodes (from Harness Engineering ch11):**

| Node | Cost | Coverage | Example Sensors |
|------|------|----------|-----------------|
| **PreToolUse** | Lowest (prevention) | Critical risks | Permission check (computational, <1ms), input format validation (computational, <5ms), dangerous pattern detection (rule-based, <10ms) |
| **PostToolUse** | Medium (correction) | Output errors | Output format validation (computational), critical error detection (rule-based), semantic quality assessment (LLM-as-judge, optional, triggered only after expensive ops) |
| **Stop** | Highest (verification) | Goal achievement | Full test suite run (computational), task goal verification (semantic) |

**Sensor types (cost-ordered pipeline, fail-fast):**

| Type | Cost | Reliability | Examples |
|------|------|-------------|----------|
| **Computational** | ~1/100~1/1000 of semantic | Deterministic, cheap | Linter, structural tests, format validators, dependency checks |
| **Rule-based** | ~1/10 of semantic | Deterministic, medium | Regex patterns, policy rule matching, threshold checks |
| **Semantic** | Base cost (LLM call) | Probabilistic, expensive | LLM-as-judge, code review agent, semantic quality assessment |

Pipeline design: computational sensors first (filter most errors at lowest cost), rule-based second, semantic last (and only when cheaper checks pass). This is fail-fast — most requests pass or fail at the cheapest tier. A vague failure message ("operation failed") vs a precise one ("line 42 assertion failed, expected 5 got 3") differ by orders of magnitude in the agent's search narrowing effectiveness — sensor output quality is equally important as capture rate.
| **Skills** | Lazy-loaded "instruction + tools" packs. Progressive disclosure. Metadata always visible, full content on invocation. | Hot reload | Git import + marketplace |
| **Prompt Templates** | Reusable markdown templates with parameter substitution. Slash-command loadable. Version-controlled. Variable injection, version management, per-tenant defaults. Prompt budget enforced. | Hot reload | Template marketplace |

**Hot reload mechanism (two modes):**

```
Development mode (local):
  ├─ File-system watcher detects extension/skill/template changes
  ├─ Changes apply to running sessions immediately, no restart
  └─ No audit required (developer's own environment)

Runtime mode (production):
  ├─ Changes applied via admin API (POST /api/extensions/reload)
  ├─ Requires tenant_admin or platform_admin permission
  ├─ Every reload audited (who, what, when, before/after diff)
  └─ Policy Engine policies themselves can only be reloaded by platform_admin
     (governance changes are high-risk, not tenant-self-service)
```

Rationale: Pi-Agent's hot reload applies changes to running sessions immediately. Enterprise scenarios require the same developer ergonomics but with permission control and audit — a developer's hot reload is a admin's audited config change.

**Prompt Template delivery:**

v1.5 delivers the complete Prompt Template system — variable injection, version management, per-tenant defaults, slash-command loading, reusable markdown templates. This is NOT fragmented across versions. v1.8 adds only A/B branching as a P1 enhancement.

**Event Hooks vs Policy Engine — execution order:**

v1.4 (before Event Hooks):

```
Agent Intent → Tool Call Request
                    │
                    ▼
            ┌──────────────┐
            │ Policy Engine │  ← Deterministic YAML evaluation (v1.4, builtin)
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
                   │
                   ▼
            ┌──────────────┐
            │ Audit Log     │  ← Merkle-tree, tamper-evident
            │ Decision BOM  │
            └──────────────┘
```

v1.5+ (with Event Hooks wrapping Policy Engine):

```
Agent Intent → Tool Call Request
                    │
                    ▼
            ┌──────────────┐
            │ Event Hooks   │  ← tool_call_before hooks (v1.5)
            │ (extensible,  │     Pre-processing: logging, rate limiting, context augmentation
            │  can augment  │     CANNOT veto — only Policy Engine can deny
            │  but not veto)│
            └──────┬───────┘
                   │
                   ▼
            ┌──────────────┐
            │ Policy Engine │  ← Deterministic YAML evaluation (v1.4, builtin)
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
            │ Event Hooks   │  ← tool_call_after hooks (v1.5)
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

**Skill Lazy Loading — transition plan:**

```
v1.4 and earlier: Skills are preloaded (all instructions + tools loaded at session start)
v1.5 upgrade:
  ├─ Existing skills: preload by default (opt-out flag available)
  ├─ New skills: lazy-load by default (metadata always visible, content on invocation)
  ├─ System detects cross-skill tool references and warns if lazy-loading would break them
  └─ v1.7: all skills lazy-load by default; preload flag deprecated
```

### v1.6 — Data Connector Layer

**Focus**: Give Agents access to external data. Structured and unstructured. This was previously bundled into v1.4 (v5) as a single P0 — it is now its own version.

| Priority | Scope | Content |
|----------|-------|---------|
| **P0** | **Data Connector SPI** | **DataConnector protocol definition. Connection lifecycle, query interface, schema discovery. Reference implementation: PostgreSQL connector.** |
| **P0** | **Document Ingestion** | **PDF/Word/Markdown/HTML → Chunking → Embedding → Per-tenant vector store.** |
| **P0** | **RAG Retrieval Pipeline** | **Semantic + keyword hybrid search + reranking. Context injection strategy (prepend/append/dynamic).** |
| **P1** | Knowledge Base Management | Tenant-isolated, ACL-controlled knowledge bases. |
| **P1** | Additional DB Connectors | MySQL, ClickHouse, SQLite connectors. |
| **P1** | API Data Sources | REST/GraphQL declarative config, normalized results. |
| **P1** | Text-to-SQL Pipeline | NL → SQL → result → Agent context. Schema catalog. |
| **P1** | AI Analysis Workbench | Data connection → Chart generation → Report/PPT export. |

**Data Connector Layer:**

```
┌─────────────────────────────────────────────────────────────┐
│                    Data Connector Layer                      │
│                                                             │
│  Unstructured Data              Structured Data              │
│  ├─ Document ingestion          ├─ DB connectors             │
│  │  (PDF/Word/Markdown/HTML)    │  (PG [P0] / MySQL [P1] /  │
│  ├─ Chunking + Embedding        │   ClickHouse [P1] /        │
│  ├─ Vector store (per-tenant)   │   SQLite [P1])             │
│  ├─ RAG retrieval pipeline      ├─ API data sources [P1]     │
│  │  (semantic + keyword hybrid  │  (REST/GraphQL, declarative│
│  │   + reranking)               │   config)                  │
│  ├─ Knowledge base mgmt [P1]    ├─ Data catalog [P1]         │
│  │  (tenant-isolated, ACL)      │  (schema discovery, samples)│
│  └─ Context injection strategy  ├─ Text-to-SQL pipeline [P1] │
│     (prepend/append/dynamic)    │  (NL → SQL → result → ctx) │
│                                 └─ Structured result fmt      │
└─────────────────────────────────────────────────────────────┘
```

**Incremental delivery**: v1.6 delivers the SPI + PG connector + Document Ingestion + RAG pipeline. Additional connectors (MySQL, ClickHouse, etc.) ship as Extension SPIs in subsequent minor releases.

### v1.7 — Enterprise Security, Session DAG & Multi-Run Modes

**Focus**: Enterprise-grade security, non-linear conversations, platform integration points, and DeerFlow runtime removal.

| Priority | Scope | Content |
|----------|-------|---------|
| **P0** | Open API | REST + Webhook: Agent dialogue, workflow trigger, result query; rate limiting, API key management |
| **P0** | Third-Party Integration | Feishu/DingTalk/WeCom/Slack/Teams bidirectional |
| **P0** | SSO/LDAP | Enterprise identity integration, auto-sync org structure to tenants/roles |
| **P0** | **Runtime Security** | **Agent workspace isolation, network policy (default-deny outbound), capability tokens (Agent never sees raw API keys)** |
| **P0** | **Declarative Agent Config** | **Agent as Code (YAML/JSON), GitOps-friendly, version-controlled** |
| **P0** | **Session DAG** | **Tree/DAG-structured conversation sessions. Fork at any point, explore alternative branches, merge or discard. Includes persistent DAG storage — sessions survive process restart.** |
| **P0** | **Multi-Run Modes** | **Interactive (UI), Batch/CI (print/JSON), RPC (cross-process), SDK (embedded). Agent Loop is callable from any mode.** |
| **P0** | **DeerFlow Loop Removal** | **Remove DeerFlow's legacy LangGraph loop. Agent Loop (v1.2) is now the sole execution engine. Existing Skill/Agent compatibility verified through comparison test suite.** |
| **P1** | Multi-Model Routing | Auto-select model by task type/cost/latency |
| **P1** | **Tool Marketplace** | **Tool discovery, distribution, versioning. Tools are platform assets, not per-agent code. Distinct from v1.2 Tool Registry (which handles registration/validation).** |

**Runtime Security — three-layer model:**

| Layer | Capability | Version |
|-------|-----------|---------|
| Perimeter | RBAC, audit trail, user auth, password rotation | v1.0 |
| Compliance | Policy-as-Code, OWASP Top 10, deterministic tool-call interception, tamper-evident audit | v1.4 |
| Runtime | Agent workspace isolation (sandbox per tenant) | v1.7 |
| Runtime | Network policy (default-deny outbound, allowlist) | v1.7 |
| Runtime | Short-lived capability tokens (Agent never sees raw API keys) | v1.7 |
| Runtime | Policy Engine integration with sandbox (permissions verified before every tool call) | v1.7 |
| Runtime | Unified event output (OCSF-compatible for SIEM integration) | v1.7 |

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

**Session DAG migration:**

```
v1.6 and earlier: Linear sessions (list of messages)
v1.7 upgrade:
  ├─ Existing linear sessions: represented as single-branch DAG (root = entire history)
  ├─ New sessions: start from DAG root
  ├─ /fork command: create new branch from current point
  ├─ DAG storage is persistent — branches survive process restart
  └─ No breaking change: linear sessions are a valid DAG subset
```

**Multi-Run Modes:**

| Mode | Interface | Use Case |
|------|-----------|----------|
| **Interactive** | Web UI + WebSocket | Daily use, conversation, exploration |
| **Batch/CI** | CLI `--print` / `--json` | Scripts, CI/CD pipelines, automated reports |
| **RPC** | gRPC / REST endpoint | Cross-process integration, microservices |
| **SDK** | `createAgentSession()` | Embedded in third-party applications |

**Policy Engine in SDK mode:**

| SDK Mode | Policy Engine | When to use |
|----------|--------------|-------------|
| **Embedded** | Policy Engine compiled into SDK binary. YAML policies loaded from local filesystem. Zero network dependency. | Edge deployment, offline use, minimal latency |
| **Remote** | SDK calls platform Policy Engine API. Lighter SDK footprint. | Cloud deployment, centralized policy management |

### v1.8 — Context Engineering

**Focus**: Manage the Agent's context window systematically. Context determines capability ceiling — this is a platform-level concern.

| Priority | Scope | Content |
|----------|-------|---------|
| **P0** | **Context Compression Engine** | **Pluggable compression algorithms. Sliding window (P0, simplest), summarization (P1), semantic pruning (P1). Configurable per agent. Auto-trigger on token threshold. ⚠️ High technical risk — compression quality directly impacts agent output quality.** |
| **P0** | **Token Budget Monitor** | **Current consumption, remaining budget, projected exhaustion. Real-time visualization. Auto-trigger compression when approaching limit.** |
| **P0** | Memory Strategy | Short-term (session), long-term (persistent), semantic (vector retrieval) — configurable per agent |
| **P0** | Context Window Management | Token budget visualization, overflow warnings, automatic truncation |
| **P1** | Cross-Session Continuity | "Continue from last conversation" — context inheritance with decay |
| **P1** | Retrieval Formatting | Structured results → Markdown table / JSON / natural language, configurable formatting |
| **P1** | Prompt Template A/B Branching | Compare prompt variants, data-driven selection |

*(Note: Summarization and semantic pruning are P1 algorithms within the Context Compression Engine P0 above, not separate items.)*

### v1.9 — Observability, SRE Governance & Evaluation

**Focus**: Measure, improve, and protect Agent quality in production.

| Priority | Scope | Content |
|----------|-------|---------|
| **P0** | Agent Runtime Metrics | Success rate, latency, token consumption, user satisfaction |
| **P0** | Workflow Analytics | Bottleneck identification, failure hotspots, optimization suggestions |
| **P0** | **Evaluation Framework** | **Offline eval (test suites, including counterfactual tests — rewriting premises to out-of-distribution forms to verify the agent still reaches correct conclusions; this detects semantic-correlation extrapolation vs true causal reasoning. Harness Engineering ch18: LLMs do Inference (statistical correlation) not Reasoning (causal truth-preservation); silent errors in Chain-of-Thought produce grammatically correct but logically wrong steps with high confidence. Counterfactual testing is the primary detection mechanism.)** |
| **P0** | **Feedback Loop** | **User rating → auto sample collection → prompt/model iteration** |
| **P1** | **Agent Self-Refinement** | **Agent adjusts its own prompt/skill config based on feedback signals. All self-modifications must pass Policy Engine approval before activation (prevents governance bypass via self-editing). Rationale: Pi-Agent enables "agents modify their own capabilities"; this aligns with Data Flywheel but requires governance gate — an agent editing itself is high-risk and must be intercepted.** |
| **P0** | A/B Testing | Compare different prompts/models/processes, data-driven iteration |
| **P0** | Cost Attribution | Tenant/user/agent/workflow four-level cost allocation, budget alerts with auto circuit-breaker |
| **P1** | **OpsinTech Benchmark Suite** | **Standard task set covering governance, workflow, data connector scenarios. Used for cross-version regression testing (like Pi-Agent's TerminalBench, but enterprise-scoped). Target: 50+ benchmark tasks by v1.9 ship.** |
| **P1** | **SLO & Error Budgets** | **Per-agent SLO (latency p95, success rate, token efficiency). Budget exhaustion → auto-degradation.** |
| **P1** | **Chaos Testing** | **Agent fault injection, tool timeout simulation, model hallucination testing, network partition drills** |
| **P1** | **Kill Switch (Per-Agent)** | **Extends v1.3 infrastructure kill switch to per-agent granularity.** |
| **P1** | **Circuit Breaker (SLO-driven)** | **Extends v1.3 circuit breaker: auto-throttle agents exceeding error budget. SLO-driven, not failure-count-driven.** |

**Kill Switch & Circuit Breaker — version evolution:**

| Version | Kill Switch | Circuit Breaker |
|---------|-------------|-----------------|
| v1.3 | Infrastructure-level: stop all workflows per tenant/workflow | Failure-count-based: pause after N consecutive failures |
| v1.9 | Extended to per-agent granularity | Extended to SLO-driven: throttle when error budget exhausted |

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
│  ├─ Kill switch (per-agent, extends v1.3)    │
│  └─ Circuit breaker (SLO-driven, extends v1.3)│
│                                              │
│  Data Flywheel                               │
│  Feedback → Samples → Refine → Deploy        │
└──────────────────────────────────────────────┘
```

### v2.0 — Autonomous Runtime + Identity Mesh + Federation

**Focus**: Architectural independence and cross-organization interoperability.

| Priority | Scope | Content |
|----------|-------|---------|
| **P0** | Autonomous Agent Runtime | Replace DeerFlow dependency entirely. Agent Loop (v1.2), Tool Registry (v1.2), Message System (v1.2), Policy Engine (v1.4) are already decoupled from DeerFlow internals via abstraction layers. Only LangGraph orchestration remains to be replaced to achieve full independence. |
| **P0** | **Identity Mesh** | **SPIFFE/DID/mTLS credentials for every agent. Trust scoring and delegation chain management. "Which agent did this?" answered with cryptographic certainty.** |
| **P0** | **Open Governance Toolkit** | **Policy Engine, RBAC, Audit, and Cost Attribution released as standalone open-source libraries (Apache 2.0). Independent repositories. Platform team maintains.** |
| **P1** | Central Skill Registry | Cross-tenant/cross-organization skill sharing and trading (npm-like, enterprise-grade permissions) |
| **P1** | Agent Federation | Cross-organization Agent interoperability: discovery, auth, permission boundaries, billing, versioning |
| **P1** | Low-Code Workflow Designer | Visual orchestration for non-technical users (drag-and-drop nodes, parameter configuration) |
| **P1** | Edge Deployment | Lightweight runtime deployed to customer environments, data stays on-premises, cloud unified management |

**Open Governance Toolkit — scope:**

| Component | Description | License |
|-----------|-------------|---------|
| `govern-policy-engine` | Deterministic tool-call interception engine. YAML Policy-as-Code evaluator. | Apache 2.0 |
| `govern-rbac` | Multi-tenant role-based access control. Three-tier roles. | Apache 2.0 |
| `govern-audit` | Merkle-tree tamper-evident audit logging. Decision BOM. | Apache 2.0 |
| `govern-cost` | Four-level cost attribution (tenant/user/agent/workflow). Budget alerts. | Apache 2.0 |

Each component is an independent repository, usable standalone or together. The platform itself consumes these libraries (dogfooding).

**Incremental migration strategy:**

```
v1.2: Agent Loop extracted (parallel to DeerFlow, feature-flag toggle)
v1.3: Agent Loop becomes default; DeerFlow loop marked deprecated
v1.4: Policy Engine independent (abstraction layer decoupled from DeerFlow internals)
v1.7: DeerFlow loop removed; only Agent Loop remains
v2.0: LangGraph orchestration replaced (last DeerFlow component)
      → DeerFlow dependency fully removed
```

---

## 3. Technical Architecture

### 3.1 Layered Architecture

Version annotations `[vX.Y]` indicate when each module is introduced. Unmarked modules are present from v1.0.

```
┌──────────────────────────────────────────────────────────┐
│  Access Layer     │ Web Console │ Open API [v1.7] │ A2A  │
│                   │ IM Bot │ CLI [v1.7] │ RPC [v1.7]     │
│                   │ SDK [v1.7] │ Batch [v1.7]            │
├──────────────────────────────────────────────────────────┤
│  Context Layer    │ Compression Engine [v1.8]             │
│  [v1.8]           │ Window Mgmt │ Token Monitor          │
│                   │ Memory Strategy                      │
├──────────────────────────────────────────────────────────┤
│  Core Layer       │ Agent Loop [v1.2] │ Workflow [v1.3]  │
│                   │ Tool Registry [v1.2] │ Saga [v1.3]   │
│                   │ Message System [v1.2] │ Kill Switch  │
│                   │ Skill System │ Model Router          │
├──────────────────────────────────────────────────────────┤
│  Extension Layer  │ Event Hooks [v1.5] │ Skills (lazy)    │
│  [v1.5]           │ Prompt Templates [v1.5]              │
│                   │ Builtin SPI (PolicyEnf) [v1.4]       │
│                   │ Extension SPI (EventSrc/Exec/Notif/  │
│                   │  DataConn [v1.6])                    │
├──────────────────────────────────────────────────────────┤
│  Data Layer       │ RAG Pipeline [v1.6] │ DB Connectors  │
│  [v1.6]           │ Vector Store │ Text-to-SQL [v1.6 P1] │
│                   │ Knowledge Base│ API Sources [v1.6 P1] │
├──────────────────────────────────────────────────────────┤
│  Compliance Layer │ Policy Engine [v1.4] (builtin)       │
│  [v1.4]           │ OWASP Rules │ Tool-Call Interception │
│                   │ Tamper-Evident Audit (Merkle)        │
├──────────────────────────────────────────────────────────┤
│  Governance Layer │ RBAC │ Audit │ Cost │ Quota          │
├──────────────────────────────────────────────────────────┤
│  Infrastructure   │ DB │ Sandbox │ Storage │ MCP │ Vector [v1.6]│
└──────────────────────────────────────────────────────────┘
```

### 3.2 Extension System — Full Architecture

**Two SPI categories:**

| Category | SPI | Toggle | Introduced |
|----------|-----|--------|------------|
| **Builtin** | PolicyEnforcer | Always on, strictness configurable | v1.4 |
| Extension | EventSource | Config toggle | v1.1 |
| Extension | Executor | Config toggle | v1.1 |
| Extension | Notifier | Config toggle | v1.1 |
| Extension | DataConnector | Config toggle | v1.6 |
| Extension | EventHook | Hot reload | v1.5 |

**Plugin SPIs:**

```python
# === BUILTIN (always on, not optional) ===

# PolicyEnforcer (v1.4): deterministic tool-call governance
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

# DataConnector (v1.6): external data access
class DataConnector(Protocol):
    async def connect(self, config: DataSourceConfig) -> Connection: ...
    async def query(self, query: Query, ctx: QueryContext) -> QueryResult: ...
    async def schema(self) -> Schema: ...

# EventHook (v1.5): agent lifecycle event subscription
# NOTE: Hooks can augment context but CANNOT veto tool calls.
#       Only PolicyEngine can deny. This is by design.
class EventHook(Protocol):
    async def on_tool_call_before(self, ctx: ToolContext) -> ToolContext | None: ...
    async def on_tool_call_after(self, ctx: ToolContext, result: ToolResult) -> None: ...
    async def on_turn_start(self, ctx: TurnContext) -> None: ...
    async def on_turn_end(self, ctx: TurnContext) -> None: ...
    async def on_error(self, ctx: ErrorContext) -> ErrorAction: ...
    async def on_session_start(self, ctx: SessionContext) -> None: ...
    async def on_session_end(self, ctx: SessionContext) -> None: ...
    async def on_stop(self, ctx: StopContext) -> StopDecision: ...  # task completion verification (v1.5)
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
| `policy-owasp` | Builtin (PolicyEnforcer) | v1.4 | OWASP Top 10 compliance rules |
| `mcp-security-gateway` | Builtin (PolicyEnforcer) | v1.4 | MCP tool poisoning detection, drift monitoring |
| `data-connector-pg` | Extension (DataConnector) | v1.6 | PostgreSQL connector (reference implementation) |
| `data-connector-mysql` | Extension (DataConnector) | v1.6+ | MySQL connector |
| `data-connector-clickhouse` | Extension (DataConnector) | v1.6+ | ClickHouse connector |
| `knowledge-base` | Extension (DataConnector + Executor) | v1.6 | RAG retrieval, vector search |
| `approval-engine` | Extension (Executor) | v1.7 | Multi-level approval workflows |
| `compliance-scanner` | Builtin (PolicyEnforcer) | v1.7 | Sensitive data detection, policy compliance |

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
| Agent Loop extraction | v1.2: abstraction layer over LangGraph (decoupling). v1.3: becomes default. v1.7: DeerFlow loop removed. v2.0: LangGraph replaced entirely. | Gradual decoupling→replacement; v1.2 is NOT independence from LangGraph, only decoupling |
| Workflow engine | Self-developed DAG + Saga (idempotent retry + selective compensation); Agent Loop as execution unit | Keep orchestration controllable; Agent Loop is decoupled from (not independent of) Workflow |
| Agent Loop vs Workflow | Coexistence, not competition | Agent = "employee", Workflow = "project manager" |
| Governance model | Three-layer: Perimeter (v1.0) + Compliance (v1.4) + Runtime (v1.7) | Defense in depth; NVIDIA + Microsoft AGT |
| Policy enforcement | Deterministic code-level interception; always-on builtin, not optional plugin | Microsoft AGT: "Model-layer defenses are probabilistic" |
| Policy Engine deployment | Platform embedded (default), SDK embedded (offline), SDK remote (lightweight) | Three deployment modes for different use cases |
| Event Hooks vs Policy Engine | Hooks can augment, cannot veto. Policy Engine is final authority. | Separation of concerns: extensibility ≠ governance |
| Policy language | YAML-based declarative policies | Industry standard (Microsoft AGT, Kubernetes); GitOps-friendly |
| Policy transition | OWASP high-severity: default deny. Custom: default allow → user writes policies. | Safe migration: no breaking change, progressive hardening |
| Extension system | Two SPI categories: Builtin (always on) + Extension (optional) | Governance is not optional; everything else is |
| Skill loading | Progressive disclosure (lazy-load); v1.5 upgrade: existing preload, new lazy; v1.7: all lazy | Backward compatible; cross-skill reference detection |
| Tool Registry vs Tool Marketplace | Registry (v1.2): register/discover/validate. Marketplace (v1.7): distribute/version/rate. | Different concerns: registration ≠ distribution |
| Prompt Template delivery | Complete system in v1.5 (variable injection, version mgmt, per-tenant defaults, slash-command). A/B branching in v1.8 (P1). | Not fragmented across versions |
| Kill Switch & Circuit Breaker | v1.3: infrastructure-level. v1.9: extended to per-agent + SLO-driven. | Progressive enhancement, not redefinition |
| Session model | DAG/tree structure with persistent storage. Linear sessions migrate as single-branch DAG. | Pi-Agent: fork/resume/compare is essential |
| Run modes | Four modes: Interactive, Batch/CI, RPC, SDK | Pi-Agent: same Agent Loop, different interfaces |
| Cross-organization federation | Identity mesh (SPIFFE/DID/mTLS) + OAuth2 REST | Microsoft AGT identity model |
| Context engineering | Platform layer, not per-agent | Context is shared concern |
| Evaluation framework | Offline + Online + Human annotation + SRE governance | Full-lifecycle quality measurement |
| Audit structure | Merkle-tree tamper-evident logs + Decision BOM | Microsoft AGT audit model |
| Open Governance Toolkit | 4 independent Apache 2.0 libraries; separate repos; platform team maintained | Microsoft AGT precedent; dogfooding |

---

## 4. Risks & Migration

### 4.1 Main Risks

| Risk | Impact | Mitigation |
|------|--------|------------|
| Agent Loop extraction breaks DeerFlow integration | Agent execution fails during transition | Parallel run with feature-flag toggle; automated comparison testing; v1.3 Agent Loop becomes default; v1.7 DeerFlow loop removed |
| Policy engine performance overhead | Tool-call latency increase | Deterministic (no LLM call); target <1ms overhead; Rust core option for hot path |
| Extension system complexity | Five levers may overwhelm users | Each lever independently usable; start with Plugins + Skills (v1.1/v1.5), add Hooks incrementally |
| Workflow engine and Agent Loop state inconsistency | Agent executing when Workflow restarts | Workflow only stores "invocation handle"; Agent Loop state managed independently; Saga retries/compensates |
| Skill lazy-loading breaks cross-skill references | Skill A's instructions reference Skill B's tools | v1.5 auto-detects cross-skill tool references; existing skills preload by default; v1.7 all lazy |
| Context engineering scope creep | v1.8 becomes overloaded | Only 4 P0s defined; compression engine, token monitor, memory strategy, window management |
| Data connector security | Tenant data leakage | Per-tenant vector store isolation; Text-to-SQL logged and schema-access controlled; Policy engine wraps all data access |
| A2A protocol fragmentation | Incompatible with Google's A2A | Monitor standardization; protocol adapter pattern for backend swap |
| Compliance rule maintenance | OWASP Top 10 evolves | Community-contributed rule packs; policy lint; versioned rule sets |
| Federated ecosystem trust model | v2.0 delayed | v1.7 first implement "cross-tenant" federation; v2.0 extend to "cross-platform" via identity mesh |
| Autonomous runtime replacement | Existing Skill/Agent incompatible | API compatibility layer; migration tools; LTS version maintained in parallel for 6 months |
| **DeerFlow upstream maintenance risk** | DeerFlow (ByteDance) stops maintenance or pivots; v1.2–v1.7 depend on it | Agent Loop abstraction (v1.2) decouples platform code from DeerFlow internals; earlier extraction = lower risk; v2.0 fully removes dependency |
| **Vector store scalability wall** | pgvector performance degrades at >10M vectors; users hit a wall after v1.6 deployment | v1.6 ships pgvector only; document the scalability ceiling; Milvus/Qdrant support as P1 in v1.6+ minor release; migration path documented |

### 4.2 Migration Path

```
v1.0 → v1.1: Zero migration, ops plugins enabled by default, behavior unchanged.

v1.1 → v1.2: Agent Loop extracted as abstraction layer over LangGraph (parallel to existing DeerFlow loop, feature-flag toggle).
              Tool Registry + Message System are additive. Default: DeerFlow loop. Opt-in: Agent Loop abstraction.

v1.2 → v1.3: Agent Loop becomes default; DeerFlow loop marked deprecated.
              Workflow engine, Saga, kill switch, circuit breaker are additive.
              Existing workflows continue to work.

v1.3 → v1.4: Policy Engine deployed as builtin (always on).
              OWASP high-severity rules: default deny (platform-managed).
              Custom policies: default allow (tenant writes their own).
              agt verify shows policy coverage gaps. No breaking change.

v1.4 → v1.5: Custom Agent upgraded to "full framework".
              Extension system: Builtin SPIs + Extension SPIs + Event Hooks + Skills (lazy) + Templates.
              Skills: existing preload by default, new lazy by default.
              Cross-skill reference detection warns before lazy-loading.
              Prompt Template system delivered complete (variable injection, version mgmt, per-tenant defaults).
              A2A enabled per-tenant.

v1.5 → v1.6: Data Connector SPI + PG connector + Document Ingestion + RAG pipeline.
              Additional connectors (MySQL, ClickHouse, etc.) ship as subsequent Extension SPIs.
              Vector store infrastructure added (pgvector default).
              AI Analysis Workbench enabled per-tenant (if P1 delivered).

v1.6 → v1.7: DeerFlow loop removed; only Agent Loop remains (v1.2 Agent Loop is now the sole execution engine).
              Session DAG is additive (linear sessions migrate as single-branch DAG).
              DAG storage is persistent — branches survive process restart.
              Multi-run modes are additive (web UI still primary).
              Open API + runtime security disabled by default.
              Agent as Code is additive. Skill preload flag deprecated (all skills now lazy).

v1.7 → v1.8: Context engineering is additive. Existing agents use default strategies.
              Compression engine, token monitor, memory strategy. Prompt Template A/B branching is opt-in (P1).

v1.8 → v1.9: Observability data auto-collected.
              SLO, chaos testing, kill switch (per-agent), circuit breaker (SLO-driven) enabled per-tenant.
              Historical data not backfilled.

v1.x → v2.0: Agent Loop, Tool Registry, Message System, Policy Engine already decoupled from DeerFlow internals from v1.2–v1.4.
              Only LangGraph orchestration remains to be replaced (the sole remaining DeerFlow dependency).
              Grayscale migration. Identity mesh is additive.
              Open Governance Toolkit released as 4 separate Apache 2.0 repos.
```

### 4.3 Success Metrics

| Version | Technical | Performance | Community |
|---------|-----------|-------------|-----------|
| v1.1 | Plugin toggle test pass rate 100%; README narrative published | Plugin toggle latency <10ms | — |
| v1.2 | Agent Loop operates as abstraction layer over DeerFlow/LangGraph (decoupled, not independent); comparison tests pass | Agent Loop latency parity with DeerFlow (±5%) | First external contributor PR merged |
| v1.3 | 5 workflow templates; 1000 concurrent workflows; Saga idempotent retry + selective compensation verified; kill switch stops workflows within 5s | Workflow step transition <100ms | — |
| v1.4 | OWASP Top 10 compliance coverage 100%; tamper-evident audit verified | Policy evaluation <1ms per tool call | — |
| v1.5 | 20+ skills in official library; 5 extension levers operational; trust scoring visible (if P1 delivered) | Skill lazy-load <500ms | Monthly active tenants > baseline |
| v1.6 | PG connector operational; RAG pipeline with hybrid search + reranking | RAG retrieval <2s p95 | — |
| v1.7 | Session DAG operational (fork/resume/compare); 4 run modes operational; ≥1 IM integration launched; runtime security policies enforceable | DAG fork <100ms; capability token issuance <50ms | — |
| v1.8 | ≥1 compression strategy (sliding window) operational; token budget monitor real-time | Compression <500ms per trigger; token count accuracy 99% | — |
| v1.9 | Cost attribution accuracy 95%+; SLO definition operational; chaos testing 10+ failure modes | Evaluation pipeline <5min per test suite | NPS > baseline |
| v2.0 | Federation verified across 2 independent instances; identity mesh operational; DeerFlow fully replaced | Migration downtime <5min per tenant | Open governance toolkit has ≥3 external contributors |

### 4.4 Non-Functional Requirements (All Versions)

| Category | Requirement | Measured By |
|----------|-------------|-------------|
| **Security** | Annual third-party penetration test (starting v1.4) | Penetration test report |
| **Security** | No critical vulnerabilities in dependencies | Dependabot / OWASP Dependency Check |
| **Performance** | Agent Loop latency <2x baseline after each version upgrade | Automated benchmark suite |
| **Performance** | API p95 latency <500ms for non-streaming endpoints | Production monitoring |
| **Reliability** | Platform uptime ≥99.5% (self-hosted, depends on infra) | Health check monitoring |
| **i18n** | All new UI features support 4 languages (EN, ZH, JA, KO) | i18n coverage check in CI |
| **Upgrade** | Each version upgrade completes in <30 min downtime | Upgrade runbook timing |
| **Backward compat** | No breaking API changes without deprecation notice + 1 version grace period | API compatibility test suite |

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
| **Data Flywheel** | Feedback → sample collection → prompt/model refinement → redeployment → more feedback |
| **Policy as Code** | Declarative YAML policies defining agent behavior boundaries; version-controlled, reviewable, GitOps-friendly |
| **Decision BOM** | Bill of Materials for every governance decision: active policy, agent request, allow/deny reason — cryptographically verifiable |
| **Saga** | Idempotent retry + selective compensation pattern. Each step has idempotent retry with exponential backoff; steps with reversible side effects (e.g., sent notifications) support compensating rollback; steps with irreversible side effects (e.g., executed SQL) support retry only. Most Agent workflow steps support retry, not compensation. |
| **Identity Mesh** | SPIFFE/DID/mTLS-based identity layer answering "Which agent did this?" with cryptographic certainty |
| **Kill Switch** | Emergency stop mechanism. v1.3: infrastructure-level (workflow/tenant). v1.9: extended to per-agent granularity. |
| **Circuit Breaker** | Auto-throttle mechanism. v1.3: failure-count-based. v1.9: extended to SLO-driven. |
| **Agent Loop** | The think→act→observe→think cycle that is the core of any Agent. In v1.2–v1.7, it is an abstraction layer over LangGraph (decoupling platform code from LangGraph-specific APIs). In v2.0, LangGraph is replaced by an autonomous runtime, making the Agent Loop truly independent of any orchestration framework. |
| **Progressive Disclosure** | Skills load metadata (name + description) eagerly, full instructions + tools only when invoked. Reduces context pollution. |
| **Session DAG** | Non-linear conversation structure: fork at any point, explore alternatives, keep or discard branches. Sessions are graphs, not lists. Persistent storage — survives process restart. |

### 5.2 References

- Current README: `README.md`, `README_zh.md`
- Previous roadmaps: `docs/superpowers/specs/2026-07-19-governed-agent-platform-roadmap-design.md`, `v2`, `v3`, `v4`, `v5`
- DeerFlow upstream: https://github.com/bytedance/deer-flow
- Pi-Agent (64K+ Stars): https://dg-ai-notes.pages.dev/modules/ch01-overview/
- Microsoft Agent Governance Toolkit: https://github.com/microsoft/agent-governance-toolkit
- NVIDIA Enterprise AI Factory: https://developer.nvidia.com/blog/how-to-govern-autonomous-agents-in-enterprise-ai-factories/
- Google Gemini Managed Agents: https://www.eigent.ai/zh-TW/blog/gemini-managed-agents-explained
- LangChain Governed Agents: https://www.langchain.com/blog/building-governed-agents-a-framework-for-cost-control-and-compliance
- AI Agent Book (bojieli): https://bojieli.github.io/ai-agent-book/
- Alibaba Cloud 2025 AI Architecture: https://www.aliyun.com/reports/2025-ai-architecture
