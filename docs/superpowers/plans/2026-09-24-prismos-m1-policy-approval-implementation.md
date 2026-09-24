# PrismOS M1 Policy/Approval 治理链实施计划

**状态：** 执行中；P0 已通过，M1 未通过退出门。
**设计：** [M1 增量 Spec](../specs/2026-09-24-prismos-m1-governed-action-design.md)、[ADR](../../strategy/adr/2026-09-24-m1-governed-action-boundary.md)、[真实调用图](../../strategy/2026-09-24-m1-entry-action-call-map.md)
**依据：** [批准的能力路线](../specs/2026-08-08-prismos-capability-roadmap-design.md)

## 已完成的起点

- P0 九个公开契约、AuditEvent 表与 JSONL dry-run 兼容工具已通过[契约基线门](../../../backend/docs/PLATFORM_CONTRACTS.md)。
- M1 私有模块已有 `PolicyRequest`、三分支 `PolicyDecision`、`Approval` 事实模型和纯状态转换；尚未公开导出或持久化。它们不能作为已经生效的 Policy/Approval 服务使用。
- AIOps 诊断 Gateway 已拒绝停用、跨租户 Agent；Lead Agent 已拒绝显式不可用 Agent 的默认回退。直通 LangGraph 的浏览器身份问题仍待处理。
- 当前 Golden fixture 的 `terminal.execute` 是 Schema 示例，未证明诊断 Agent 可以调用 SSH Terminal。DB 自定义 Agent 的 `tool_groups` 现已在 MCP 服务器发现前强制过滤；内置/社区工具还需独立治理。

## 顺序和工作包

| 序号 | 交付与修改面 | 验收及故障测试 | 启动依赖 |
| --- | --- | --- | --- |
| 1 | 已选只读 `read_file` 与首个副作用 Agent→AIOps 工单 webhook Adapter。沙箱写入存在 `bash`/`str_replace` 绕过，不能只治理 `write_file`。后续 Adapter 必须独占该 Agent Tool 的外部提交入口，并与规则触发的 `auto_ticket` 区分。 | 仍需从已认证请求到实际 Tool/Provider 的可执行集成测试；绕过 PEP 的调用路径有反例。 | 本计划与调用图 |
| 2 | 已实现 MCP 服务器精确选择：DB Agent 空数组保留为空且不加载 MCP，非空选择在 SDK 发现和 OAuth 前按服务器名过滤；缓存按 tenant/user/服务器集合分开，deferred tool_search 只含所选工具。默认 Agent/未指定组仍走旧行为；内置/社区工具不受 MCP 选择约束。 | 空配置、未知服务器、同名前缀服务器、缓存刷新、Agent 传参和内置工具兼容测试通过；旧 DB 空数组失去此前隐式 MCP 权限，需在试点放量前核对现有 Agent。 | 1 |
| 3 | 冻结 M1 契约：review `PolicyRequest`/`PolicyDecision`/`Approval` 的摘要算法、版本、过期和受控 Action 名；增加稳定 canonical context hash 生成器和拒绝敏感字段的输入 DTO；由 Contract Owner 一次性调整公共导出与文档。 | v1 round-trip、未知 schema、额外字段、tenant、UTC、三分支、领域解耦、上下文变化及 Secret 反例测试；P0 导出兼容。 | 1–2 |
| 4 | 决策与审批持久化：新增唯一 Alembic 迁移和最小 SQLModel 投影；`PolicyDecisionRepository` 按 `(tenant_id, request_id)` 幂等，`ApprovalRepository` tenant 范围查询并以版本列/CAS 更新状态。 | SQLite 和配置数据库迁移升级/降级；重复和并发 approve/reject/consume 只有一个有效终结；跨租户不可读写。 | 3 |
| 5 | 关键写入单元：扩展 AuditEvent repository 的事务内 append，PolicyDecision 与 `action.policy_evaluated` AuditEvent 同 session 提交；`require_approval` 同事务建 pending Approval；事务失败不得返回可执行 token。 | 决策、审计、审批任一写入失败全回滚；无外部调用；唯一键竞争返回同一事实或冲突。 | 4 |
| 6 | 确定性 Policy 服务：最小规则对只读/副作用分别求值，映射 Guardrail/Terminal 安全种子；不允许 Prompt、默认 allow 或 `fail_closed=False` 绕开纳管 Action。 | allow/deny/require_approval、策略版本、无配置、Provider 超时/异常、风险类别错误；副作用默认拒绝。 | 3、5 |
| 7 | Approval API/服务：Gateway 从会话取审批人和 tenant，核验角色、原请求者/权限、context hash/version 与截止时间；状态从数据库读取，纯转换在 CAS 事务内应用。 | create/approve/reject/expire/resume、重复操作、并发、撤权、跨租户、过期与版本变化；浏览器提交的身份字段不起授权作用。 | 4–6 |
| 8 | 受控提交标识：副作用 Adapter 有唯一 idempotency key 和 `not_submitted|submitted|unknown` 提交事实；恢复消费 Approval 后再重查权限并提交。外部超时进入 unknown，不自动重放。 | 重复请求只产生一次外部提交；Audit/Policy 故障提交次数零；超时不伪装成功，故障可人工核查。 | 1、5–7 |
| 9 | 兼容双写：Gateway JSONL、Terminal 审计与平台 Audit 对受控路径双写；非关键目标失败记录投递表/重放标识和指标，避免覆盖主事实。 | 旧读路径仍可读；双写故障可见、可重放且不含 Secret；关闭开关恢复旧路径。 | 5、8 |
| 10 | 可信执行入口：Gateway 绑定会话 tenant/user、Agent 可见性/启用与线程 Agent；LangGraph 仅接受已验证上下文或签名能力，运行时拒绝裸浏览器自报身份。Nginx 路由、旧线程不变和回退路径一并验证。 | 跨租户、停用、伪造 context、重放能力、旧线程改 Agent 均在实际 Tool 执行前拒绝。 | 1、7–8 |
| 11 | AIOps Golden Scenario 与最小 UI：实际诊断 Action 覆盖 allow、deny、审批、reject/expire、Policy/Audit 故障；界面从平台事实显示等待/结果，不以聊天消息推断。单租户、单 Action 开关放量。 | 成功、失败、撤权、关闭开关回退；操作员可从 Action 追到 tenant、actor/workload、run、decision、approval、policy version 和 result。 | 2–10 |
| 12 | M1 四门复核：Contract、Golden Scenario、Quality、Migration，另做副作用/Secret/tenant Security Gate；记录测试通过、跳过、历史失败及部署回滚证据。 | 仅当[批准路线的 M1 退出门](../specs/2026-08-08-prismos-capability-roadmap-design.md)全部满足时宣布 M1 完成；此前不启动 M2 生命周期。 | 1–11 |

## 实施规则

- 每项先添加能失败的测试，修复后跑目标测试、相邻回归和 `scripts/test-platform-contracts.sh`；Schema/迁移由一个 Owner 串行提交。每两周给出可运行演示和失败基线。
- P0 `task_id`/`run_id` 只作关联，不建状态机。Approval 状态不等于 Run 状态；LangGraph checkpoint 不等于审批事实。
- 功能开关默认关闭。关闭后不删除平台审计；新路径的关键决策/审计失败时 fail closed，不能偷偷退回旧副作用路径。
- 不把 `terminal.execute` fixture、独立 Terminal graph 或规则触发 `auto_ticket` 单独计作 AIOps Agent Golden Scenario。真实路径无法验证时维持开关关闭并先补有界 Action Adapter。
