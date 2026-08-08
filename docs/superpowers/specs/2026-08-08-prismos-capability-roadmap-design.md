# PrismOS Capability Roadmap Design

**日期：** 2026-08-08
**状态：** Approved
**适用项目：** PrismOS (`prism-platform`)
**项目基线：** `main` @ `a58d461`，`v0.1.0-alpha.2`
**规划基线：** 未来 12 个月由 1–2 名核心开发者持续投入；M1 已批准采用 4–5 名核心贡献者的加速情景
**战略依据：** AgentOS 白皮书及其与 PrismOS 的双向校验报告

---

## 1. 文档目的

本文档将 AgentOS 白皮书的长期战略裁剪为一条以 PrismOS 现有项目为根基、可由小团队持续交付的 Capability Roadmap。

它回答五个问题：

1. PrismOS 当前真正拥有和缺少什么；
2. 白皮书中哪些能力应该保留、复用、延后或取消；
3. 未来 12 个月必须证明什么；
4. 后续能力按照什么依赖关系和证据门启动；
5. 如何防止 AI 运维验证场景重新侵入平台内核。

本文档是能力路线设计，不是单个里程碑的实施计划。每个里程碑在启动前仍需独立的 Spec、ADR 和 Implementation Plan。

## 2. 输入、证据与约束

### 2.1 主要输入

- 原始白皮书草稿：`/Users/yespon/Downloads/whitepaper-agentos.md`；
- 正式重构白皮书：`/Users/yespon/Documents/AgentOS/whitepaper-agentos-restructured.md`；
- 双向校验报告：`/Users/yespon/Documents/AgentOS/agentos-whitepaper-prismos-gap-roadmap-review.md`；
- PrismOS 当前代码、README、Release Notes、测试和迁移文件；
- 旧 Governed Agent Platform Roadmap v1–v6。

### 2.2 已确认的项目事实

PrismOS 当前不是从零开始的概念项目，而是一个建立在 DeerFlow/LangGraph 执行基础上的 Agent 应用与治理平台 Alpha。项目已经拥有：

- 多租户、用户和 RBAC 基础；
- 数据库化模型配置与租户分配；
- Agent 配置、Skill、MCP 和 Memory；
- Local、Docker 和可选 Kubernetes Sandbox；
- 文件、对象存储和 Artifact 基础；
- 管理、审计视图和垂直插件；
- LangGraph Checkpoint、interrupt/resume 和 Tool Middleware 等执行设施。

项目同时存在明确边界：

- 平台没有统一的 Resource、Execution、Policy 和 Audit 契约；
- LangGraph Thread/Run 不是平台一等 Task/Run；
- Terminal 审批不是通用 Approval；
- Guardrail Provider 是 Policy Enforcement 技术种子，不是完整 Policy Engine；
- Agent 配置是可变记录，不是 Definition/Version/Deployment 生命周期；
- Plugin Protocol 和静态开关不是可分发扩展供应链；
- 后端完整测试存在历史失败，前端 lint、typecheck、unit test 和 build 尚未成为可靠硬门。

因此，项目的近期问题不是“再添加一个 Workflow 页面”，而是已有能力之间缺少可治理、可追踪、可恢复的执行中轴。

### 2.3 兼容约束

Roadmap 默认保留：

- DeerFlow-compatible harness 和 LangGraph；
- `deerflow` Python import 路径；
- 已有 API 路由和客户端行为；
- 已有数据库表、Alembic migrations 和历史数据；
- `.opsintech` 与 `OPSINTECH_*` 兼容输入边界；
- 当前 Skill、MCP、File、Sandbox 和模型配置能力。

基础能力通过新增契约、Adapter、旁路事件、双写和渐进迁移建立，不通过一次性重写建立。

### 2.4 资源约束

本 Roadmap 的范围、依赖顺序和退出门仍按 1–2 名核心开发者的可持续投入规划。M1 可采用 4–5 名核心贡献者并行交付互不重叠的契约、持久化、兼容与场景验证轨道，但增加人力只提高同一里程碑内的吞吐量，不改变能力顺序，也不授权把 M2/M3 范围提前带入 M1。

由此产生四项纪律：

1. 同一阶段只允许一条平台主线；
2. 每 3–4 个月必须形成一条端到端、可演示、可测试的闭环；
3. 不并行建设多个尚未被真实场景验证的横向平台层；
4. 候选阶段不会因为日期到达而自动启动。

## 3. 核心判断

### 3.1 产品定位

PrismOS 是企业级 Governed Agent Execution Platform：它不与 Agent Framework 竞争模型调用和推理循环，而是在现有 Runtime 之上提供确定性的身份、策略、执行、责任和质量边界。

首年唯一需要证明的核心命题是：

