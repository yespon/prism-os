# AgentOS 白皮书与 PrismOS 双向校验报告

> 文档性质：战略与架构审计、现状能力基线、差距分析、实施路线建议
> 审计日期：2026-08-08
> 项目基线：`prism-platform` `main` 分支，提交 `a58d461`，标签 `v0.1.0-alpha.2`
> 原始白皮书：`/Users/yespon/Downloads/whitepaper-agentos.md`
> 正式重构稿：`/Users/yespon/Documents/AgentOS/whitepaper-agentos-restructured.md`

---

## 1. 执行摘要

### 1.1 核心结论

原始白皮书中的战略判断基本成立：企业需要的不是另一个 Agent Framework、聊天界面或垂直自动化产品，而是一层统一管理 Agent 身份、能力、执行、状态、策略、责任和持续改进的治理与执行平台。

正式重构稿已经正确完成了最重要的战略收敛：

- 将产品定位从 Agent Platform、Workflow、iPaaS、数字员工和 Marketplace 的混合体，收敛为企业级 Agent 治理与执行平台；
- 将路线从 Feature Driven 改为 Capability Driven；
- 将 Workflow、Marketplace、Runtime 替换和 Federation 放回合理边界；
- 将 AI 运维定义为验证场景，而不是平台本体；
- 明确区分 Agent、Skill、Tool、Plugin、Connector、Knowledge、Memory、Artifact、Policy 和 Evaluation。

因此，本报告的总体判定是：

> **白皮书可以作为 PrismOS 的长期战略和目标架构源，但还不能直接作为工程 Backlog。正式实施前，必须把核心对象、执行生命周期、Policy 决策、Approval、Audit Event 和 Evaluation 验收机制冻结成平台契约。**

PrismOS 也不是从零开始。项目已经具备多租户、RBAC、模型配置、Skill、MCP、沙箱、文件与存储、Agent 配置、Memory、Checkpoint 和垂直场景审批等基础。真正缺少的不是更多页面或业务模块，而是连接现有能力的治理与执行中轴：

```text
Identity
   ↓
Policy Decision / Enforcement
   ↓
Task / Run / Action
   ↓
Approval（必要时）
   ↓
Artifact / Audit / Trace
   ↓
Evaluation / Promotion / Rollback
```

推荐路线不是继续扩展旧 v6 Roadmap，也不是立即替换 DeerFlow/LangGraph，而是：

1. 先冻结资源与执行契约；
2. 建立 Policy、Approval 和统一 Audit；
3. 建立一等 Task/Run/Action 生命周期；
4. 以适配器隔离现有 Runtime；
5. 再建设 Agent Version、Workflow、Evaluation、Connector 和扩展供应链；
6. 仅在证据满足时启动 Runtime Independence 和 Federation。

AI 运维可以继续作为产品楔入，但只能用于验证平台原语。告警、事件、诊断、修复和 On-call 等领域对象必须留在 AIOps 插件中，不能进入平台核心 Schema。

### 1.2 判定总览

| 审查项 | 判定 | 说明 |
|---|---|---|
| 战略方向 | 成立 | “治理与执行平台”定位清晰，市场问题真实 |
| 目标架构 | 基本成立 | 六层架构与横向治理自洽，但若干契约仍停留在概念层 |
| 逻辑严密性 | 有条件成立 | 存在 Evaluation 时序、阶段一 Run 身份、Registry/Lifecycle 等矛盾 |
| 工程可行性 | 可行但工作量大 | 可复用现有基础，关键难点是跨模块契约和数据迁移，不是 UI |
| 近期产品可行性 | 较高 | AI 运维能提供高价值、高风险、可验证的受控执行场景 |
| Runtime 自研 | 暂不构成立项条件 | 应先建立适配契约和替换证据 |
| Marketplace | 近期不成立 | 缺少稳定 SDK、包生命周期、签名、兼容性和质量治理 |
| Federation | 仅长期条件项 | 缺少跨组织需求、信任、责任、审计交换和结算前提 |

---

## 2. 审计范围、方法与证据边界

### 2.1 审计对象

本次审计同时使用四类输入：

1. **原始白皮书草稿**：用于确认最初问题意识、战略批判和长期设想；
2. **正式重构稿**：用于审查当前目标架构、对象模型和 Capability Roadmap；
3. **PrismOS 代码与项目文档**：用于确认已实现、部分实现和缺失能力；
4. **旧 Roadmap v6**：用于判断既有工程计划是否仍与白皮书一致。

### 2.2 证据分级

| 等级 | 认定方式 | 本报告中的措辞 |
|---|---|---|
| A：代码事实 | 存在数据模型、服务、API、运行链或测试证据 | 已实现、已有基础 |
| B：可复用原型 | 只在单一垂直场景或局部链路成立 | 部分实现、原型、技术种子 |
| C：文档或 UI | README、路线图、页面存在，但缺少平台契约 | 已规划、已有界面，不代表交付 |
| D：目标能力 | 只存在于白皮书 | 缺失、待建设、条件项 |

本报告严格避免以下等价关系：

- LangGraph `thread_id` 或内部 Run 不等于平台一等 `Task/Run`；
- Terminal 的命令确认不等于通用 `Approval`；
- Guardrail Provider 不等于完整 `Policy Engine`；
- JSONL 管理审计不等于全链路 Audit；
- Plugin Protocol 不等于可分发 Plugin SDK；
- 配置中的版本字段不等于不可变资源版本和发布历史；
- 文件下载能力不等于具备 Lineage、Retention 和 Policy 的 Artifact Store。

### 2.3 验证限制

- 本轮进行了代码与文档的静态证据审查，没有重新运行完整后端测试套件；
- 项目发布说明记录：可收集 `1173` 个测试，历史完整套件基线为 `973 passed, 18 skipped, 184 failed`；
- 因此不能把当前项目描述为“测试全部通过”或“生产就绪”；
- 本报告不采用未在本轮本地证据中复核的依赖漏洞数量。

---

## 3. 原始白皮书结构诊断

### 3.1 原稿不是单一、可发布的白皮书

原始文件共 62,352 行，实际是多轮 ChatGPT 产物、路线图评论、正文版本和附录素材的拼接语料库，而不是一个逻辑连续的单一版本：

- 约第 1–839 行：对旧 Roadmap 的批判性审查；
- 约第 840 行起：能力演进重构方案；
- 约第 3,590 行起：英文白皮书正文；
- 约第 4,687–34,715 行：第 3–27 章，存在标题和整章重复；
- 约第 34,737 行后：附录 A–V，混入大量远期架构与商业设想；
- `End of White Paper` 分别出现在第 34,715 和 62,342 行。

典型重复包括：

