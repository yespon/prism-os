# PrismOS M1 Policy/Approval 治理执行增量设计

**状态：** 增量设计；P0 已通过，M1 退出门尚未通过。
**日期：** 2026-09-24
**决策记录：** [M1 受控 Action 边界](../../strategy/adr/2026-09-24-m1-governed-action-boundary.md)
**上位依据：** [能力路线 M1](./2026-08-08-prismos-capability-roadmap-design.md)、[Octop 借鉴计划](../../strategy/2026-09-24-octop-research-adoption-plan.md)

## 目标与范围

让现有 AIOps 链路中一个真实 Agent Action，在外部副作用前经过可信身份绑定、持久 Policy Decision、必要时的持久 Approval、关键 Audit，然后由受控入口提交。另选同一链路的一个只读 Action 验证风险分类。M1 的 `task_id`/`run_id` 仍为关联 ID；运行状态和重试/恢复语义属于 M2。

本设计保留 P0 的九个公开导出并增加 M1 契约符号、不把运维对象写入平台必填字段、不建立新的模型连通性测试接口，也不把 IM 新入口或 Agent 卡片直达聊天纳入治理链的退出条件。可信 LangGraph 入口是后续打开卡片直达的独立安全门。

## 当前实证与实施前置

完整调用图与接入风险见[入口与 Action 调用图](../../strategy/2026-09-24-m1-entry-action-call-map.md)。其中 `terminal.execute` fixture 不构成真实 AIOps→Terminal 路径证据；DB 自定义 Agent 的 MCP `tool_groups` 现已在服务器发现前过滤；内置/社区 Tool 和可信入口仍需独立治理。

| 现有部件 | 事实 | 需要补的边界 |
| --- | --- | --- |
| `backend/packages/harness/deerflow/guardrails/provider.py` | `GuardrailDecision.allow` 为布尔值，请求不带 tenant/ExecutionEnvelope | 平台三分支 Policy 契约与可信身份 Adapter |
| `backend/packages/harness/deerflow/guardrails/middleware.py` | Tool 执行前同步/异步调用 Provider，可选择 fail closed | 纳管 PEP 需持久决策、关键审计并禁止绕过；不能简单复用 `fail_closed=False` |
| `backend/app/services/terminal/security.py` | 命令安全返回 allow/block/ask | 映射成 Policy 输入；安全配置不能覆盖强制审计 |
| `backend/app/agent/terminal_graph.py` | interrupt/resume 使用 `MemorySaver` | 平台 Approval 持久事实、过期和恢复重检 |
| `backend/app/gateway/audit.py` 与 `backend/app/platform/audit` | JSONL 与平台 AuditEvent 独立 | 明确主写入和兼容双写/重放 |
| `backend/app/gateway/routers/alerts.py` | AIOps 诊断调用 LangGraph，并有 IncidentAction/通知等副作用 | 追踪实际 Action seam；确定只读和副作用各一个，不凭 fixture 推断真实路由 |

先记录 Web、已有 IM、Terminal 到真实执行函数的调用图。选定的 AIOps 副作用必须能由已认证入口追到实际外部提交点；无法证明时停止开关放量，先补适配点。

## 契约

`PolicyRequest` 包含 v1 schema、tenant、request ID、ExecutionEnvelope、action 名、资源引用或目标标识、显式 `read_only`/`side_effect` 风险类别、规范化上下文摘要、请求时间。临时 `ActionContextInput` 仅接收非敏感参数并生成规范摘要，参数不进入序列化契约。`PolicyDecision` 包含 decision ID、request ID、tenant、同一 execution/action/context hash、`allow|deny|require_approval`、policy ID/version、结构化 reason code、决策时间与有效期。未知 schema、额外字段、跨租户引用、naive datetime 一律拒绝。决策只包含决策事实，不复制命令正文或凭据。

`Approval` 包含 approval ID、decision ID、tenant、requester/approver、policy version、context hash、创建/到期/终结时间与 `pending|approved|rejected|expired|consumed` 状态。只有 `require_approval` 决策可创建；审批人不能凭浏览器参数选择 tenant 或替换 Action。`resume` 消费批准时再验证当前权限、decision version、context hash 和有效期。审批状态由数据库条件更新，重复和并发请求返回同一终态或冲突，不重复提交。

