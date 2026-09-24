# Octop 深度调研与 PrismOS 渐进式借鉴计划

**日期：** 2026-09-24

**状态：** 调研结论与分阶段实施方案；不替代已批准的 PrismOS Capability Roadmap

**证据版本：** PrismOS `73954f018fe1a9f59279d4060a99c0b9d0ad6eee`；Octop `c04aacc604a23ac05c00538f1bd4bc586fee6bb6`（`v1.0.2b2`）

**容量假设：** 延用[已批准的能力路线](../superpowers/specs/2026-08-08-prismos-capability-roadmap-design.md)：1–2 名持续核心开发者，每 3–4 个月形成一条可验证闭环；M1 可采用已经批准的 4–5 人加速编制。

## 1. 核心结论

Octop 值得借鉴的是一组协同工作的产品与工程模式：统一的消息入口、可恢复的会话投影、数据库驱动的定时任务、用户可管理的知识库、连接器与插件生命周期，以及简短的安装到日常使用路径。PrismOS 已有多租户、RBAC、Skill、MCP、文件、沙箱、LangGraph、IM 和终端基础；关键缺口是让它们共享同一执行、授权和审计链。

**实施顺序不变：M1 治理执行闭环 → M2 Task/Run 生命周期 → M3 Runtime 与质量证据 → M4–M7 按证据启动 Agent 资产、工作流、数据/知识和扩展供应链。** Octop 的能力作为每个阶段的用例和设计参考，不另起平行路线。首年不迁到单进程，不把用户级共享语义照搬到租户，也不开放任意插件或外部编码 Agent 执行。

本文件覆盖全部候选能力，但只有 M1 近期工作拆成下一步可执行的核验与迭代；**M1 的新增工作不能扩大已批准的退出门**。M2 之后各阶段在前一阶段退出门通过后，再写独立 Spec、ADR 和逐任务 Implementation Plan。日期用于容量规划，不构成自动晋级承诺。

**交互优先级：** 在每个已获准的能力阶段并行交付一个有界体验切片。近期优先验证“管理员完成配置 → 用户选择可用 Agent → 发起新对话 → 看见结果或明确的阻塞原因”。体验切片可以独立延后，不改变平台退出门和依赖顺序。

## 2. 方法和证据边界

- 阅读 Octop 固定提交的架构、ADR、API/ACP 文档与组合根、消息处理、cron、知识库、连接器、插件、团队和安全代码，并核对 `v1.0.2b2` 发布内容。
- 对照 PrismOS 当前代码、[白皮书差距审计](./agentos-prismos-gap-roadmap-review.md)、[批准的能力路线](../superpowers/specs/2026-08-08-prismos-capability-roadmap-design.md)和[M1/P0 实施计划](../superpowers/plans/2026-08-08-prismos-governed-foundation-contract-baseline.md)。
- 本次是静态调研；未运行 Octop，也未进行负载、渗透或故障恢复测试。文中的“已实现”指可找到代码和接口，不代表生产 SLA 或安全认证。
- 两个仓库采用 MIT 许可。优先借鉴模式并自行实现；若后续移植代码，另行审查版权声明、依赖许可和安全边界。

### 与已批准路线的一致性审核

- M2 的明确非目标是“通用调度平台”，因此 Octop 式 Schedule 产品试点移到 M5 的 Event/Schedule 入口 Adapter；M2 只验证 Run 可由模拟外部触发创建。
- M6 的正式退出门需要**两个参考 Connector**；可先以一个做首个纵向切片，但不能凭一个连接器宣称 M6 完成。
- M7 的启动门需要**至少三类真实扩展由不同边界独立维护**，不是两种内部扩展。
- M1 的承诺是治理型 AIOps Golden Scenario；额外 IM 入口只做现状核验与契约适配预研，不作为 M1 退出门或阻塞已有 P0/Policy/Approval 工作。
- 现有工作台已支持模型连通性测试、通用欢迎页和提问建议。交互切片复用这些能力，不重复建设。

## 3. Octop 架构与能力的代码级调研