- `03 Why Enterprise Needs Agent OS`：第 4,687、4,700 行；
- `04 Market Positioning`：第 5,676、5,690 行；
- `PART II`：第 7,541、7,556 行；
- `06 Overall Architecture`：第 7,543、7,558 行。

因此，原稿不适合继续做逐句润色，也不能被当作单一需求规格。正确使用方式是：

| 原稿区段 | 建议用途 |
|---|---|
| 前约 1,000 行 | 战略校正层，保留其批判和能力演进判断 |
| 约 3,590–34,715 行 | 架构素材库，选择性吸收，不视为全部承诺 |
| 第 34,737 行后 | 远期研究库，需通过条件门后才能进入 Roadmap |

正式重构稿将这些内容压缩为 19 章和 6 个附录，方向正确，也更适合作为唯一正式母本。

### 3.2 原稿最有价值的战略校正

原稿前部对旧路线的批评应继续保留，其核心判断包括：

- 产品定位曾同时跨越 Agent Platform、Workflow、iPaaS、AI Employee 和 Marketplace；
- Workflow、Marketplace、Federation 被放得过早；
- Skill、Tool 和 Workflow 边界不清；
- Digital Employee 不应成为平台核心对象；
- 自研 Runtime 不具有天然战略价值；
- 缺少 Policy、Secret、Artifact、Execution State、Knowledge、Plugin SDK 和 Evaluation；
- 最大风险是 Feature Driven，而不是 Capability Driven；
- 合理演进应遵循 Foundation → Agent Runtime → Execution → Governance → Ecosystem，但 Governance 的最小契约必须从 Foundation 开始。

### 3.3 原稿中不应直接继承的内容

以下内容适合作为长期研究方向，不适合作为当前承诺：

- 将数字员工组织、自治企业或全球 Agent 网络作为近期产品对象；
- 在稳定对象模型和扩展供应链之前建设公共 Marketplace；
- 在没有真实跨组织参与方和责任模型时建设 Federation；
- 在缺少替换收益与兼容测试时自研完整 Runtime；
- 用大量未经基线测量的并发、时延、可用性和覆盖率数字定义版本成功。

---

## 4. 正式白皮书逻辑审查

### 4.1 已经成立的逻辑主干

正式稿的下列设计可以作为长期架构原则保留：

1. **定位清晰**：Agent OS 是企业 Agent 的治理与执行平台，不是模型、Framework、Workflow 或垂直业务系统；
2. **智能与执行分离**：概率性判断由模型承担，确定性状态、权限、重试、审批和审计由平台承担；
3. **声明与运行分离**：定义资源与运行实例不能相互覆盖；
4. **横向治理**：Security、Policy、Audit、Observability、Evaluation 和 Cost 贯穿各层；
5. **对象边界较完整**：Agent/Identity、Skill/Tool/Plugin/Connector/MCP、Knowledge/Memory/Context/Artifact 已有清晰区分；
6. **执行边界合理**：Agent 负责理解和动态判断，Workflow 负责确定性编排，Execution Engine 负责可靠执行；
7. **生态顺序合理**：官方库 → 企业内部目录 → 合作伙伴 → 公共 Marketplace；
8. **远期能力降级正确**：Federation 被定义为有前置条件的长期方向；
9. **审计原则正确**：记录执行事实、数据来源、调用、决策和结果，不把隐藏思维链作为企业审计要求；
10. **AIOps 边界正确**：研发运维只是企业场景之一，高风险动作仍受 Policy 和审批控制。

### 4.2 阻断实施的问题

以下问题不影响白皮书的战略价值，但会导致不同团队实现出互不兼容的对象和 API，必须在编码主链前解决。

#### B1. 核心聚合关系尚未冻结

白皮书列出了 Agent、Agent Identity、Task、Run、Workflow、Approval、Artifact 等对象，但没有回答：

- 一个 Task 能否包含多个 Run？
- 重试是同一个 Run 的 Attempt，还是新 Run？
- Workflow Run 与 Agent Run 是继承、包含还是关联关系？
- Approval 绑定 Plan、Action、Run 还是 Policy Decision？
- Artifact 属于 Task、Run、Action 还是 Workflow Step？
- Agent Version 如何被历史 Run 不可变引用？

建议先冻结最小关系：

```text
Task 1 ── N Run
Run  1 ── N Action / Event / Artifact
Run  N ── 1 AgentVersion 或 WorkflowVersion
PolicyDecision N ── 1 Action/Transition
Approval 0..N ── 1 PolicyDecision
Run/Action ── references ── WorkloadIdentity
```

#### B2. Policy 仍是概念，不是决策契约

白皮书给出了 Definition → PDP → PEP → Decision → Audit 链路，但没有最小请求、结果、组合规则、默认策略和版本语义。

建议冻结最小接口：

```text
PolicyRequest
  = subject + action + resource + context

PolicyDecision
  = allow | deny | require_approval
  + reason_code
  + policy_id / policy_version
  + obligations
  + decided_at
```

还必须明确：

- 无匹配策略时是默认拒绝还是按风险域决定；
- 多策略冲突时 Deny、Require Approval 和 Allow 的优先级；
- Policy 版本是否随 Run 固化；
- PEP 覆盖哪些动作和状态迁移；
- 决策失败时哪些链路 Fail Closed；
- 决策和审批怎样进入统一 Audit。

#### B3. 阶段一与阶段二存在执行身份矛盾

阶段一要求“每次生产执行都有可追踪身份”，阶段二才引入 Task 和 Run。没有最小 Execution Envelope，阶段一无法表达工作负载身份、执行版本、Policy Decision 和审计关联。

修订方式不是把完整 Execution Engine 提前，而是在阶段一引入最小信封：

```text
ExecutionEnvelope
  = task_id + run_id + tenant_id + environment_id
  + initiator_identity + workload_identity
  + definition_ref + correlation_id
```

#### B4. Evaluation 的架构地位与交付时序冲突

白皮书将 Evaluation 定义为全生命周期能力，却到阶段四才建设完整体系。这样早期 Agent、Tool、Policy 和 Runtime 变化没有可信晋级门。

应拆为三层：

1. **阶段零/一**：Schema、状态机和策略契约的确定性验收；
2. **阶段二/三**：Agent/Tool 场景数据集、回归和安全测试；
3. **阶段四**：线上质量、业务价值、漂移、成本和组合运营。

### 4.3 重要但不阻断概念验证的问题

#### I1. Agent Registry 与 Lifecycle 混杂

建议拆分为：

- `AgentDefinition`：目标、配置和依赖；
- `AgentVersion`：不可变发布快照；
- `AgentDeployment/Binding`：版本在环境、租户和策略下的激活关系。

Registry 负责发现与索引，Lifecycle 负责状态迁移和发布门，二者不能由一张可变配置表代替。

