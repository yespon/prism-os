# PrismOS M1 Policy/Approval 治理链实施计划

**状态：** 执行中；P0 已通过，M1 未通过退出门。
**设计：** [M1 增量 Spec](../specs/2026-09-24-prismos-m1-governed-action-design.md)、[ADR](../../strategy/adr/2026-09-24-m1-governed-action-boundary.md)、[真实调用图](../../strategy/2026-09-24-m1-entry-action-call-map.md)
**依据：** [批准的能力路线](../specs/2026-08-08-prismos-capability-roadmap-design.md)

## 已完成的起点

- P0 九个公开契约、AuditEvent 表与 JSONL dry-run 兼容工具已通过[契约基线门](../../../backend/docs/PLATFORM_CONTRACTS.md)。
- M1 已公开 `ActionContextInput`、`hash_action_context`、`PolicyRequest`、三分支 `PolicyDecision` 与 `Approval` 契约；Decision/Approval 与提交事实已持久化。决策、关键 Audit 与待审批事实同事务提交；内部 Policy、Approval API 及默认关闭的工单 Adapter 已实现。可信 Agent Tool 入口尚未接入，不能作为已经生效的治理执行服务使用。
- AIOps 诊断 Gateway 已拒绝停用、跨租户 Agent；Lead Agent 已拒绝显式不可用 Agent 的默认回退。直通 LangGraph 的浏览器身份问题仍待处理。
- 当前 Golden fixture 的 `terminal.execute` 是 Schema 示例，未证明诊断 Agent 可以调用 SSH Terminal。DB 自定义 Agent 的 `tool_groups` 现已在 MCP 服务器发现前强制过滤；内置/社区工具还需独立治理。

## 顺序和工作包