> PrismOS 能将不确定的 Agent 行为包裹在确定、可治理、可恢复、可审计、可评估的执行边界中。

### 3.2 平台主轴

所有近期建设围绕同一条主轴展开：

```text
Resource / Identity
        ↓
Execution Envelope
        ↓
Policy Decision / Approval
        ↓
Task / Run / Attempt / Action
        ↓
Artifact / Audit / Trace
        ↓
Evaluation / Promotion / Rollback
```

Workflow、Connector、扩展供应链、Runtime Independence 和 Federation 都是建立在这条主轴之上的能力，而不是可以跳过主轴提前交付的独立功能。

### 3.3 采用的演进方式

Roadmap 采用“契约优先的纵向闭环”：每个里程碑都用真实场景贯穿必要的平台层，以端到端证据检验抽象。

未采用的两种方式是：

- **AIOps 产品优先：** 容易让 Alert、Incident、Host 和 Command 语义侵入核心，后续再抽象成本高；
- **完整横向平台优先：** 对小团队而言交付周期过长，大量抽象在运行前无法验证，容易形成新的愿望清单。

## 4. 能力裁剪

### 4.1 首年主线

- 工程可信基线和核心术语；
- Resource Metadata 与引用契约；
- Execution Envelope；
- 统一 AuditEvent；
- Policy Decision、PEP 与 Approval；
- Task、Run、Attempt、Action 生命周期；
- Runtime Adapter Contract；
- 最小 Evaluation Gate；
- AIOps 和企业研究两类 Golden Scenarios。

### 4.2 直接复用，不重写

- Tenant、User 和 RBAC；
- Model Provider 配置；
- Skill 和 MCP；
- Sandbox 和 Checkpoint；
- File、Storage 和 Artifact 基础；
- DeerFlow/LangGraph 执行能力；
- 现有垂直场景中的 Guardrail、Approval 和 Audit 技术种子。

### 4.3 后续候选能力

- Agent Definition、Version 和 Deployment；
- 最小 Workflow 生命周期；
- Connector、SecretRef 和 Knowledge Governance；
- Extension Package、SDK 和企业私有目录。

### 4.4 证据触发能力

- Runtime Independence；
- Federation。

### 4.5 不进入默认 Roadmap

- 公共 Marketplace；
- 通用 iPaaS；
- 完整低代码 Agent Builder；
- BPMN 全兼容和通用 RPA；
- “数字员工”独立核心框架；
- 以自主可控为理由自研 Runtime；
- 无真实组织需求支撑的 Federation；
- 以自动闭环率为中心扩张 AIOps 产品范围。

## 5. 目标架构边界

### 5.1 六类职责

| 架构职责 | 主要对象或能力 | 边界 |
|---|---|---|
| 入口与体验 | Web、API、IM、Event、Schedule | 接收意图、展示状态，不拥有执行真相 |
| 资源与身份 | Tenant、IdentityRef、DefinitionRef、EnvironmentRef、ResourceMetadata | 提供稳定身份和引用，不承载领域流程 |
| 治理控制 | Policy、Decision、Approval、Audit、Cancel/Kill | 在确定性代码层做授权和责任记录 |
| 执行生命周期 | Task、Run、Attempt、Action、Event、ArtifactRef | 是平台执行状态的唯一事实来源 |
| 能力与 Runtime | Agent、Skill、Tool、MCP、Sandbox、Runtime Adapter | 执行工作，但不能绕过治理和生命周期 |
| 质量与演进 | Evaluation、Cost、Version、Promotion、Rollback | 用证据控制版本晋级和平台演进 |

### 5.2 统一执行数据流

```text
Intent / Event
  → Entry Adapter
  → Task / Run
  → Policy Request / Decision
  → Approval（必要时）
  → Attempt / Action
  → Runtime Adapter / Tool / Sandbox
  → Artifact / Audit / Trace
  → Evaluation
```

每个组件必须满足单一责任：

- Entry Adapter 只把外部输入映射为平台请求；
- Task/Run 管理业务执行生命周期；
- Policy 决定是否允许，不执行领域动作；
- Approval 管理人工授权，不承担 Policy 计算；
- Runtime Adapter 翻译执行协议，不定义平台资源语义；
- Artifact 保存结果和来源，不决定运行状态；
- Audit 记录事实，不作为业务状态机的隐式替代品；
- Evaluation 评估结果和行为，不直接修改历史事实。

### 5.3 核心 Schema 的领域隔离

AIOps 和企业研究领域对象只能通过 `external_ref`、typed payload 或插件资源关联，不能进入平台核心必填字段。

以下现象视为边界失败：