#### I2. “一切皆资源”表达过宽

并非每条 Token、内部推理片段或瞬态对象都需要完整 CRUD、版本和生命周期。建议改为：

> 可治理定义和影响业务结果的运行实例，采用统一资源元数据与引用语义。

#### I3. Runtime Independence 不应是固定版本承诺

Runtime 替换是成本手段，不是用户价值。白皮书应先要求稳定 Runtime Adapter，再根据性能、可靠性、许可证、上游风险和缺失能力决定是否替换。

#### I4. Federation 应从“阶段”改为“条件投资项”

只有同时出现跨组织真实交易、互认证、责任边界、审计交换、SLA 和结算需求时，Federation 才进入投资组合。否则 Connector + API + 合同 + 人工审批更经济。

### 4.4 建议性修订

- 区分“参考架构中的完整能力”和“当前阶段必须交付的最小切片”；
- 为核心对象增加状态机、幂等键、版本引用和租户边界；
- 为 Artifact 增加 Provenance、Checksum、Retention、Classification 和 Policy Link；
- 为 Approval 增加请求者、授权人规则、过期、委托、撤销和决策证据；
- 为 Audit 定义事件 Envelope，而不仅是字段清单；
- 把 Stop、Cancel、Suspend、Kill Switch 的语义分开；
- 把 Secret 定义为独立平台契约，避免把 MCP `env/headers` 当作 Secret Manager；
- 将性能和规模目标改为“先测量基线，再设 SLO”，避免无证据指标。

---

## 5. 可行性评估

### 5.1 技术可行性

**判定：可行。**

白皮书没有要求依赖尚不存在的基础技术。身份、策略、状态机、事件、对象存储、沙箱、工作流、评估和可观测性都有成熟工程范式。主要技术风险来自跨模块语义一致性，而不是某一个算法无法实现。

最困难的部分依次是：

1. 在不破坏兼容性的前提下建立统一 Task/Run/Action 和 Audit；
2. 把 RBAC、Tool Guardrail、审批和运行状态统一到一个 Policy/Approval 语义；
3. 保证重试、恢复、审批恢复和外部副作用之间的幂等性；
4. 建立定义版本、运行引用、Evaluation 和发布晋级闭环；
5. 让垂直插件只依赖平台核心，而不是反向污染核心。

### 5.2 工程可行性

**判定：有条件可行。**

PrismOS 当前基础可显著降低从零建设成本，但工程质量还不能支持同时铺开 Policy、Workflow、Marketplace 和 Runtime 重写。历史测试基线仍有 184 个失败，意味着每个基础契约改动都可能与 DeerFlow 兼容层产生回归。

实施应采用以下约束：

- 每次只增加一个平台不变量；
- 先以旁路记录和适配器接入，再迁移为唯一写路径；
- 数据模型只做向前兼容迁移；
- 保留 `deerflow` import、API、数据库表、Alembic migrations 和历史数据路径；
- `OPSINTECH_*` 与 `.opsintech` 只作为兼容输入，不继续扩散；
- 不以“大版本重写”解决架构边界问题。

### 5.3 产品可行性

**判定：近期较高，长期取决于治理价值能否被验证。**

AI 运维是合理楔入，原因不是它代表平台本体，而是它同时具备：

- 高频事件和长任务；
- 多数据源、多工具和外部副作用；
- 明确的低、中、高风险操作；
- 天然需要审批、暂停、恢复、审计和回放；
- 可测量的时延、采纳率、误报率和变更结果。

如果平台原语能在该场景成立，又不包含 AIOps 专用字段，就具备向研发、客服、财务和业务运营复用的证据。

### 5.4 商业与生态可行性

**判定：基础平台可验证，公共生态暂不应承诺。**

近期商业价值应来自：

- 私有部署与企业控制；
- 受控 Agent 执行；
- 审批、审计、评估和成本治理；
- 将企业已有模型、MCP、数据与系统组织到统一运行链。

Marketplace、开放治理工具包、跨组织网络等需要活跃开发者、稳定 SDK、内容供给和商业责任机制，不能通过先做上传页面获得。

---

## 6. PrismOS 当前架构与能力基线

### 6.1 当前运行架构

```text
Browser
  → Nginx :2026
     ├─ Next.js :3000
     ├─ FastAPI Gateway :8001
     └─ LangGraph :2024
          → DeerFlow-compatible harness
          → Sandbox / Tools / Memory / Artifact
```

项目当前是建立在 DeerFlow/LangGraph 执行基础上的治理平台 Alpha，而不是独立 Agent Runtime。README 已正确披露这一边界。

### 6.2 能力成熟度总表

| 能力域 | 当前判定 | 主要证据 | 与白皮书关系 |
|---|---|---|---|
| Tenant / User / RBAC | 已有基础 | 租户头解析、Membership、平台/租户管理员检查 | 可复用为 Human Identity 和租户边界 |
| Agent Definition | 部分实现 | `CustomAgent`、租户化 CRUD、DB-first 配置 | 缺 Version、Deployment、生命周期和历史引用 |
| Agent Identity / Workload Identity | 缺失 | 现有用户/Agent 字段不构成独立身份契约 | 必须新建 |
| Model Provider | 已有基础 | DB 配置和租户分配 | 需补版本、策略和成本关联 |
| Skill | 已有基础 | Scope、instructions、版本字段、导入和管理 | 需补不可变版本、依赖和 Evaluation |
| MCP | 已有基础 | 租户配置、OAuth 字段、健康状态 | 需接 Secret、Policy、Capability Registry |
| Tool / Capability Registry | 部分实现 | Runtime Tool 与 MCP 可用，但缺统一治理资源 | 需要统一 Schema、风险和版本 |
| Sandbox | 已有适配基础 | local、Docker、可选 Kubernetes | local 不构成生产隔离；需网络、凭证和资源策略 |
| File / Storage | 较强基础 | FileObject、Checksum、local/S3/JuiceFS Provider | 可演进为 Artifact，但需 Lineage/Retention/Policy |
| Knowledge / Memory / Context | 部分实现 | Memory、Context compression、线程文件 | 缺统一知识治理和权限检索契约 |
| Checkpoint / Durable State | 已有设施 | memory/sqlite/postgres checkpointer | 可复用，但不等于业务 Task/Run |
| Policy / PEP | 技术种子 | Pre-tool Guardrail Provider、Middleware、Fail Closed | 缺 Registry、PDP 语义、审批决策和统一审计 |
| Approval | 垂直原型 | Terminal 风险分级、LangGraph interrupt/resume | 需抽象为通用资源和状态机 |
| Audit | 部分实现且割裂 | 管理 JSONL、Terminal 独立审计表 | 需统一 Event Envelope 和执行链 |
| Task / Run / Action | 核心缺失 | 仅有 LangGraph Run、thread 和 `SubagentRun` | 必须优先建立平台对象 |
| Workflow | 缺失 | 有事件/图执行代码，无通用 Definition/Version/Run | 必须建立在 Task/Run 之后 |
| Observability / Cost | 部分实现 | Token 日志、LangSmith/运行事件等局部能力 | 缺统一关联、指标和归因 |
| Evaluation | 缺失 | 无通用 Dataset/Eval Run/Score/Promotion | 需要分层提前建设 |
| Plugin SDK | 接口草图 | EventSource/Executor/Notifier Protocol、静态三插件 | 缺发现、安装、版本、依赖、签名、隔离和生命周期 |
| Connector Contract | 缺失 | MCP 与垂直集成不等于统一 Connector | 中期建设 |
| Runtime Adapter | 部分实现 | LangGraph/DeerFlow 兼容层和 Provider 抽象 | 先稳定契约，不急于替换 |
| Federation | 缺失 | 无跨组织身份、信任和交换模型 | 长期条件项 |