`GovernedAction` 入口输入已验证的 ExecutionEnvelope、Action 描述和稳定提交标识。该入口执行顺序为：身份和目标校验 → 风险分类 → Policy 计算 → 决策与关键审计同事务落库 → 可选审批创建/等待 → 恢复重检 → 调用外部系统 → 结果审计。deny、过期、撤权、数据库故障或未知决策均不触发副作用。外部超时保留“提交状态未知”供人工或受控查询确认，不自动重试。

## 数据与兼容

当前已建立 Decision/Approval 的独立表、租户范围读取与 Approval CAS，迁移接在 P0 唯一 head 后。关键 Decision 与 Audit 的同事务写入、审批授权接口和受控外部提交仍待实施，不能将独立表视为完成的治理闭环。

新增 PolicyDecision、Approval 与副作用提交标识的最小持久化表；字段及索引由独立迁移接在唯一 Alembic head 后。查询必须带 tenant。关键 Policy/Audit 使用同一 session 和事务；P0 Audit repository 可在不破坏既有 append API 的前提下增加事务内写入方法。审批更新使用受影响行数或版本字段做并发控制。

Gateway JSONL 和 `terminal_audit_logs` 继续读写；平台 Audit 为纳管路径的关键事实。兼容双写失败记录在可重放投递表，包含目的地、原事件 ID、重试计数和错误类别，不保存 Secret。关闭租户/Action 开关后仍走旧路径；平台记录保留供审计，不能反向删除已发生的 Action。

## 小型交互切片

纳管 Action 的聊天/操作界面从平台事实展示 `allow`、`deny`、`等待审批`、`已拒绝`、`已过期` 和失败原因，以及当前允许的下一步。审批按钮只能调用认证 Gateway 接口；审批过期或上下文变化时提示重新发起，不把旧批准复用。现有聊天消息可以解释动作，但不能作为决策或审批状态来源。

## 逐步交付与验收

1. **事实图与基线：** 固定一个 AIOps 只读工具和一个真实副作用，记录入口、身份来源、Tool/Action 调用点、旧审计写入点和 bypass 风险；收集相邻测试 passed/skipped/failed。产物为调用图和 seam 清单。未证明真实链路时不开放开关。
2. **契约：** test-first 加入 PolicyRequest/Decision、Approval 模型和三分支、tenant、UTC、版本、上下文摘要测试；P0 原九符号保持兼容，新增符号在 M1 契约冻结后单点导出。平台包仍不依赖 AIOps、Terminal 或 LangGraph。
3. **持久化：** Alembic 单链迁移；tenant 范围读取、唯一 request/decision、审批并发终结和提交标识去重；证明升级/降级不改写旧 JSONL/Terminal 表。
4. **确定性 Policy：** 最小规则先覆盖只读 allow、受控副作用 deny/require_approval 与明确 allow；配置缺失或计算异常 fail closed。Adapter 可读取 Guardrail/Terminal 安全判断，但必须产出有版本的 PolicyDecision。
5. **Approval 服务：** create/approve/reject/expire/resume，截止时间和 context hash/version 绑定；Gateway 使用认证身份并核验 tenant/授权。Terminal interrupt 只负责等待和展示。
6. **受控提交：** 决策与关键审计同事务落库后才允许 side effect；记录稳定 idempotency key 和提交状态。注入审计失败、Policy 超时、重复请求、外部超时、权限撤销并断言副作用次数。
7. **兼容和场景：** Gateway/Terminal 双写失败进入可观测重放；真实 AIOps allow/deny/approval/reject/expire 路径通过，AIOps 禁用时平台契约仍可测。单租户、单 Action 开关先行，逐步扩大。
8. **退出门：** 检查所有纳管 Action 的持久 Decision 及 tenant/actor/workload/run/approval/policy version/result 追溯，新增契约全绿，历史失败不增加，迁移及回滚、故障演练通过；只有此时宣告 M1 完成。

每两周评审可运行演示、失败基线、完成率与容量。若 P0 以后的安全门受阻，延后交互切片放量，不提前启动 M2 Task/Run 生命周期。