- Task、Run、Policy 或 Approval 核心 Schema 要求 `alert_id`、`incident_id`、`host_id` 或 `command`；
- Core 模块 import AIOps 插件；
- Policy Engine 需要调用 Incident Service 才能完成通用决策；
- Artifact 必须属于 Incident 才能持久化；
- 禁用 AIOps 后，Task/Run、Policy、Approval 或 Audit 无法运行；
- 企业研究场景必须走告警或命令状态机。

## 6. Golden Scenarios

### 6.1 场景 A：AI 运维验证楔入

```text
告警 / 事件
  → 诊断 Task
  → Agent 分析与只读检查
  → 变更提案
  → Policy Decision
  → Approval（必要时）
  → 受控 Action
  → 验证
  → Artifact / Audit / Evaluation
```

平台验证：

- 只读操作自动允许；
- 高风险变更需要审批；
- 破坏性操作拒绝；
- 审批后可以恢复；
- 重复告警不会重复提交副作用；
- 每项结果都能追溯到 Run、Policy、Approval 和 Action。

领域归属：Alert、Incident、Host、Runbook、On-call、Diagnosis 和 Remediation 留在 AIOps 插件。

### 6.2 场景 B：受控企业研究与报告交付

```text
研究任务
  → 数据 / 文件访问
  → Agent 分析
  → 引用与报告 Artifact
  → Evaluation
  → 人工批准
  → 导出或发布
```

平台验证：

- 数据访问经过租户和 Policy 控制；
- 输出保留来源和 Artifact 关联；
- Evaluation 同时检查质量、来源完整性、成本和治理行为；
- 发布前可要求人工审批；
- 与 AIOps 复用同一 Execution、Policy、Approval、Audit 和 Task/Run 契约。

领域归属：Source、Citation、Report 和 Publication 留在研究应用或插件。

### 6.3 第二场景的意义

企业研究不是首年第二条产品线，而是架构解耦试纸。只有两类语义显著不同的场景能够复用同一核心，才能证明 PrismOS 的平台原语不是 AIOps 的改名抽象。

## 7. Roadmap 总览

Roadmap 分为三层：

| 层级 | 时间窗口 | 里程碑 | 核心结果 |
|---|---|---|---|
| 承诺路线 | 2026.08–2026.11 | M1 最小治理执行闭环 | Agent 行为可拦截、决策、审批和审计 |
| 承诺路线 | 2026.12–2027.03 | M2 通用执行生命周期 | Task/Run 可持久化、恢复、取消、重试和幂等 |
| 承诺路线 | 2027.04–2027.07 | M3 平台化与质量证据 | Runtime 契约、最小 Evaluation、第二场景复用 |
| 候选路线 | 2027.08–2027.11 | M4 Agent 资产生命周期 | Definition、不可变 Version、Deployment 和回滚 |
| 候选路线 | 2027.12–2028.03 | M5 最小 Workflow 生命周期 | 版本化 DAG、等待、审批和补偿 |
| 候选路线 | 2028.04–2028.07 | M6 数据与知识治理 | Connector、SecretRef、ACL、来源和检索审计 |
| 候选路线 | 2028.08–2028.11 | M7 扩展供应链与私有目录 | 安装、升级、签名和回滚的企业扩展 |
| 条件路线 | 无预设日期 | C1 Runtime Independence | 仅在现有 Runtime 被证明确实阻碍目标时启动 |
| 条件路线 | 无预设日期 | C2 Federation | 仅在真实跨组织需求无法由现有集成满足时启动 |

日期用于容量规划，不构成自动晋级承诺。里程碑按退出门晋级。

## 8. 首年承诺路线

### 8.1 M1：最小治理执行闭环

**周期：** 2026.08–2026.11
**目标：** 让一项真实 Agent 行为在发生外部副作用前经过统一治理链。

#### 主要交付

- 冻结 `ResourceMetadata`、`IdentityRef`、`DefinitionRef` 和 `EnvironmentRef`；
- 定义版本化 `ExecutionEnvelope`，至少包含 tenant、task、run、workload、correlation 和 schema version；
- M1 中的 task/run 只作为全链路稳定、不可复用的关联 ID 和兼容引用，不在本阶段定义持久化生命周期或状态转换；这些语义由 M2 交付；
- 定义统一 `AuditEvent` Envelope；
- 对管理审计、Terminal 审计和 Agent Tool 事件做兼容双写；
- 在 Guardrail Provider 基础上建立最小 `PolicyRequest` 和 `PolicyDecision`；
- 支持 `allow`、`deny`、`require_approval` 三种确定性决策；
- 从 Terminal interrupt/resume 抽取通用 Approval Primitive；
- 建立 AIOps Golden Scenario 和 Contract Test；
- 建立历史测试失败分类和不回退基线。

#### 故障语义