### 6.3 关键代码事实

#### 身份和权限

- `backend/app/gateway/auth.py:111–165`：解析租户头、Membership 和租户角色；
- `backend/app/gateway/auth.py:168–280`：认证和租户上下文注入；
- `backend/app/gateway/authorization.py:7–87`：平台管理员、租户管理员和配置写权限。

这证明租户和人类用户 RBAC 基础真实存在，但不能替代 Agent Identity、Service Identity、Workload Identity 或 ABAC/Policy。

#### Agent 配置

- `backend/app/models/agents.py:18–49`：`CustomAgent` 保存模型、工具组、Prompt、Skill 和启用状态；
- `backend/app/gateway/routers/agents.py:164–205,269–333`：租户感知查询和创建；
- `backend/packages/harness/deerflow/config/agents_config.py:104–157`：DB-first 与文件兼容回退。

当前对象是可变配置记录，不是白皮书要求的 Definition → Version → Deployment 聚合。

#### Policy 技术种子

- `backend/packages/harness/deerflow/guardrails/provider.py:9–55`：Tool 请求、Allow/Deny 决策和 Provider SPI；
- `backend/packages/harness/deerflow/guardrails/middleware.py:20–98`：执行前拦截和 Fail Closed；
- `backend/packages/harness/deerflow/config/guardrails_config.py:13–24`：Guardrail 默认关闭；
- `backend/packages/harness/deerflow/agents/middlewares/tool_error_handling_middleware.py:93–113`：在 Agent Middleware 中挂载。

它是优秀的 PEP seam，但缺少完整 Subject/Resource/Context、`require_approval`、Policy Version、Registry、决策持久化和统一 Audit，因此不能宣称已交付 Policy Engine。

#### Approval 原型

- `backend/app/agent/terminal_graph.py:420–570`：Terminal 风险分级、Allow/Ask/Block 和 interrupt；
- `backend/app/gateway/routers/terminal.py:675–800`：审批后恢复 Graph；
- `backend/app/models/terminal.py:65–88`：记录命令、风险动作、批准者和结果。

这条链可以抽取通用 Approval Primitive，但当前仍绑定 Terminal、命令和会话，没有独立审批资源、授权人规则、过期、委托和统一责任链。

#### 执行状态

- `backend/packages/harness/deerflow/agents/checkpointer/async_provider.py:41–109`：异步 Memory/SQLite/Postgres Checkpoint；
- `backend/packages/harness/deerflow/agents/checkpointer/provider.py:59–157`：同步 Checkpoint Provider；
- `backend/packages/harness/deerflow/database/models.py:206–233`：`SubagentRun` 只记录子 Agent 后台任务。

这些设施可用于实现持久运行，但不能直接承担通用 Task、Run、Attempt、Action 和业务幂等语义。

#### 扩展和数据基础

- `backend/app/plugins/__init__.py:17–36`：EventSource、Executor、Notifier Protocol；
- `backend/app/plugins/registry.py:10–79`：三个内置运维插件的静态元数据和开关；
- `backend/app/gateway/routers/plugins.py:24–36`：只提供插件状态；
- `backend/app/gateway/routers/skills.py:37–117,158–190`：Skill 元数据、Scope、版本字段和安装；
- `backend/app/gateway/routers/mcp.py:44–99,166–249`：租户感知 MCP 配置和管理；
- `backend/app/models/files.py:80–185`：FileObject、Checksum、来源和存储元数据；
- `backend/packages/harness/deerflow/storage/provider.py:51–143`：统一存储 Provider。

这些是能力层和 Artifact 层的可复用基础，但尚未形成统一 Capability、Plugin Package、Connector 或 Artifact 治理契约。

---

## 7. 白皮书—PrismOS 差距矩阵

| 白皮书目标 | 当前实现 | 核心差距 | 优先动作 |
|---|---|---|---|
| Human/Agent/Service/Workload 四类身份 | User、Tenant、Role，Agent 仅有配置 ID | Agent 与一次运行没有独立授权身份 | 定义 IdentityRef、Delegation、WorkloadIdentity |
| 统一资源语义 | 各模块独立表和配置 | ID、Owner、Version、State、Policy Link 不一致 | 先定义 Resource Metadata，不做大一统基表 |
| Agent Registry + Lifecycle | CustomAgent CRUD | 配置可变、无不可变版本和部署绑定 | 拆 Definition/Version/Deployment |
| Policy Registry/PDP/PEP | Guardrail Provider + Terminal Security | 只有局部 Tool Allow/Deny；默认关闭 | 建 PolicyRequest/Decision、PEP Adapter、Audit |
| Secret Manager | MCP env/header、现有配置 | 无统一引用、轮换、最小注入和使用审计 | 先定义 SecretRef 和 Provider，不自建 Vault |
| Task/Run/Action | LangGraph Run、Thread、SubagentRun | 缺业务级状态、幂等、取消、重试和版本引用 | 建 Execution Envelope 和状态机 |
| Approval | Terminal Ask/Resume | 场景专用，无独立资源和授权规则 | 从 Terminal 抽出通用 Approval Service |
| Workflow | 垂直图和事件代码 | 无 Definition/Version/Run 和统一节点契约 | Task/Run 稳定后再建最小 DAG |
| Artifact | Thread 文件、FileObject、Storage Provider | 未统一绑定 Run、Lineage、Retention、Policy | 增 ArtifactRef 和 Provenance，复用存储层 |
| Audit | JSONL 管理审计 + Terminal 表 | 事件格式、存储和关联 ID 割裂 | 建统一 AuditEvent Envelope，先双写 |
| Observability | 运行事件、Token 日志、局部 Trace | 缺统一 Run ID、指标语义和租户成本归因 | 以 Execution Envelope 作为关联主键 |
| Evaluation | 无平台模型 | 无 Dataset、Eval Run、Score、Gate | 先建最小回归 Gate，再扩线上评估 |
| Skill/Tool/Capability | Skill、Runtime Tool、MCP | 三套发现/授权/版本语义 | 建 Capability Descriptor 与 Binding |
| Plugin SDK | Protocol + 静态开关 | 无包、安装、版本、权限、签名和隔离 | 先内部插件合同，再建设私有目录 |
| Connector | MCP 和垂直接口 | 缺连接、凭证、Schema、同步状态和健康统一模型 | 在 Policy/Secret/Artifact 后定义 Connector |
| Runtime Independence | DeerFlow/LangGraph 兼容执行 | 平台 API 仍可感知 Runtime 概念 | 建 Adapter Contract 和 Contract Test |
| Federation | 无 | 所有前置条件均未满足 | 保持研究项，不进入近期 Backlog |