| 序号 | 交付与修改面 | 验收及故障测试 | 启动依赖 |
| --- | --- | --- | --- |
| 1 | 已选只读 `read_file` 与首个副作用 Agent→AIOps 工单 webhook Adapter。沙箱写入存在 `bash`/`str_replace` 绕过，不能只治理 `write_file`。内部 Adapter 已建立；后续 Agent Tool 必须独占该受控提交入口，并与规则触发的 `auto_ticket` 区分。 | 仍需从已认证请求到实际 Tool/Provider 的可执行集成测试；绕过 PEP 的调用路径有反例。 | 本计划与调用图 |
| 2 | 已实现 MCP 服务器精确选择：DB Agent 空数组保留为空且不加载 MCP，非空选择在 SDK 发现和 OAuth 前按服务器名过滤；缓存按 tenant/user/服务器集合分开，deferred tool_search 只含所选工具。默认 Agent/未指定组仍走旧行为；内置/社区工具不受 MCP 选择约束。 | 空配置、未知服务器、同名前缀服务器、缓存刷新、Agent 传参和内置工具兼容测试通过；旧 DB 空数组失去此前隐式 MCP 权限，需在试点放量前核对现有 Agent。 | 1 |
| 3 | M1 契约已增加 canonical Action context hash 和拒绝敏感键的临时输入 DTO，公开 Policy/Approval 事实模型及五个增量符号；原 P0 九符号保持兼容。首个受控 Action 命名为 `ticket.create`，供内部有界 Adapter 使用。 | 三分支、tenant、UTC、过期、上下文变化、非规范 JSON、敏感键及公开导出测试通过；内部持久服务见工作包 4–8。 | 1–2 |
| 4 | 已新增唯一 Alembic 迁移、Decision/Approval SQLModel 投影、tenant 范围查询、Decision 幂等与 Approval 版本 CAS；Approval 创建须绑定已持久化的 `require_approval` Decision。 | 临时 SQLite 升级/降级/再升级、重复写入、跨租户和并发 approve/reject 测试通过；目标部署数据库及服务重启场景在集成门复核。 | 3 |
| 5 | 已新增 AuditEvent 事务内 append 和 `PolicyFactWriter`：Decision、`action.policy_evaluated` AuditEvent、必要时的 pending Approval 同 session 提交；只返回完成信号，不生成可执行 token。 | 三分支和重复写入通过；Decision、Audit、Approval 写入冲突均回滚，孤立 Decision fail closed；目标数据库并发唯一键竞争仍需在集成门复核。 | 4 |
| 6 | 已实现内部确定性 Policy 服务：按可信配置显式匹配 Action/风险类别，旧 Guardrail/Terminal 结果仅能收紧规则，结果经原子写入单元持久化；尚未接入实际 PEP，因此 Prompt 与旧 `fail_closed=False` 的绕过问题留在受控入口处理。 | 三分支、版本、无配置、Provider 超时/异常、风险类别错误、缺失 actor、重复请求及已批准审批不重开均通过；副作用未配置默认拒绝。 | 3、5 |
| 7 | 已新增 Approval 服务和 Gateway read/approve/reject API：tenant 与审批人取自认证会话，操作时重查租户启用状态、成员角色与原请求者有效身份；内部 consume 在恢复时重查 Decision、context/version、权限与期限，并以 CAS 持久化。pending 由 Policy 服务创建，内部恢复提交已接入工作包 8；可信 Agent Tool 尚未接入。 | 授权、自审批、撤权、停用租户、跨租户、过期、reject、重复审阅、上下文变更与状态冲突测试通过；浏览器身份字段无法覆写会话。实际 Action 恢复/资源授权及部署数据库并发仍待工作包 8/集成门。 | 4–6 |
| 8 | 已新增提交事实表与唯一迁移、本地稳定 idempotency key、`not_submitted→unknown→submitted` CAS，以及默认关闭的 Agent→AIOps 工单内部 Adapter。Adapter 重查租户 Incident、启用的来源配置、请求者权限和 payload/目标摘要；审批恢复先消费，再占位并调用现有 webhook。Provider 可传幂等键，但接收端未承诺去重；超时或结果写入失败保留 unknown，不自动重发。人工工单与规则 `auto_ticket` 仍是独立旧路径。 | 并发占位只有一个成功；allow、deny、审批等待/恢复、撤权、上下文变化、Audit 故障和超时反例通过；真实 Incident→AlertSource 解析及迁移升降级通过。Agent Tool 尚未注册，可信入口与真实已认证请求→Tool/Provider 的集成门留给工作包 10–11；结果审计和兼容双写留给工作包 9。 | 1、5–7 |
| 9 | 兼容双写：Gateway JSONL、Terminal 审计与平台 Audit 对受控路径双写；非关键目标失败记录投递表/重放标识和指标，避免覆盖主事实。 | 旧读路径仍可读；双写故障可见、可重放且不含 Secret；关闭开关恢复旧路径。 | 5、8 |
| 10 | 可信执行入口：Gateway 绑定会话 tenant/user、Agent 可见性/启用与线程 Agent；LangGraph 仅接受已验证上下文或签名能力，运行时拒绝裸浏览器自报身份。Nginx 路由、旧线程不变和回退路径一并验证。 | 跨租户、停用、伪造 context、重放能力、旧线程改 Agent 均在实际 Tool 执行前拒绝。 | 1、7–8 |
| 11 | AIOps Golden Scenario 与最小 UI：实际诊断 Action 覆盖 allow、deny、审批、reject/expire、Policy/Audit 故障；界面从平台事实显示等待/结果，不以聊天消息推断。单租户、单 Action 开关放量。 | 成功、失败、撤权、关闭开关回退；操作员可从 Action 追到 tenant、actor/workload、run、decision、approval、policy version 和 result。 | 2–10 |
| 12 | M1 四门复核：Contract、Golden Scenario、Quality、Migration，另做副作用/Secret/tenant Security Gate；记录测试通过、跳过、历史失败及部署回滚证据。 | 仅当[批准路线的 M1 退出门](../specs/2026-08-08-prismos-capability-roadmap-design.md)全部满足时宣布 M1 完成；此前不启动 M2 生命周期。 | 1–11 |

## 实施规则

- 每项先添加能失败的测试，修复后跑目标测试、相邻回归和 `scripts/test-platform-contracts.sh`；Schema/迁移由一个 Owner 串行提交。每两周给出可运行演示和失败基线。
- P0 `task_id`/`run_id` 只作关联，不建状态机。Approval 状态不等于 Run 状态；LangGraph checkpoint 不等于审批事实。
- 功能开关默认关闭。关闭后不删除平台审计；新路径的关键决策/审计失败时 fail closed，不能偷偷退回旧副作用路径。
- 不把 `terminal.execute` fixture、独立 Terminal graph 或规则触发 `auto_ticket` 单独计作 AIOps Agent Golden Scenario。真实路径无法验证时维持开关关闭并先补有界 Action Adapter。