- Policy 无法决策时，纳管副作用操作默认拒绝；
- Approval 过期、上下文变化或 Decision Version 不匹配时不得继续；
- 关键 Audit 持久化失败时不得提交外部副作用；
- Adapter 双写失败必须可观测、可重放，不得静默丢失；
- 只读路径和副作用路径使用明确风险分类，不依靠 Prompt 猜测。

#### 退出门

- 所有纳管 Action 在执行前都有持久化 Policy Decision；
- 可从 Action 追溯 tenant、actor/workload、run、approval、policy version 和 result；
- 核心 Schema 不含 AIOps 领域必填字段；
- AIOps Golden Scenario 的允许、拒绝、审批和审计路径通过；
- 新增 Contract Tests 全部通过；
- 历史失败被独立标识，新功能不增加失败数量。

#### 非目标

- 不建立完整 Task/Run 生命周期；
- 不把 M1 的关联 ID 宣称为已交付 Task/Run 聚合；
- 不建设 Workflow；
- 不重写 Runtime；
- 不增加大型垂直业务模块。

### 8.2 M2：通用执行生命周期

**周期：** 2026.12–2027.03
**目标：** 将 Runtime 会话和领域执行提升为平台可管理对象。

#### 主要交付

- `Task → Run → Attempt → Action → Event` 聚合模型；
- Created、Queued、Running、Waiting、Succeeded、Failed、Cancelled、TimedOut 等状态和合法转换；
- 取消、超时、有限重试、恢复和业务幂等键；
- 副作用提交记录和去重语义；
- Policy、Approval、Artifact 和 Audit 与 Attempt/Action 关联；
- LangGraph Run Adapter；
- 最小生命周期查询和运营视图。

#### 故障语义

- 进程重启后从持久状态恢复，不根据聊天历史猜测状态；
- 重试创建新 Attempt，不覆盖历史 Attempt；
- 重复输入和事件不会再次执行已提交副作用；
- Cancel 采用协作式语义，不能撤销的副作用必须显式标记；
- Unknown、Orphaned 或状态不一致的 Run 必须可检索和人工处置。

#### 退出门

- Run 可以恢复、取消、超时和有限重试；
- 重复输入或重复事件不产生重复外部副作用；
- 每个历史 Run 固化执行时的 Policy 和 Definition 引用；
- AIOps 等待审批、恢复执行和重复告警通过故障注入；
- 生命周期状态只能通过定义的 Command/Transition 改变；
- 运营视图展示平台事实，不从多个日志临时拼装状态。

#### 非目标

- 不建设通用调度平台；
- 不建设完整 Workflow DAG；
- 不承诺任意外部副作用均可撤销。

### 8.3 M3：平台化与质量证据

**周期：** 2027.04–2027.07
**目标：** 证明内核可以跨场景复用，并用 Evaluation 证据管理质量。

#### 主要交付

- 冻结 Runtime Adapter：`start`、`stream`、`pause`、`resume`、`cancel`、`get_state`；
- 标准化 Runtime Message、Tool Call、Checkpoint、Error 和 Event 映射；
- 建立最小 Dataset、EvaluationRun、Score 和 Gate；
- 评估越权、幂等、恢复、结果质量、来源完整性、延迟和成本；
- 接入“受控企业研究与报告交付”Golden Scenario；
- 建立两场景共用的 Contract/Evaluation Suite；
- 对 Runtime 私有类型泄漏和领域字段侵入做架构测试。

#### 故障语义

- Runtime 错误统一映射为平台错误类别，原始诊断作为受控详情保留；
- Adapter 必须显式表达不支持的能力，不伪造 pause/cancel 成功；
- Evaluation 失败阻止高风险版本晋级，但不重写历史 Run；
- 外部来源不可用时，报告必须标记证据缺失，不能把无依据输出视为成功。

#### 退出门

- AIOps 与企业研究通过同一核心 API、状态机和事件契约运行；
- 上层治理和生命周期模块不 import LangGraph 私有对象；
- 两类 Golden Scenarios 均可执行可重复回归评估；
- 高风险治理或质量回归会阻止版本晋级；
- 禁用 AIOps 插件后，核心平台和企业研究场景仍可运行；
- Runtime Adapter Contract 具有独立 Contract Test，而不仅是实现测试。

#### 非目标

- 不替换 DeerFlow/LangGraph；
- 不建设完整 Agent Version/Deployment；
- 不建设完整 Workflow 或统一 Connector；
- 不把企业研究扩张为第二条完整产品线。

## 9. 后续候选路线

M4–M7 只冻结能力目标、启动条件和退出门。每阶段开始前重新检查项目证据和市场需求，不提前冻结两年后的内部实现。

### 9.1 M4：Agent 资产生命周期