### 7.1 最大设计差异

白皮书是围绕“可治理资源 + 可追踪运行实例”设计的，当前项目仍主要围绕“页面/API 配置 + Runtime 会话 + 垂直业务表”组织。

两者差异可以概括为：

```text
当前 PrismOS
配置对象 → LangGraph Thread/Run → 文件/局部日志

白皮书目标
版本化定义 → Workload Identity → Task/Run/Action
          → Policy/Approval → Artifact/Audit/Evaluation
```

所以，下一阶段不应以增加更多业务菜单为目标，而应把当前链路纳入统一执行信封，再逐步替换各模块的私有语义。

---

## 8. 旧 Roadmap v6 校验

### 8.1 为什么不能继续作为主 Roadmap

旧 v6 文档包含许多有价值的架构判断，但整体仍是版本和 Feature 驱动：

- v1.2 Agent Loop；
- v1.3 Workflow；
- v1.4 Policy；
- v1.5 Digital Employee 与 Extension；
- v1.6 Connector；
- v1.7 移除 DeerFlow；
- v1.9 才引入 Evaluation；
- v2.0 同时承载 Runtime 替换、Identity Mesh、开放工具包和 Federation。

主要问题如下：

1. **Workflow 早于统一 Task/Run 和 Policy**：无法可靠定义 Workflow Step、审批、重试和 Audit；
2. **Policy 延后**：与文档自己的 Governance First 原则冲突；
3. **Evaluation 过晚**：v1.2–v1.8 的架构变化缺少质量和回归门；
4. **Digital Employee 重新膨胀定位**：把产品概念带回核心对象；
5. **Runtime 移除过早**：与当前确认的 DeerFlow/LangGraph 兼容策略冲突；
6. **v2.0 过载**：多个高风险、无共同验收面的战略项目被捆绑；
7. **存在无基线目标**：例如固定 Policy 时延、并发、可用性和 OWASP 覆盖率，未说明测量条件；
8. **版本成功不等于能力闭环**：每个版本包含许多条目，却没有跨版本不变量和停止条件。

### 8.2 可以保留的判断

- Policy 不应放在 Prompt 中；
- Hook 可以增强上下文，但不能拥有最终授权权；
- Registry 和 Marketplace 必须分离；
- Agent Loop 和 Workflow 是共存关系；
- 通过适配层渐进解耦 Runtime；
- Kill Switch、Circuit Breaker 和 Plan-before-Act 是有价值的治理机制；
- Governance 应是内核，扩展系统不能绕过治理链。

### 8.3 迁移原则

旧 v6 不需要删除，但应降级为设计素材和历史决策记录。所有未实施条目必须重新映射到新能力主链，不能仅凭原版本号继续实施。

---

## 9. 推荐 Roadmap：能力基线 + 产品楔入

### 9.1 路线原则

新 Roadmap 不以版本号或页面数量为主，而以平台不变量和依赖门为主：

```text
P0 工程与术语基线
  ↓
P1 Resource / Execution Envelope / Audit Contract
  ↓
P2 Policy Decision / PEP / Approval
  ↓
P3 Task / Run / Action Lifecycle
  ↓
P4 Runtime Adapter Contract
  ↓
P5 Agent Definition / Version / Deployment
  ↓
P6 Workflow Definition / Version / Run
  ↓
P7 Evaluation / Observability / Cost
  ↓
P8 Connector / Knowledge Governance
  ↓
P9 Extension Supply Chain / Private Catalog
  ↓
P10 Runtime Independence（条件触发）
  ↓
P11 Federation（条件触发）
```

这是逻辑依赖顺序，不代表每一阶段必须完全结束后下一阶段才能写第一行代码；可以做技术预研，但发布门必须按该顺序满足。

### 9.2 P0：工程可信基线与契约冻结

**目标**

建立可以安全演进基础对象的工程条件。

**交付**

- AgentOS 术语表和对象责任表；
- Architecture Decision Records：聚合关系、ID、版本、租户和兼容策略；
- 当前关键链路 Contract Test；
- 测试失败分类和基线收敛；
- 数据迁移、双写、回滚和兼容规则；
- 明确 `deerflow`、旧 API、数据库和数据路径兼容边界。

**退出门**

- 核心对象术语在白皮书、API 和代码中含义一致；
- 新基础表和事件 Schema 有版本策略；
- 关键现有链路有可重复基线；
- 已知失败不再混入新功能回归。

**AIOps 验证**

固定一组告警诊断、只读检查和受控命令 Golden Scenarios，作为后续阶段的贯穿样本。

**非目标**

不重写 Runtime，不建设 Workflow，不新增大型场景。

### 9.3 P1：Resource、Execution Envelope 与 Audit Contract

**目标**

让每次执行先拥有统一身份和关联主键，即使底层仍由 LangGraph 执行。

**交付**

- 最小 Resource Metadata；
- IdentityRef、DefinitionRef、EnvironmentRef；
- Execution Envelope：`task_id/run_id/tenant/workload/correlation`；
- 统一 AuditEvent Envelope；
- 对现有 Agent、Terminal 和 Alerting 链路旁路生成 Envelope；
- 现有审计双写 Adapter。

**退出门**

- 任一次受支持执行都能从入口追踪到 Runtime、Tool、Artifact 和结果；
- Audit Event 都带 Tenant、Actor/Workload、Run、Event Type 和 Schema Version；
- 不要求通过 AIOps 表反查平台执行身份。

**AIOps 验证**

告警进入后创建通用执行信封；Incident ID 只作为 `external_ref`，不能成为核心必填字段。

### 9.4 P2：Policy Decision、Enforcement 与 Approval Primitive

**目标**

建立统一、确定性的治理决策链。

**交付**