| 子系统 | 固定版本事实 | 借鉴点 | PrismOS 的调整 |
| --- | --- | --- | --- |
| 组合根 | [`OctopServer.start`](https://github.com/TencentCloud/Octop/blob/c04aacc604a23ac05c00538f1bd4bc586fee6bb6/src/octop/infra/server.py)装配 DB、仓库、Agent、Gateway、Cron；[ADR 001](https://github.com/TencentCloud/Octop/blob/c04aacc604a23ac05c00538f1bd4bc586fee6bb6/docs/adr/001-single-process-model.md)明确无外部队列和独立 worker。 | 显式依赖、启动/关闭顺序、从持久状态重建。 | 保留 PrismOS Gateway/LangGraph/Frontend 的现有进程边界。Octop 的 ADR 也明确单机纵向扩展和 CPU 阻塞代价。 |
| 统一入口 | [`GlobalProcessor`](https://github.com/TencentCloud/Octop/blob/c04aacc604a23ac05c00538f1bd4bc586fee6bb6/src/octop/infra/gateway/process/processor.py#L127)汇合 Web、IM、CLI；[会话键](https://github.com/TencentCloud/Octop/blob/c04aacc604a23ac05c00538f1bd4bc586fee6bb6/docs/architecture.md#L70-L86)区分 Agent、通道、用户和群聊。 | 入口只负责身份解析、规范化、会话映射和回传。 | 必须从认证 Membership 或已验证通道绑定解析 tenant；不信任消息中自报 tenant。 |
| 定时任务 | [`CronManager`](https://github.com/TencentCloud/Octop/blob/c04aacc604a23ac05c00538f1bd4bc586fee6bb6/src/octop/infra/cron/manager.py#L50)从 DB 恢复调度；[`CronDeliveryService`](https://github.com/TencentCloud/Octop/blob/c04aacc604a23ac05c00538f1bd4bc586fee6bb6/src/octop/infra/cron/delivery.py#L49)在会话锁内执行并投影历史；[`CronJob`](https://github.com/TencentCloud/Octop/blob/c04aacc604a23ac05c00538f1bd4bc586fee6bb6/src/octop/infra/cron/job.py#L21)记录状态和审计。 | DB 是配置事实源；调度、执行、投递分责；支持 run-now。 | 代码没有证明分布式租约或端到端 exactly-once。M2 先冻结 Run/Attempt/幂等语义，M5 再把 cron 实现为带租约的 Run 触发器，不另建执行状态机。 |
| 知识库 | [`KnowledgeService`](https://github.com/TencentCloud/Octop/blob/c04aacc604a23ac05c00538f1bd4bc586fee6bb6/src/octop/infra/knowledge/service.py#L78)处理 owner/shared 可见性；[索引任务](https://github.com/TencentCloud/Octop/blob/c04aacc604a23ac05c00538f1bd4bc586fee6bb6/src/octop/infra/knowledge/jobs.py)支持中断恢复；[检索](https://github.com/TencentCloud/Octop/blob/c04aacc604a23ac05c00538f1bd4bc586fee6bb6/src/octop/infra/knowledge/retrieve.py)筛选可见库和 ready 文档并生成引用。 | 解析/索引状态、检索预算、引用来源、失败恢复。 | owner/shared 是实例级规则，不是租户 ACL；检索失败可降级但须对用户可见并留审计。完整知识治理到 M6。 |
| 连接器 | [`ConnectorService`](https://github.com/TencentCloud/Octop/blob/c04aacc604a23ac05c00538f1bd4bc586fee6bb6/src/octop/infra/connectors/service.py#L74)有实例、加密凭据、OAuth 刷新和 MCP 配置装配。 | 目录定义与安装实例分离；凭据、授权状态和健康检查闭环。 | PrismOS 需 tenant/owner、SecretRef、工具权限和同步状态；不能只扩展 MCP JSON。 |
| 插件 | [`PluginManager`](https://github.com/TencentCloud/Octop/blob/c04aacc604a23ac05c00538f1bd4bc586fee6bb6/src/octop/infra/agents/plugins/manager.py#L270)有 bundled seed、发现、安装、启停和工具目录；可从 ZIP/URL 安装并在主进程加载依赖。 | manifest、版本、安装/启用两种状态、UI 与工具元数据。 | 主进程执行第三方代码不适合企业扩展默认边界；先内部包规范，后建签名、权限、隔离、回滚。 |
| 团队/ACP | [团队服务](https://github.com/TencentCloud/Octop/blob/c04aacc604a23ac05c00538f1bd4bc586fee6bb6/src/octop/infra/agents/teams/service.py#L114)和 [TeamManager](https://github.com/TencentCloud/Octop/blob/c04aacc604a23ac05c00538f1bd4bc586fee6bb6/src/octop/infra/agents/teams/team_manager.py#L82)已有主持人/成员协作；[ACP 文档](https://github.com/TencentCloud/Octop/blob/c04aacc604a23ac05c00538f1bd4bc586fee6bb6/docs/acp.md)有双向集成。 | 团队可作为显式产品对象；外部执行器用协议和权限回传。 | 团队编排依赖 Agent Version、Run、Workflow；出站 ACP runner 是有副作用的执行器，先过 Policy、沙箱和审计。 |
| 安全默认值 | [`SecuritySettingsStore`](https://github.com/TencentCloud/Octop/blob/c04aacc604a23ac05c00538f1bd4bc586fee6bb6/src/octop/infra/agents/security/policy_store.py#L18-L27)在无配置时设置 `hitl.enabled=false` 和 `tool_guard={enabled:true, mode:warn}`。 | 风险规则和审批交互值得研究。 | README 的“安全内置”不代表所有高风险调用默认阻断。PrismOS 纳管副作用须以确定性 Decision 和经测试的 fail-closed 为准。 |

Octop 的主要经验是“入口 → 会话 → Agent → 投递”的完整用户路径。PrismOS 可以复用契约和体验设计，同时保留分服务结构。Octop 的 README 中部分长期 AgentTeams 描述与本次提交已存在的团队代码范围不同；估算依据以固定提交的代码和已发布接口为准。

## 4. PrismOS 起点与复用地图

| Octop 启发 | PrismOS 可复用基础 | 缺口 | 阶段 |
| --- | --- | --- | --- |
| 统一入口 | [MessageBus](../../backend/app/channels/message_bus.py)、[Feishu/Slack/Telegram](../../backend/app/channels/service.py)、Gateway 身份上下文 | Web、IM 和未来 Schedule 尚无同一受治理执行入口；外部身份到 tenant 绑定需冻结 | M1 只核验现有入口映射；M2 统一 Run 入口；后续按需求扩 IM |
| 可恢复调度 | 运维摘要等局部调度、LangGraph checkpoint | 通用 Schedule、Occurrence、租约、幂等和执行历史 | M2 验证通用 Run 可接外部触发；M5 交付 Schedule 入口 |
| 知识与引用 | [FileObject](../../backend/app/models/files.py)、Storage Provider、Memory、线程文件 | 语料、文档版本、ACL、索引状态、引用与检索审计 | M3 引用验证，M6 正式知识治理 |
| 连接器 | [租户 MCP API](../../backend/app/gateway/routers/mcp.py)和健康检查 | Connector Instance、SecretRef、授权范围、同步状态 | M6 |
| 插件生命周期 | [SPI 草图](../../backend/app/plugins/__init__.py)、[静态运维插件](../../backend/app/plugins/registry.py)、[状态 API](../../backend/app/gateway/routers/plugins.py) | 包格式、版本、权限、安装、升级、隔离、回滚 | M7 |
| 团队和 ACP | [CustomAgent](../../backend/app/models/agents.py)、subagent、Terminal interrupt/resume | 不可变版本、部署绑定、跨 Agent 授权、外部 runner 治理 | M4/M5 后按需求验证 |

### 工作台交互起点

| 用户路径 | 当前实现 | 下一步 |
| --- | --- | --- |
| 首次配置 | `/setup` 建立管理员；平台/租户模型管理页已有模型测试与启用状态。 | 在管理概览显示配置就绪与下一步链接；普通用户只看到可执行入口或联系管理员提示。 |
| 选择 Agent 并聊天 | Agent 列表支持搜索、创建和编辑；`AgentThreadContext` 已有 `agent_name`，但卡片只有编辑/删除操作，聊天页也没有贯通 Agent 选择。 | 新对话显示所选 Agent；已有对话保持原绑定。服务端完成可信身份、可见性和启用状态核验后才开放卡片直达聊天。 |
| 运行与审批 | 聊天展示流式结果，Terminal 有局部 interrupt/resume。 | M1 显示纳管动作的审批等待与结果；M2 使用平台 Run 状态作为刷新和恢复后的事实源。 |
| 结果来源 | File/Artifact 可查看，通用知识治理未成形。 | M3 在研究场景显示来源引用及失败提示；M6 才建设知识管理界面。 |

**安全前置事实：** 当前 Nginx 将 `/api/langgraph/` 直接转发给 LangGraph，浏览器提交的 `tenant_id`、`user_id`、`agent_name` 不能作为授权证据。Agent 卡片直达聊天必须等可信服务端入口校验会话、租户成员关系、Agent 可见性及启用状态，并把验证过的身份绑定到运行上下文；前端先行查询只改善提示，不构成安全门。

已有 [M1/P0 实施计划](../superpowers/plans/2026-08-08-prismos-governed-foundation-contract-baseline.md)规定 `app.platform` 契约边界、AuditEvent 最小持久化和兼容方式。**P0 契约基线现已落地并通过退出检查**，包含 v1 公开契约、AuditEvent 持久化、JSONL 兼容迁移和 AIOps fixture；验证证据见[平台契约基线](../../backend/docs/PLATFORM_CONTRACTS.md)。下一步在该边界上设计 M1 Policy/Approval 治理链，不创建第二套 ID、Audit 或 ExecutionEnvelope。

## 5. 目标架构与不变量

```text
Web / API / IM / Event / Schedule
         │ 来源验证、认证、去重、身份绑定
         ▼
Tenant-aware Entry Adapter → Intent + ExecutionEnvelope
                                      │
                                      ▼
                           Task / Run / Attempt (M2)
                                      │
                              Policy / Approval
                                      │
                                      ▼
                          Runtime Adapter → LangGraph
                                      │
            ┌─────────────────────────┼──────────────────────────┐
            ▼                         ▼                          ▼
       Audit / Trace             Artifact / File           Delivery / Reply
            ▲                         ▲                          ▲
            └──────────── Knowledge / Connector / Plugin ───────┘
```

1. **入口不决定租户。** Web 从认证会话及 Membership 获取 tenant；IM 先验证平台签名/token，再通过管理员配置的通道绑定映射 tenant 和用户；Schedule 从持久定义读取绑定。缺失或歧义时拒绝，不猜默认租户。
2. **执行只有一个事实来源。** M1 的 `task_id/run_id` 仅为关联 ID；M2 后平台 Run 表拥有生命周期。LangGraph thread/checkpoint、聊天历史和 cron 状态是适配或投影。
3. **副作用先决策。** 连接器、插件工具、终端命令、ACP runner 和外发动作共用 `PolicyRequest → Decision → Approval? → Action`；关键 Audit 持久化失败时不得提交纳管副作用。
4. **投递至少一次，副作用去重。** 不承诺端到端 exactly-once；入口用 `tenant_id + source + external_event_id` 去重，occurrence/action 使用幂等键，外发带可追踪 delivery ID。
5. **隔离先于检索。** 文档与 chunk 带 tenant、owner、ACL、版本；检索前后校验权限；引用指向当前有权读取的版本；删除、撤权和重建索引有失效机制。
6. **不重写执行内核。** M1–M3 保留 DeerFlow/LangGraph、现有 API、Alembic 和数据路径；增加 Adapter 与 Contract Test。更换 Runtime 由 M3 证据触发。

### 待冻结接口草案

| 契约 | 最少字段或操作 | 阶段 |
| --- | --- | --- |
| `EntryContext` | tenant、actor、agent、origin、external_event_id、session_ref、received_at、correlation_id；来源特有数据放扩展字段 | M1 预研，M2 随 Run 入口冻结 |
| `SessionBinding` | tenant + channel + external conversation + principal ↔ 内部 thread；版本和状态 | M1 核验现状，M2 按需求持久化 |
| `ScheduleDefinition/Occurrence` | owner、tenant、trigger、时区、Agent Version；计划触发时间、幂等键、Run | M5 |
| `DeliveryAttempt` | destination、Run、内容引用、状态、重试、provider message ID | M5 Schedule/外发切片按需要 |
| `KnowledgeDocument/Chunk` | tenant、owner、ACL、原文件版本、索引状态、embedding model、引用锚点 | M6；M3 只定义引用输出 |
| `ConnectorInstance/SecretRef` | catalog kind、tenant、owner、授权范围、凭据引用、状态、续期 | M6 |
| `PluginPackage/Installation` | manifest version、摘要/签名、能力与权限声明、tenant binding、回滚状态 | M7 |

这些是后续 Spec 的输入，不是现在修改现有公开契约的授权。

## 6. 分阶段实施

### M1：治理执行闭环（已批准，2026.08–11）

**目标：** 现有 AIOps Agent/Tool 链路共享身份、Policy、Approval 和 Audit。Octop 式统一入口只做现状核验：不把新 IM 通道适配列为 M1 必需交付，也不让它阻塞 P0。

| 迭代 | 具体工作 | 可演示结果 | 退出证据 |
| --- | --- | --- | --- |
| 0：现状与基线 | 核对 M1/P0 任务状态；画 Web、现有 IM 和 Terminal 调用图；固定测试 passed/skipped/failed 基线；记录身份映射及重复消息风险。 | 真实入口到 LangGraph 的追踪图和 P0 未完成清单。 | ADR/契约差异清单、失败基线、无 Schema 冲突。 |
| 1：P0 契约 | 执行既有 P0 计划，交付 Resource/Identity/Execution/Audit 及最小持久化；将现有入口的来源字段映射到契约 fixture，不增加新产品 API。 | AIOps Action 得到稳定的 tenant、actor、task/run 关联 ID。 | 已批准 P0 契约和迁移门通过；核心不含运维领域必填字段。 |
| 2：治理链 | 一个只读工具和一个副作用工具接入 Policy PEP；从 Terminal interrupt/resume 抽出通用 Approval；管理 JSONL/Terminal 与统一 Audit 双写。 | 同一受控链路展示 allow、deny、require_approval。 | 允许、拒绝、审批、过期路径可追溯 tenant、actor、run、decision、action。 |
| 3：失败和收口 | 注入 Policy 不可用、Audit 写失败、审批后权限变化、重复输入；补最小链路查询和运行手册。IM 身份绑定只做独立评估记录。 | AIOps Golden Scenario 及失败后的可解释记录。 | 新增 Contract Test 全绿，历史失败不增加，M1 正式退出门通过。 |

P0 契约基线已完成，**不得把这一进度视为整个 M1 的 6–8 周交付承诺**。下一轮先核算 Policy/Approval、入口身份绑定及失败演练的工作量和真实吞吐量；两周一轮审查完成证据与阻塞项，必要时调整日历，不削弱退出门。

### M1 同期交互切片：首次成功执行

1. **管理员就绪入口：** 在租户管理概览复用已加载的可用模型状态，显示“可发起对话”或“需启用模型”，并链接现有租户模型管理页、Agent 列表和工作台；平台管理员在平台概览使用现有模型配置与测试入口。未加载成功时显示“状态未知”，不把网络错误解释为零模型。
2. **普通用户阻塞提示：** 工作台新对话在没有可用模型时显示原因和联系管理员指引，不暴露仅管理员可用的模型操作；有可用模型时保留现有欢迎页和建议问题。
3. **Agent 直达聊天：** 在服务端可信入口完成身份和 Agent 校验之后，卡片只对可用 Agent 显示“开始对话”；新线程绑定 `agent_name` 并在发送前展示名称，旧线程不受工作台当前选择影响。停用、越权或不存在的 Agent 必须在执行前拒绝，不能回退到默认 Agent。
4. **治理状态：** 纳管动作的 allow、deny、require_approval、超时及失败说明来自 M1 Decision/Approval，不由聊天文案推断；没有对应契约前只展示现有流式状态。

验收演示从管理员配置开始，以用户获得结果或明确阻塞原因结束。只读就绪引导由前端 `NEXT_PUBLIC_FIRST_RUN_TENANT_IDS` 按租户灰度，默认关闭；关闭后回到现有工作台路径。Agent 直达聊天及审批交互须另经服务端授权与治理契约门，不能仅靠此前端开关发布。此切片不增加 M1 正式退出门。

### M2：通用执行生命周期（已批准，规划 2026.12–2027.03）

**先决条件：** M1 纳管动作有持久 Decision/Audit，Approval 恢复可验证。

**主交付：** `Task → Run → Attempt → Action → Event`，状态迁移、超时、取消、恢复、有限重试、幂等和 LangGraph Adapter。将现有 Web/领域事件映射到同一 Run；用模拟外部触发验证去重与恢复。

**Octop 借鉴的设计预研：** 研究其 DB 恢复调度、会话锁、运行结果投递和状态审计；产出 Schedule → Run、DeliveryAttempt 的契约草案及单机/多实例故障矩阵。M2 不创建通用 Schedule API、数据库或用户入口，符合既有路线的“通用调度平台”为非目标。

**验收：** 重复外部输入不重复提交副作用；重启后 Run 状态可解释；撤权后新 Action 不执行；现有 Web/业务入口兼容测试通过。Schedule 产品试点等待 M5 的触发器入口立项。

### M3：Runtime 契约与质量证据（已批准，规划 2027.04–07）

**先决条件：** M2 生命周期及实际纳管入口的恢复和幂等测试通过；IM 仅在纳入 M2 范围后成为必需入口。

**主交付：** `Start/Stream/Pause/Resume/Cancel/GetState` Runtime Adapter Contract；基础 Evaluation、成本、Trace 关联；AIOps 和企业研究两个 Golden Scenarios 共用 Execution/Policy/Audit。

**Octop 启发的研究切片，预计 2–3 开发周：** 用现有 File/Artifact 提供最小来源引用：原文件 ID、版本/哈希、读取者、引用位置及 Run 关联。可在研究场景 Adapter 内使用受控语料验证检索，但**不发布通用知识库**或提前建 RAG 管理 UI。测量引用完整性、越权拒绝、检索失败后的可见降级和成本。

**验收：** 平台上层不依赖 LangGraph 私有类型；两个领域场景使用同一评测与审计链；Contract Test 和 Evaluation Gate 可重复运行。

### M2–M3 同期交互切片

- **M2：** 对话中读取平台 Run 状态，展示当前阶段、审批等待、失败原因、取消与允许的重试。刷新和服务重启后的展示以 Run 为准；现有聊天消息只作为内容投影。Schedule 仍是契约预研，不提供管理入口。
- **M3：** 研究场景结果显示原文件、版本、引用位置和 Artifact/Run 关联；打开来源时重新校验权限。检索失败时明确提示降级，评测覆盖引用完整性、越权拒绝与成本。

### M4–M7：按证据立项的候选阶段

| 里程碑 | 借鉴 Octop 后的 PrismOS 切片 | 启动门 | 退出门与范围 |
| --- | --- | --- | --- |
| **M4 Agent 资产**，规划 2027.08–11 | 从 `CustomAgent` 演进 Definition、不可变 Version、Deployment；草稿、发布、回滚。借鉴专家配置体验。 | M3 两场景复用核心，Agent 配置变更带来的复现问题有证据。 | 历史 Run 可解析当时版本；回滚不改历史；人格模板/专家市场只作 UI 候选。 |
| **M5 最小 Workflow**，规划 2027.12–2028.03 | Event/Schedule/Manual 入口，有限 DAG、Agent/Tool 节点、Approval 等待和补偿；先做单租户只读 Schedule → Run 试点，再按需求验证团队分工。 | M4 Version/Deployment 用于真实运行，且有跨步骤或定时执行的实际需求。 | 定时重复触发只生成一个业务 Run，重启后 occurrence 可解释；双 Agent 场景的授权和结果可追踪；不做通用 BPMN。 |
| **M6 数据、Connector、Knowledge 治理**，规划 2028.04–07 | 租户 Connector Catalog/Instance、SecretRef/Secret Provider、OAuth 刷新/撤销、健康；Knowledge Source/Document/Chunk/IndexVersion、ACL、引用和检索审计。先做一个纵向切片，正式退出前完成两个参考 Connector。 | 外部接入确成主要重复成本，至少两类不同接入模式，Policy/Artifact/Secret 边界清楚。 | 两个 Connector 通过统一契约测试；撤权后检索和调用失败，跨租户、索引残留、token 续期和外部故障有测试；不做通用 iPaaS。 |
| **M7 扩展供应链**，规划 2028.08–11 | 规范现有运维模块为版本化内置包，再做私有目录、签名/摘要、权限声明、租户安装、升级与回滚。 | 至少三类真实扩展由不同边界独立维护，且 Policy/Audit/隔离契约稳定。 | 不可信代码不在 Gateway 主进程加载；兼容、权限、依赖和回滚门通过；公共 Marketplace 延后。 |

候选阶段各交付一个最小管理交互：M4 发布/回滚与版本标识，M5 Schedule 运行记录和失败处置，M6 Connector 授权/健康及索引状态，M7 扩展权限、安装、升级和回滚。界面不得先于对应的平台事实源与授权契约发布。

若实证需求不足，停在上一稳定阶段。桌面壳、远程桌面、MBTI、大量社交平台和公共插件市场不会仅因 Octop 已提供而进入默认 Backlog。ACP 入站可在 M4 后做兼容试验；ACP 出站须等 Policy/Run/隔离成熟并有明确用例。

## 7. 容量与工作包

每个阶段仅保留一条平台主线。下表为**开发周**估算，不是日历承诺；M2 后的大项在启动前依据实际迁移和回归基线重新估算。

| 工作包 | 所有者 | 估算 | 前置条件 | 完成物 |
| --- | --- | ---: | --- | --- |
| M1 首次使用引导 | 工作台前端 | 与 P0 并行的小切片 | 现有模型状态接口、按租户 UI 开关 | 管理员就绪入口、普通用户无模型提示与回退；Agent 发起对话另受可信服务端入口门约束 |
| M1 入口事实映射与审计 | 平台后端 | P0 核验后重估 | P0 契约 | 现有 AIOps 链路的身份/关联映射、契约测试 |
| M1 Policy/Approval 贯通 | 平台后端 + 前端 | 4–6 | 身份和 Audit | 现有 AIOps 链路的副作用闭环、审批/恢复、故障注入 |
| M2 Task/Run 生命周期 | 平台后端 | 按 M2 正式计划重估 | M1 退出门 | Schema、迁移、状态机、恢复测试 |
| M2 Schedule 契约预研 | 平台后端 | 不进入 M2 交付容量 | Run/幂等语义 | 触发器/投递 ADR、故障矩阵，无产品接口 |
| M3 来源引用试点 | Runtime/Artifact + 场景 | 2–3 | Runtime/Artifact 关联 | 引用契约、研究评测、失败可见性 |
| M5 Schedule 首个试点 | 平台后端 + 工作台 | M5 立项时重估 | Workflow/Event 入口和 Agent Version | 单租户只读 Schedule → Run、重启与去重证据 |
| M6 Connector/Knowledge 纵向切片 | 集成/数据后端 | 届时重估 | SecretRef/Policy/ACL | 首个数据源和语料切片；M6 最终需两个参考 Connector |

每个两周迭代保留约 20% 容量用于回归、迁移和文档。超过两周不能演示端到端效果的包继续拆分；增加人力只能并行不冲突的工作，不能跳过依赖门。

## 8. 通用验收、迁移与回退

| 发布门 | 必须有的证据 |
| --- | --- |
| 契约 | Schema、状态图、权限矩阵、失败语义、旧 API/DB/数据路径兼容表、至少一个非运维 fixture。 |
| 隔离与安全 | 跨租户反例、伪造 IM 身份、过期/撤销授权、Policy/Audit 故障时的副作用控制、Secret 不进日志或模型上下文。 |
| 恢复与幂等 | 重启、重复 IM/webhook、cron 重叠、网络超时、投递成功但回执丢失、索引中断的故障注入。 |
| 质量 | 新测试 passed/skipped/failed 明细，既有失败基线不恶化；两个 Golden Scenarios 的 trace、artifact、成本和质量信号。 |
| 交互 | 首次任务从管理员配置到用户结果的演示录屏或脚本；无模型、无权限、停用 Agent、审批等待、失败与恢复提示；按租户开关开启/关闭路径。 |
| 运维 | 健康/积压视图、失败重试和人工处置、备份、迁移 dry-run、双写观测、版本回滚演练。 |

**迁移顺序：** 新表/契约 → 只读旁路观测 → 双写或双投影 → 单租户 feature flag → Golden Scenario → 扩大租户 → 停止旧写入 → 清理兼容层。每一步定义关闭开关后的行为；旧数据不在缺少备份、校验和回滚演练时原地覆盖。

**暂停晋级条件：** 无法从入口追到 Run/Decision/Audit；出现跨租户访问；故障后只能靠聊天历史猜状态；插件或连接器需要绕过授权；以“pytest 可收集”掩盖失败。先修主链，再开启新能力。

## 9. 风险与应对

| 风险 | 表现 | 应对 |
| --- | --- | --- |
| 功能追赶挤掉平台主轴 | UI、cron、RAG、插件各有状态和权限 | 每项借鉴绑定既有里程碑，复用 Execution/Policy/Audit 并通过退出门。 |
| 个人助手模型侵入企业多租户 | 照搬 owner/shared、全局插件开关 | 先写 tenant/owner/actor/ACL 不变量及反例测试。 |
| 单机调度误用于多实例 | 重复执行副作用 | M2 验证 Run 幂等语义；M5 的 Schedule 试点增加可观测租约与多实例故障测试，通过前只允许一个调度者。 |
| 外部扩展破坏隔离 | URL/ZIP 安装依赖并在 Gateway 进程执行 | M7 先内置包，再私有签名目录；依赖审查、沙箱和权限声明是安装门。 |
| 宣传与默认值不一致 | “有审批”却默认关闭，“有策略”却只警告 | 以实际默认值和故障注入判断控制；PrismOS 当前 guardrail 也默认关闭，M1 明确纳管动作集合。 |
| 路线膨胀 | 提前冻结两年 API 和人天 | 只冻结下一阶段契约；M4–M7 保留启动/退出门。 |

### 本次实施状态（2026-09-24）

- 已实现：租户管理概览的模型就绪与下一步指引；新对话无可用模型的分角色提示；`NEXT_PUBLIC_FIRST_RUN_TENANT_IDS` 默认关闭的按租户 UI 灰度，以及关闭开关后的旧路径。
- 已通过平台门：M1/P0 契约基线及其测试、迁移与兼容检查，见[平台契约基线](../../backend/docs/PLATFORM_CONTRACTS.md)。
- 待平台门：M1 Policy/Approval 治理闭环；可信的 LangGraph 执行身份绑定、Agent 可见性/启用校验；Agent 卡片直达聊天与审批状态。当前前端引导不代表 M1 已通过退出门。
- 待后续立项：M2–M7 的 Run、Runtime、Workflow、Connector/Knowledge 和扩展管理能力及对应体验切片。

## 10. 立即执行的下一步

1. 以已通过的[M1/P0 计划](../superpowers/plans/2026-08-08-prismos-governed-foundation-contract-baseline.md)和[契约基线证据](../../backend/docs/PLATFORM_CONTRACTS.md)为起点，冻结九个公开符号及迁移兼容边界，不创建平行平台包。
2. 固定一个 Web 请求、一个现有 IM 请求和一个 Terminal 副作用动作，形成调用图；M1 的 Golden Scenario fixture 只绑定既有 AIOps 链路。
3. 编写 Policy/Approval 的 M1 增量 Spec 与 ADR，落实 decision/audit-before-side-effect 顺序和失败回退；IM 的 `EntryContext` 与外部身份绑定先形成独立 ADR 候选，不扩大 M1 退出门。
4. 在现有 Nginx → LangGraph 请求路径上设计可信执行入口：从已认证会话解析 user/tenant，核验 Agent 可见性和启用状态，并绑定新线程 Agent；补跨租户、伪造上下文、停用后重试和旧线程不变的反例测试。通过前不开放 Agent 卡片的“开始对话”。
5. 按租户打开首次使用引导，记录管理员就绪与普通用户阻塞路径；执行 M1 治理迭代并通过退出门。M2 建 Run 后研究 Schedule 契约，产品试点在 M5 立项。

## 附录：主要证据

**Octop：** [架构](https://github.com/TencentCloud/Octop/blob/c04aacc604a23ac05c00538f1bd4bc586fee6bb6/docs/architecture.md)、[单进程 ADR](https://github.com/TencentCloud/Octop/blob/c04aacc604a23ac05c00538f1bd4bc586fee6bb6/docs/adr/001-single-process-model.md)、[API](https://github.com/TencentCloud/Octop/blob/c04aacc604a23ac05c00538f1bd4bc586fee6bb6/docs/api.md)、[ACP](https://github.com/TencentCloud/Octop/blob/c04aacc604a23ac05c00538f1bd4bc586fee6bb6/docs/acp.md)、[发布](https://github.com/TencentCloud/Octop/releases/tag/v1.0.2b2)、[源码](https://github.com/TencentCloud/Octop/tree/c04aacc604a23ac05c00538f1bd4bc586fee6bb6/src/octop/infra)。

**PrismOS：** [README](../../README_zh.md)、[架构](../../backend/docs/ARCHITECTURE.md)、[差距审计](./agentos-prismos-gap-roadmap-review.md)、[批准的能力路线](../superpowers/specs/2026-08-08-prismos-capability-roadmap-design.md)、[M1/P0 计划](../superpowers/plans/2026-08-08-prismos-governed-foundation-contract-baseline.md)。