**候选周期：** 2027.08–2027.11
**目标：** 将 `CustomAgent` 可变配置升级为可发布、评估、部署和回滚的企业 Agent 资产。

#### 启动条件

- M3 两类 Golden Scenarios 使用同一执行与治理契约；
- Runtime Adapter 稳定；
- Evaluation Gate 能阻止不合格版本晋级；
- 真实历史证明可变配置覆盖会损害可追溯性。

#### 主要交付

- `AgentDefinition`：稳定身份、Owner、风险等级和生命周期；
- `AgentVersion`：不可变的模型、Prompt、Skill、Tool、Knowledge 和 Policy 引用快照；
- `AgentDeployment`：Version 与 environment、tenant、traffic scope 的绑定；
- Draft、Evaluated、Approved、Active、Suspended、Retired 状态；
- 灰度、激活、暂停、回滚和历史引用；
- `CustomAgent` 兼容迁移 Adapter。

#### 退出门

- 配置变更产生新版本，不覆盖历史；
- 历史 Run 可还原实际 Agent、Model、Skill、Tool 和 Policy 版本；
- 未通过 Evaluation 或审批的版本不能进入受控环境；
- 回滚不修改历史事实；
- 两类 Golden Scenarios 可以独立升级和回滚 Agent。

#### 裁剪

- 不建设数字员工、组织编制或绩效语义；
- 不把 AgentVersion 扩张成通用软件包系统。

### 9.2 M5：最小 Workflow 生命周期

**候选周期：** 2027.12–2028.03
**目标：** 在稳定执行和治理原语上提供确定性编排。

#### 启动条件

- M4 Agent Version/Deployment 已用于真实运行；
- Task/Run 经两个场景验证；
- 真实需求持续需要多步骤等待、分支、并行或补偿，单一 Agent Loop 无法清晰表达。

#### 主要交付

- `WorkflowDefinition`、不可变 `WorkflowVersion` 和 `WorkflowRun`；
- 最小 DAG；
- Agent、Tool、Approval 和 Condition 四类节点；
- 输入输出 Schema、超时、有限重试、幂等和等待恢复；
- 失败分支和外部副作用补偿声明；
- Event 和 Schedule 入口 Adapter；
- 节点统一创建 Action 或子 Run。

#### 退出门

- WorkflowVersion 不可变，历史运行可解释；
- 等待审批或外部事件后可以安全恢复；
- 节点重试不重复已提交副作用；
- AIOps 最小 Runbook 和研究发布流程使用同一 DAG 原语；
- 简单 Task 不被迫包装为 Workflow；
- Workflow 节点不能绕过 Policy、Audit 和生命周期。

#### 裁剪

- 不做 BPMN 全兼容、拖拽式低代码、通用 RPA；
- 不允许 Skill 隐藏第二套复杂 DAG 状态机。

### 9.3 M6：数据、Connector 与 Knowledge 治理

**候选周期：** 2028.04–2028.07
**目标：** 让外部数据访问拥有统一身份、凭证、权限、来源和审计语义。

#### 启动条件

- 外部系统接入成为主要重复成本；
- 至少存在两类不同接入模式；
- 当前 MCP 和垂直集成不能一致回答谁以什么权限访问了什么数据。

#### 主要交付

- `ConnectorDefinition`、`ConnectorInstance` 和 `CredentialRef`；
- Secret Provider Contract，优先集成成熟 Secret Manager；
- Schema、Health、Rate Limit、Sync State 和标准错误；
- `KnowledgeSource`、Document、Chunk、IndexVersion 和 ACL；
- Retrieval Audit、Data Classification 和 Provenance；
- Connector、Artifact、Run 和 Evaluation 关联；
- 至少两个参考 Connector。

#### 退出门

- Credential 仅通过引用按需注入，不进入 Prompt、日志或普通配置响应；
- User 和 Agent 不能绕过 tenant/data ACL 获取检索结果；
- Artifact 可追溯 source、connector、index version 和 run；
- Connector 或 Index 变化能触发相关 Evaluation；
- 两个参考 Connector 通过统一 Contract Test。

#### 裁剪

- 不建设通用 ETL/iPaaS；
- 不自研 Vault、搜索引擎或数据目录；
- 不追求大量首发 SaaS Connector。

### 9.4 M7：扩展供应链与企业私有目录

**候选周期：** 2028.08–2028.11
**目标：** 让团队在不修改内核的情况下安全扩展 PrismOS。

#### 启动条件

- 至少三类真实扩展由不同边界独立维护；
- AIOps、企业研究或 Connector 出现独立发布需求；
- Policy、Audit、隔离和兼容契约稳定；
- 直接修改主仓库已经成为升级或维护瓶颈。

#### 主要交付