- PolicyRequest、PolicyDecision 和 PolicyVersion；
- 最小 Policy Registry 和 Binding；
- PDP 接口与 Tool/State Transition PEP；
- `allow/deny/require_approval`；
- 通用 Approval 状态机；
- 从 Terminal Security/Interrupt 抽取 Adapter；
- 决策与审批统一 Audit。

**退出门**

- 所有纳管 Tool 调用在执行前产生持久 Policy Decision；
- `require_approval` 可以暂停、批准、拒绝、过期并恢复；
- Fail Closed 范围有明确文档和测试；
- Policy 决策不依赖 Prompt。

**AIOps 验证**

只读查询自动允许，配置变更要求审批，破坏性命令拒绝；同一接口也可用于非运维 Tool。

### 9.5 P3：Task、Run、Attempt 与 Action 生命周期

**目标**

把 Runtime 会话提升为平台可管理的业务执行。

**交付**

- Task、Run、Attempt、Action、Event 数据模型；
- Created/Queued/Running/Waiting/Terminal 状态机；
- 取消、超时、重试、幂等键和恢复；
- Policy、Approval、Artifact 和 Audit 关联；
- LangGraph Run Adapter；
- 最小 API 和运营视图。

**退出门**

- 进程重启后仍可解释和恢复受支持 Run；
- 重复事件不重复执行已提交的外部副作用；
- 重试和新 Run 的语义清晰；
- Run 固化 Agent/Workflow/Policy 版本引用。

**AIOps 验证**

告警诊断、人工等待、恢复和命令执行都映射到同一 Task/Run 链；重复告警通过业务幂等键处理。

### 9.6 P4：Runtime Adapter Contract

**目标**

隔离平台对象与 DeerFlow/LangGraph 实现细节，同时保留兼容性。

**交付**

- Start/Stream/Pause/Resume/Cancel/GetState Runtime Contract；
- Message、Tool Call、Checkpoint 和 Error 标准映射；
- DeerFlow/LangGraph Adapter；
- Runtime Contract Test Suite；
- 性能、恢复和兼容基线。

**退出门**

- 上层 Task/Run、Policy 和 Audit 不 import Runtime 私有对象；
- 当前 Agent/Skill/API/数据路径通过兼容测试；
- 替换 Runtime 不需要修改平台核心 Schema。

**AIOps 验证**

同一诊断 Golden Scenario 经 Adapter 执行，输出、审批、事件和 Artifact 契约保持一致。

**非目标**

本阶段不移除 DeerFlow，不承诺自研 Runtime。

### 9.7 P5：Agent Definition、Version 与 Deployment

**目标**

将当前 CustomAgent 配置演进为可发布、可回滚的 Agent 资产。

**交付**

- AgentDefinition、不可变 AgentVersion；
- Model/Prompt/Skill/Tool/Knowledge 依赖快照；
- Environment Deployment/Binding；
- Draft → Evaluated → Approved → Active → Suspended/Retired；
- Owner、Risk、Policy 和 Rollback；
- 现有 CustomAgent 兼容迁移。

**退出门**

- 历史 Run 永远引用原执行版本；
- 配置变更产生新版本而不是覆盖历史；
- 生产激活、暂停和回滚可审计。

**AIOps 验证**

诊断 Agent 新版本可以灰度到测试环境，失败后回滚，不改变 Incident Schema。

### 9.8 P6：Workflow Definition、Version 与 Run

**目标**

在统一执行和治理原语上增加确定性编排。

**交付**

- WorkflowDefinition、WorkflowVersion、WorkflowRun；
- 最小 DAG、条件、并行、Agent/Tool/Approval 节点；
- 节点输入输出 Schema；
- Timeout、Retry、Compensation 和 Idempotency；
- Event Trigger 与 Schedule Adapter；
- 不可变版本和回放。

**退出门**

- Workflow 节点统一创建 Action/Run，不绕过 Policy；
- 长任务可等待、恢复和取消；
- 失败分支和外部副作用有明确语义；
- Skill 内不隐藏第二套复杂 DAG。

**AIOps 验证**

实现“事件 → 诊断 → 变更提案 → 审批 → 受控执行 → 验证”的最小 Runbook Workflow。

### 9.9 P7：Evaluation、Observability 与 Cost

**目标**

建立可晋级、可运营和可证明改进的质量闭环。

**交付**

- Dataset、EvaluationRun、Score、Comparator 和 Gate；
- Agent/Tool/Workflow/Policy 回归数据集；
- Run 级日志、指标、Trace 和状态关联；
- Model/Token/Tool/Compute 成本归因；
- 版本 Compare、Promote、Reject、Rollback；
- 线上反馈和漂移信号。

**退出门**

- 高风险 Agent 变更未通过 Gate 不能晋级；
- 可以回答哪个版本、哪个 Tool、哪条 Policy 导致质量或成本变化；
- 评估保留分项结果，不压缩为单一“智能分”。

**AIOps 验证**

评估诊断正确性、证据完整性、建议采纳率、误执行、审批率、恢复率、时延和成本；不只评估文字质量。

### 9.10 P8：Connector Contract 与 Knowledge Governance

**目标**

将外部数据和知识接入纳入身份、Secret、Policy、Artifact 和运行治理。

**交付**

- Connector Definition/Instance/CredentialRef；
- Schema、Health、Sync State、Rate Limit 和 Error Contract；
- Knowledge Source、Document、Chunk、Index Version 和 ACL；
- Retrieval Audit 与 Data Classification；
- MCP 作为能力协议之一，而不是所有 Connector 的替代；
- 首批参考 Connector。

**退出门**

- Agent 不能绕过数据权限看到检索内容；
- 凭证只通过 SecretRef 注入；
- Connector 和索引变化可追踪到 Evaluation；
- 数据来源和 Artifact Provenance 可解释。

**AIOps 验证**

接入监控、日志、CMDB 和工单，但这些系统只实现 Connector，不向平台核心注入领域模型。

### 9.11 P9：扩展供应链与私有能力目录

**目标**

让团队在不修改内核的情况下安全扩展平台。

**交付**

- Plugin Package Manifest、SDK、CLI 和模板；
- 权限、Secret、依赖和 Runtime 声明；
- 安装、升级、暂停、卸载和回滚；
- 签名、来源、扫描和兼容性；
- 官方库和企业私有目录；
- 使用、质量、Owner 和维护状态。

**退出门**

- 插件不能绕过 Policy、Audit 和资源隔离；
- 升级前可以看到权限变化和回归结果；
- AIOps 插件可以独立安装/禁用，平台核心仍可工作。

**非目标**

不建设公共 Marketplace，不追求海量条目。

### 9.12 P10：Runtime Independence（条件触发）

**触发条件**

只有满足下列任一类证据才立项：

