# ADR: M1 受控 Action 的决策、审批与提交边界

**状态：** 已选定用于 M1 增量设计；实现和退出门仍待完成。
**日期：** 2026-09-24
**依据：** [批准的能力路线](../../superpowers/specs/2026-08-08-prismos-capability-roadmap-design.md)、[P0 契约基线](../../../backend/docs/PLATFORM_CONTRACTS.md)

## 背景

P0 已冻结九个公开符号及 AuditEvent 持久化，但 `policy_decision_id`、`approval_id` 仍只是引用。现有 Guardrail Provider 接收 tool name/input，返回布尔 allow/deny；它没有可信租户、完整 ExecutionEnvelope、三分支决策或持久审计。Terminal security 会返回 allow/block/ask；Terminal graph 的 `interrupt`/`resume` 和 `MemorySaver` 无法承担跨进程、过期与权限变化后的审批事实。Gateway JSONL、Terminal 审计表与新平台审计仍是独立写入路径。Nginx 对 `/api/langgraph/` 的直通代理不能把浏览器提交的身份字段提升为授权证据。

## 决策

1. `app.platform` 拥有领域无关的 `PolicyRequest`、`PolicyDecision`、`Approval` 契约及服务。`ExecutionEnvelope`、AuditEvent 和 v1 schema 沿用 P0，不另建 ID 或生命周期模型。M1 的 task/run 继续只表示关联 ID。
2. 可信入口先从认证会话解析 tenant、actor 和成员关系，再构建不可由浏览器覆写的 ExecutionEnvelope。Adapter 将实际 Action 名、资源与风险分类映射成 PolicyRequest；Policy 只决定 `allow`、`deny`、`require_approval`，不执行动作。
3. 决策以独立版本和请求内容摘要标识。纳管副作用在执行前，必须将 PolicyDecision 与关键 AuditEvent 在同一个数据库事务中提交；任一写入失败则拒绝执行。`require_approval` 还须持久化待审批事实。当前工单的 JSONL/IncidentAction 兼容投递在主事务成功后进行，投递失败进入可观测的重放队列，不得阻断或改写已提交的平台事实。Terminal 待命令真正纳管后再接入对应双写。
4. Approval 有明确截止时间、tenant、actor/approver、decision ID、policy version、context hash 和状态。approve/reject/expire 是条件更新；同一审批只允许一次有效终结。resume 时重新核对租户、当前权限、未过期状态、decision version 与完整上下文摘要。批准只授权同一动作上下文，不能授权变更后的参数或目标。
5. 副作用由唯一受控执行入口提交，提交标识/idempotency key 与 decision、approval 关联。外部调用结果区分未提交、已提交、提交状态未知；未知状态不自动重放。Adapter 必须证明真实调用不能绕开该入口。只读动作的降级规则必须由显式 Risk Policy 决定；M1 默认也拒绝不确定状态。
6. Terminal 的安全规则和 Guardrail Provider 可作为 Policy 输入或 PEP 适配器，但不能单独充当平台决策事实。现有 Terminal interrupt 可作为 UI 暂停信号，持久审批状态以平台记录为准。旧路径在功能开关关闭时保持可用；打开开关仅纳管经过端到端验证的租户与 Action。

## 约束与取舍

- 事务保证的是决策及关键审计**先于**副作用持久化，不承诺数据库与外部系统的分布式原子性。外部结果另记不可变审计；若结果审计失败，记录可重放的提交状态并告警，不把未知结果伪装为成功。
- 不在 M1 引入 Task/Run 表、恢复状态机、Schedule、通用插件权限或持久 Evaluation；它们属于后续里程碑。
- 不把 Alert/Incident/Host/Command 设为平台必填字段。敏感命令内容或凭据不进入 Policy/Audit 普通 payload；需要凭据时只使用已批准的 `SecretRef` 方向。
- 不能假定 AIOps 诊断与 Terminal 副作用已有完整调用链。先画真实入口图并验证实际 Tool/Action seam，再选择 Golden Scenario 的受控动作；不以独立 Terminal 演示冒充 AIOps 端到端场景。

## 验证

- 三分支决策、审批 approve/reject/expire/resume、重复请求、并发终结、上下文变化、policy version 变化、跨租户与撤权均有契约和持久化测试。
- Policy/数据库不可用、关键 Audit 失败时，副作用函数调用次数为零；重复提交只有一个外部提交标识。外部超时标记未知，不盲目重试。
- 禁用 AIOps 插件后平台 Policy/Approval 测试可运行；启用的真实 AIOps Golden Scenario 覆盖 allow、deny、require_approval 和失败路径。
- 双写失败可查询、可重放；关闭租户开关回到现有路径，迁移保留旧审计读法。M1 退出仍由批准路线的完整四类门判定。