- Extension Package Manifest、SDK、CLI 和模板；
- Dependency、Permission、Secret、Runtime 和 Compatibility 声明；
- Install、Enable、Pause、Upgrade、Rollback 和 Uninstall 生命周期；
- 签名、来源、权限差异、基础扫描和兼容验证；
- 官方扩展库和企业私有目录；
- Owner、维护状态、使用和质量报告；
- AIOps 作为独立扩展安装或禁用。

#### 退出门

- 扩展不能绕过 Policy、Approval、Audit、Secret 和 tenant isolation；
- 升级前可查看权限变化、兼容性和 Evaluation；
- 安装或升级失败可回滚；
- 禁用所有垂直扩展后核心仍运行；
- 私有目录完成真实组织内发布、升级和回滚验证。

#### 裁剪

- 不建设公共 Marketplace；
- 不建设评分、交易、分成和网络效应机制；
- 不以插件数量作为成功指标。

## 10. 条件路线

### 10.1 C1：Runtime Independence

默认继续使用 DeerFlow/LangGraph。Runtime Independence 是需要证明投资合理性的独立决策，不是预定版本。

#### 进入预研的硬证据

满足至少一项：

- 现有 Runtime 无法满足已确认的恢复、取消、幂等或一致性要求；
- 无法在可接受成本内实现必要的 Policy Enforcement、隔离或审计；
- 基准证明性能、延迟或资源成本无法通过配置与 Adapter 优化解决；
- 上游维护、许可证、兼容性或方向形成不可接受风险；
- 第二种成熟 Runtime 的适配实验证明多 Runtime 具有真实价值。

#### 正式立项条件

- M3 Runtime Contract Test 已稳定；
- 已完成一个有时间边界的替代 Runtime Spike；
- 存在量化基线、替换收益和长期维护成本；
- API、数据、Agent、Skill、执行历史和回滚有兼容方案；
- 扩展当前 Runtime 和采用另一成熟 Runtime 均被证明不足，才考虑自研。

#### 验收

- 两类 Golden Scenarios 的 Contract/Evaluation 不低于原 Runtime；
- 上层 Policy、Task/Run、Workflow 和 Artifact Schema 不修改；
- 历史执行可解释；
- 可在一个发布窗口内回滚；
- 新 Runtime 有明确 Owner 和维护预算。

### 10.2 C2：Federation

Federation 只解决跨独立组织的身份、信任、授权、责任和能力交换，不用于包装普通多租户或 API 集成。

#### 研究条件

- 至少两个真实组织持续进行双向 Agent 或能力协作；
- API、Webhook、MCP 或 Connector 被证明不足；
- 双方需要保持独立身份域、Policy、数据边界和审计责任；
- 已有明确 SLA、成本、责任和争议处理需求。

#### 立项条件

- 跨组织 Subject/Workload Identity；
- Trust Establishment、Revocation 和 Key Rotation；
- Policy Decision 和最小信息披露协议；
- Audit Evidence 交换和责任归属；
- 数据驻留、合规、计量和故障隔离；
- 至少一个真实参与方联合试点。

在条件满足前，只跟踪协议和标准，不开发 Federation Control Plane。

## 11. 共同晋级规则

候选里程碑只有同时满足以下条件才启动：

1. 上一里程碑退出门通过并保留可重复证据；
2. 至少两个真实需求指向同一平台原语；
3. 现有组件或 Adapter 已经不足，而非仅仅不够漂亮；
4. 工作可以在 3–4 个月内形成端到端闭环；
5. 不破坏兼容边界和跨场景解耦；
6. 有明确 Owner、迁移路径和停止条件。

条件不满足时，团队继续加固上一阶段、偿还质量债或扩充 Golden Scenarios，不因日期到达自动进入下一里程碑。

## 12. 错误处理与安全原则

### 12.1 默认决策

- 对有外部副作用的受控 Action，Policy 或 Audit 基础设施不可用时 Fail Closed；
- 对只读、无副作用路径是否降级，必须由显式 Risk Policy 决定；
- Runtime Adapter 不得把超时、未知状态或不支持能力伪装成成功；
- Approval 必须有有效期、Context Hash 或 Decision Version，避免批准后语义漂移。

### 12.2 状态与事实

- Task/Run Store 是执行生命周期事实来源；
- Audit 是不可变证据流，不代替状态机；
- Runtime Checkpoint 是恢复设施，不代替业务级 Run；
- Artifact 保存结果和来源，不隐式表示成功；
- Evaluation 产生评价，不修改历史事实。

### 12.3 外部副作用

- 每项副作用 Action 必须有 idempotency key 或等价提交标识；
- 重试必须区分“未提交”“提交状态未知”和“已提交”；
- 不可补偿副作用必须在批准前显式呈现；
- Compensation 是声明和受控动作，不承诺分布式事务式自动回滚。