- DeerFlow/LangGraph 阻碍关键可靠性或安全需求；
- 性能或成本基线无法通过适配优化满足；
- 许可证、维护或上游方向构成不可接受风险；
- 至少两个 Runtime Adapter 证明平台契约稳定；
- 替换收益大于迁移和长期维护成本。

**验收**

- 现有 API、Skill、Agent、数据和执行历史兼容；
- Contract/Evaluation Suite 达到或超过原 Runtime；
- 回滚路径真实可用；
- 不因追求“自主可控”重新发明所有基础设施。

### 9.13 P11：Federation（条件触发）

**触发条件**

- 至少存在多个真实组织的持续协作需求；
- 有跨组织身份、信任、能力发现和授权协议；
- 有数据边界、责任、审计交换、SLA、计费和争议处理；
- 普通 Connector/API 方案已经不能经济满足需求。

在条件满足前，只保留协议研究和兼容性观察，不进入承诺型 Roadmap。

---

## 10. AI 运维楔入路线与解耦测试

### 10.1 验证主链

```text
告警 / 事件
  → Task
  → Run
  → Policy Decision
  → Agent 分析
  → 受控 Action
  → Approval（必要时）
  → Artifact / Audit / Trace
  → Evaluation
```

这条链验证的不是“AIOps 产品功能是否足够多”，而是平台能否把一个不确定 Agent 行为包在可治理、可恢复和可评估的确定性边界里。

### 10.2 平台核心与 AIOps 插件边界

| 平台核心 | AIOps 插件 |
|---|---|
| Event Envelope | Alert、Change、Incident |
| Task / Run / Action | Diagnosis、Remediation、Runbook |
| Policy / Approval | 生产变更风险规则、On-call 审批策略 |
| Tool / Connector | Monitoring、CMDB、Ticket、SSH 适配 |
| Artifact | 故障报告、日志快照、变更方案 |
| Audit / Trace | 事故时间线和领域视图 |
| Evaluation | 诊断正确性、修复采纳率等场景评分器 |

### 10.3 解耦停止条件

出现以下任一现象时，应停止当前实现并重新划界：

- 平台核心 `Task/Run/Policy/Approval` Schema 出现 `alert_id`、`incident_severity`、`host_id` 等运维专用必填字段；
- Core 模块 import AIOps 插件代码；
- 禁用所有 AIOps 插件后，Agent、Task/Run、Policy 或 Audit 核心无法工作；
- Policy Engine 需要调用 Incident Service 才能完成通用决策；
- 通用 Workflow 节点以告警状态机为默认语义；
- Artifact 必须属于 Incident 才能持久化；
- Evaluation 只能评估诊断文本，不能评估其他 Agent 任务。

### 10.4 产品楔入的成功标准

早期不以“自动闭环率越高越好”为唯一目标。更可靠的指标组合是：

- 证据完整率和诊断可复盘率；
- 建议采纳率与人工修改率；
- 误执行和越权执行为零；
- 审批等待、恢复和取消成功率；
- 重复事件下副作用幂等率；
- 从告警到可执行建议的时延；
- 每个成功 Task 的模型和工具成本；
- 同一平台原语在第二个非运维场景中的复用率。

---

## 11. 路线洞察

### 11.1 PrismOS 的竞争力不应是“又一个 Agent Builder”

Builder、聊天界面、模型选择和 Tool 调用正在快速商品化。PrismOS 更有机会建立差异的位置是：

- 将身份、委派、策略和审批放进同一执行链；
- 将 Agent 的动态行为转化为可暂停、恢复、取消和复盘的 Run；
- 将定义版本、运行证据和 Evaluation 连接起来；
- 在私有部署中提供跨模型、框架和业务系统的治理一致性。

### 11.2 最小内核不是模块最少，而是不变量最少

平台核心不应膨胀成所有企业软件的集合，但必须拥有少量不可绕过的不变量：

1. 每次执行有身份；
2. 每个外部动作有 Policy Decision；
3. 每个副作用有幂等和 Audit；
4. 每个生产定义有不可变版本；
5. 每次发布有可解释的 Evaluation 和回滚路径。

### 11.3 现有垂直代码不是包袱，而是原语矿场

Terminal 的 Ask/Block/Allow、LangGraph interrupt/resume、Alerting 的长任务和取消、FileObject 的 Checksum 与来源、Guardrail 的 Pre-tool seam 都是高价值原型。正确做法不是复制到新模块，也不是直接把场景对象升格为核心，而是抽取契约、写 Adapter、以双写验证后再迁移。

### 11.4 Runtime Independence 是结果，不是起点

当平台能用稳定契约驱动现有 Runtime，并积累足够 Contract Test 和 Evaluation 数据后，是否替换 Runtime 会成为可计算的工程决策。在此之前重写 Runtime，只会把精力从真正差异化的治理层移开。

### 11.5 Evaluation 必须早于规模化，而不必一开始就“大而全”

早期 Evaluation 可以只是 20–50 个高价值 Golden Scenarios、确定性状态机测试、Tool 参数正确性和安全回归。重要的是形成“变更必须拿证据晋级”的机制，而不是先建设复杂评估平台。

### 11.6 私有能力目录比公共 Marketplace 更接近企业价值

企业首先需要知道内部 Agent、Skill、Connector 谁负责、能否使用、经过什么审核、适用于哪个环境、质量如何。只要这些元数据和生命周期没有建立，公共 Marketplace 只会扩大供应链风险。

### 11.7 第二验证场景是平台化的关键证据

AI 运维只能证明系统在 AI 运维中有用，不能单独证明它是 Agent OS。建议在 P3–P5 期间选择一个低耦合第二场景，例如研发任务治理、客服知识处理或内部文档审批。若核心原语无需修改即可复用，平台定位才获得实证支持。

---

## 12. 主要风险与控制

| 风险 | 可能后果 | 控制方式 |
|---|---|---|
| 术语先行、契约滞后 | 各模块都声称支持 Agent/Run/Policy，但含义不同 | P0 冻结对象责任和 ADR |
| 同时铺开过多能力 | 大量半成品和跨模块返工 | 以阶段退出门控制 WIP |
| 垂直场景污染核心 | PrismOS 退化为 AIOps 套件 | 插件依赖单向、执行解耦测试 |
| 把 Runtime 状态当业务状态 | 无法保证幂等、责任和历史兼容 | 独立 Task/Run/Action 模型 |
| Policy 只拦 Tool 名称 | 参数、资源、身份和结果提交仍可越权 | 完整 Request Context 和多 PEP |
| Approval 只做 UI 弹窗 | 无授权人、过期、责任和恢复语义 | 独立 Approval 资源与状态机 |
| Audit 继续分散 | 无法完成事故复盘和合规证明 | Event Envelope、统一 ID、先双写 |
| 过早 Workflow | 把不稳定对象固化进 DAG | P3 后再发布 Workflow |
| 过早 Runtime 重写 | 兼容回归、投入失控、差异化延误 | Adapter First + 条件触发 |
| 过晚 Evaluation | 质量退化无法定位 | 最小 Gate 从 P0/P1 开始 |
| 无基线 SLO | 指标成为愿望清单 | 测量后设置分场景 SLO |
| 历史测试失败累积 | 新旧回归不可区分 | 失败分类、关键链 Contract Test |

---

## 13. 白皮书修订清单

### 13.1 必须修订

1. 在对象模型附录中补充 Task/Run/Attempt/Action、WorkflowRun、PolicyDecision、Approval 的基数关系；
2. 增加最小 `ExecutionEnvelope`；
3. 增加 `PolicyRequest/PolicyDecision` 契约、组合优先级、默认决策和 Fail Closed 边界；
4. 修正阶段一要求生产执行可追踪、阶段二才引入 Task/Run 的矛盾；
5. 将 Evaluation 拆为基础契约验证、场景回归、线上运营三层；
6. 将 Agent Registry 拆解为 Definition、Version、Deployment/Binding 和 Lifecycle；
7. 将 Runtime Independence 改为条件投资项；
8. 将 Federation 从固定阶段改为条件投资项。

### 13.2 建议修订

1. 将“一切皆资源”改为“可治理定义和影响业务结果的运行实例具有统一资源语义”；
2. 为每个 Roadmap 阶段增加“依赖、退出门、非目标和停止条件”；
3. 区分 Stop、Cancel、Suspend、Terminate 和 Kill Switch；
4. 增加 SecretRef、Artifact Provenance、AuditEvent 和 Idempotency 规范；
5. 明确 Workflow 不能绕过 Task/Run、Policy 和 Approval；
6. 明确 MCP 是能力接入协议，不等于 Connector、Secret 或 Policy；
7. 增加“当前能力与目标能力”声明，防止白皮书被当作发布清单；
8. 增加 AI 运维插件边界和第二验证场景要求；
9. 删除或降级没有基线和测量条件的绝对性能数字。

### 13.3 文档治理建议

- 将正式重构稿设为唯一 Canonical Whitepaper；
- 原始 62,352 行文件归档为 Research Corpus，不再直接编辑发布；
- Roadmap 独立为随工程证据更新的文档，不把白皮书每次改成版本计划；
- 对象契约、状态机和 API 放在 Architecture Specs/ADR，不让白皮书承担全部技术细节；
- 每个发布版本生成 Capability Claim Matrix，明确“已实现、部分实现、实验性、规划中”。

---

## 14. 建议的近期决策

按当前证据，最合理的下一步不是开始 Workflow 或 Runtime 重写，而是正式批准以下近期范围：

```text
近期主线：P0 → P1 → P2 → P3

即：
工程与术语基线
→ Execution Envelope / Audit Contract
→ Policy / Approval
→ Task / Run / Action
```

同时保留三条横向支线：

1. **工程质量与供应链安全**：测试基线、依赖、迁移和发布门；
2. **Artifact/File/Storage 与 Secret**：复用现有基础，逐步接入治理；
3. **AI 运维验证**：只验证平台原语，不扩大 AIOps 领域范围。

在 P3 退出门满足前，建议明确延后：

- 通用 Workflow Engine；
- 公共 Marketplace；
- DeerFlow/LangGraph 移除；
- Agent Federation；
- 数字员工组织模型；
- 大规模低代码 Builder。

---

## 15. 最终判断

白皮书没有需要推翻的根本逻辑问题。它已经给出了正确的长期方向：围绕 Agent 建立企业级治理与执行基础设施，而不是继续堆叠聊天、流程和垂直功能。

但从白皮书到工程实施还差一层关键转换：

> **把架构名词转换为少量不可绕过、可以测试、可以迁移、可以审计的平台契约。**

PrismOS 当前最有价值的资产，是它已经拥有足够多的真实运行设施和高风险场景原型，可以在不重写 Runtime 的情况下完成这层转换。最危险的路线，则是继续按旧 v6 增加 Workflow、数字员工、Marketplace 和 Federation，最后拥有很多模块，却没有统一身份、运行、策略和证据链。

因此建议正式确认：

1. 以正式重构白皮书作为长期战略母本；
2. 以本报告的依赖有序 Roadmap 作为近期工程主线；
3. 以 AI 运维作为验证楔入，不作为平台内核；
4. 先完成 P0–P3 的治理与执行中轴，再决定 Workflow、Runtime Independence 和生态投资；
5. 以退出门和实证数据驱动阶段晋级，而不是以版本号或功能数量驱动。

---

## 附录 A｜证据索引

### A.1 白皮书

- `whitepaper-agentos-restructured.md:255–317`：定义、价值和边界；
- `whitepaper-agentos-restructured.md:376–483`：设计原则和六层架构；
- `whitepaper-agentos-restructured.md:497–580`：身份、Registry、Policy、Secret 和生命周期；
- `whitepaper-agentos-restructured.md:583–689`：Runtime、Task/Run、Workflow 和人工介入；
- `whitepaper-agentos-restructured.md:776–887`：能力分类、核心对象和标准执行流程；
- `whitepaper-agentos-restructured.md:924–962`：策略域与执行链；
- `whitepaper-agentos-restructured.md:982–1072`：Audit、Observability、Cost 和 Evaluation；
- `whitepaper-agentos-restructured.md:1138–1197`：风险、审批和责任；
- `whitepaper-agentos-restructured.md:1286–1324`：研发与运维场景；
- `whitepaper-agentos-restructured.md:1355–1575`：Capability Roadmap 和 Federation；
- `whitepaper-agentos-restructured.md:1653–1689`：核心对象附录。

### A.2 项目

- `prism-platform/README.md:10–20`：定位、当前基础和 AIOps 解耦；
- `prism-platform/README.md:22–40`：能力基线与部分能力；
- `prism-platform/README.md:44–62`：运行架构和 DeerFlow/LangGraph 边界；
- `prism-platform/README.md:64–83`：现有高层 Roadmap；
- `prism-platform/README.md:118–128`：安全和 Alpha 未交付声明；
- `prism-platform/docs/releases/v0.1.0-alpha.1.md:114–138`：测试与发布验证记录；
- `prism-platform/docs/superpowers/specs/2026-07-23-governed-agent-platform-roadmap-design-v6.md`：旧 v6 Roadmap。

### A.3 证据时间性

本报告是对提交 `a58d461` 的快照审计。后续代码、数据库迁移、Release 和 Whitepaper 更新可能改变能力判定；每个重要版本应重新生成 Gap Matrix，而不是永久复用本报告中的“当前状态”。