### 12.4 数据与 Secret

- Secret 只通过引用和最小范围注入；
- Prompt、普通日志、Artifact 和 API Response 不保存明文 Secret；
- Tenant Context 必须贯穿 Resource、Run、Policy、Artifact 和 Audit；
- 跨租户访问必须有显式系统身份和独立审计，不能依赖隐式管理员权限。

## 13. 测试与验证策略

### 13.1 四类基础发布门

每个里程碑必须同时通过：

1. **Contract Gate**：Schema、API、状态转换、Adapter 和兼容契约；
2. **Golden Scenario Gate**：成功、拒绝、审批、恢复和故障注入；
3. **Quality Gate**：新增测试全部通过，历史失败被隔离且持续下降；
4. **Migration Gate**：升级、双写、回滚和历史数据读取。

从 M3 开始增加 Evaluation Gate。涉及 Secret、Sandbox、外部副作用或跨租户数据时增加专项 Security Gate。

M1–M2 的 Golden Scenario 使用普通测试断言、故障注入结果和基线指标进行验收，不要求提前交付持久化 Evaluation 资源。M3 才将 Dataset、EvaluationRun、Score 和 Gate 建设为平台能力，并把已有场景基线迁入统一 Evaluation Contract。

### 13.2 Contract Test

至少覆盖：

- Schema version compatibility；
- Resource/Identity reference resolution；
- Policy Decision 三分支；
- Approval create/approve/reject/expire/resume；
- Task/Run 合法与非法状态转换；
- Retry、Cancel、Timeout 和 Idempotency；
- Runtime Adapter capability mapping；
- Audit correlation completeness；
- Artifact provenance；
- 插件禁用和领域隔离。

### 13.3 Golden Scenario Test

每个场景必须包含：

- 正常成功路径；
- Policy deny；
- require approval 后 approve；
- reject 和 expire；
- 进程或 Runtime 中断后恢复；
- 重复事件；
- Tool 超时和部分失败；
- Audit 或 Artifact 存储异常；
- 可获得的成本记录；M3 起增加持久化 Evaluation 记录。

### 13.4 质量债规则

当前“pytest 可收集”不等于“测试通过”。M1 必须建立失败清单、责任域和趋势基线。

- 新功能不能增加已知失败数量；
- 修改相关模块时必须修复或显式重分类相关历史失败；
- 前端 lint、typecheck、unit test 和 build 按阶段修复并逐步转为硬门；
- Release Notes 必须分别报告 passed、failed、skipped 和未执行项；
- 不以跳过或非阻塞方式掩盖平台核心契约失败。

## 14. 迁移与兼容策略

### 14.1 渐进迁移序列

基础对象的默认迁移模式是：

```text
Define versioned contract
  → Add sidecar/adapter generation
  → Dual write
  → Compare and reconcile
  → Switch read path
  → Observe
  → Retire legacy write only after an explicit decision
```

### 14.2 数据原则

- 新表和 Event Schema 从第一天带版本；
- 历史记录不做就地语义重写；
- 旧 ID 通过映射或 external reference 保留；
- 双写必须有一致性观测和补偿工具；
- Migration 必须支持 dry-run、backup guidance 和 rollback；
- 删除旧字段、表、API 或路径需要独立兼容决策，不作为普通重构附带完成。

### 14.3 Runtime 兼容

- M1–M2 允许 Adapter 靠近 LangGraph/DeerFlow；
- M3 后上层平台模块不得依赖 Runtime 私有类型；
- 保留现有 API、Skill、Agent 和历史数据行为；
- Runtime 替换不允许驱动平台核心 Schema 变化。

## 15. 核心度量

Roadmap 不以页面数、插件数、Agent 数或自动执行率作为主要成功指标。

| 维度 | 核心指标 |
|---|---|
| 治理覆盖 | 纳管 Action 比例、Decision 完整率、越权执行数、审批责任链完整率 |
| 执行可靠性 | 恢复成功率、取消完成率、重复副作用数、未知终态 Run 数 |
| 可追溯性 | Run—Action—Policy—Approval—Artifact—Audit 关联完整率、Schema 兼容性 |
| 质量与成本 | Golden Scenario 通过率、分项 Evaluation、回归拦截、延迟、单成功 Task 成本 |
| 平台化程度 | 两场景核心契约复用率、领域字段侵入数、Runtime 私有类型泄漏数、插件禁用测试 |

三条红线：

- 越权执行为零；
- 重复事件不得产生重复已提交副作用；
- 平台核心不得依赖 AIOps 领域对象。

其他指标在 M1–M2 建立真实基线后再设发布阈值，不提前编造无测量条件的固定 SLA。

## 16. 版本与发布治理

### 16.1 废止旧版本承诺

旧 v6 中 `v1.2 Agent Loop → v2.0 Federation` 的序列不再驱动实施。旧文档保留为历史设计和素材，不删除，但所有未实施条目必须重新映射到本 Capability Roadmap。

### 16.2 SemVer 与能力里程碑分离

- `0.x-alpha`：核心契约仍可能演进，只用于受控验证；
- `0.x-beta`：核心契约冻结、迁移路径稳定，并开始扩大部署；
- `1.0`：必须通过兼容、恢复、安全、升级、运维和质量门，不由日期或 M3 自动触发；
- 破坏性变更必须使用显式 Schema/API Version 和 Migration Window。

M1、M2、M3 是能力里程碑，不强制绑定 `0.2`、`0.3` 等固定版本号。每个里程碑结束时根据实际交付决定发布版本。

### 16.3 文档职责

- **白皮书：** 长期战略、问题、目标架构和原则；
- **Capability Roadmap：** 依赖、启动条件、退出门和裁剪；
- **Milestone Spec / ADR：** 单个阶段的确定契约和架构决策；
- **Implementation Plan：** 可执行任务、测试、迁移和提交序列；
- **Release Notes：** 已交付能力、验证证据、限制和兼容信息。

每个里程碑结束时更新能力成熟度矩阵，并根据证据决定下一阶段继续、裁剪、延后或终止。

## 17. Roadmap 成功判定

### 17.1 首年成功

到 M3 结束时，PrismOS 应能用同一核心完成 AIOps 与企业研究两种场景，并证明：

- 行为在副作用前可被确定性治理；
- 执行可持久化、恢复、取消、重试和去重；
- 人工审批可以安全等待和恢复；
- 结果、来源、策略、审批和执行历史可关联；
- Runtime 被 Adapter 隔离但没有为“自主”而重写；
- Evaluation 能阻止关键治理和质量回归；
- AIOps 可以禁用，平台核心仍成立。

### 17.2 长期成功

长期成功不是功能清单全部完成，而是：

- 新场景通过稳定契约接入，不修改内核；
- 新 Agent、Workflow、Connector 和扩展都不能绕过治理中轴；
- 每项重大平台投资都由运行证据触发；
- 历史执行在版本演进后仍然可解释；
- PrismOS 的竞争力来自治理与执行不变量，而不是拥有更多页面、插件或框架名词。

## 18. 下一步

本 Roadmap 批准后，第一项设计子项目是：

> **M1 / P0：PrismOS Governed Foundation Contract Baseline**

该子项目应先冻结 Resource、Identity Reference、Execution Envelope、AuditEvent、ID/Version/Tenant、兼容和迁移规则，并把 M1 的 AIOps Golden Scenario 写成 Contract Test 基线。

M1 需要独立设计和实施计划；不得把 M1–M3 一次性展开为巨型实现 Backlog。

---

## Appendix A：决策摘要

| 决策 | 结论 |
|---|---|
| 团队假设 | 1–2 名核心开发者为持续规划基线；M1 可按已批准的 4–5 人加速情景执行，但不改变里程碑顺序和退出门 |
| 演进方式 | 契约优先的纵向闭环 |
| 首年目标 | 治理闭环 → 执行生命周期 → 跨场景与质量证据 |
| 首个验证场景 | AI 运维，但与平台核心解耦 |
| 第二验证场景 | 受控企业研究与报告交付 |
| 当前 Runtime | 继续使用 DeerFlow/LangGraph |
| Workflow | Task/Run、Policy 和 Agent Version 稳定后再启动 |
| Marketplace | 不建设公共 Marketplace；只在证据满足后建设私有目录 |
| Runtime Independence | 证据触发，优先适配成熟 Runtime，自研为最后选项 |
| Federation | 真实跨组织需求和责任模型满足后才立项 |
| 旧 v6 Roadmap | 保留为历史材料，不再驱动实施 |

## Appendix B：Roadmap 依赖图

```text
M1 Governed Execution
  Resource / Envelope / Audit / Policy / Approval
                         ↓
M2 Execution Lifecycle
  Task / Run / Attempt / Action / Idempotency / Recovery
                         ↓
M3 Platform Evidence
  Runtime Contract / Evaluation / Second Golden Scenario
                         ↓
M4 Agent Lifecycle
  Definition / Version / Deployment / Rollback
                         ↓
M5 Workflow Lifecycle
  Versioned DAG / Wait / Resume / Compensation
                         ↓
M6 Data & Knowledge Governance
  Connector / SecretRef / ACL / Provenance
                         ↓
M7 Extension Supply Chain
  Package / SDK / Signature / Private Catalog

C1 Runtime Independence ── only when runtime evidence triggers it
C2 Federation           ── only when cross-organization evidence triggers it
```
