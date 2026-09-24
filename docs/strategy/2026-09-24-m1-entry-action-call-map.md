# M1 入口与 Action 调用图（代码事实）

**日期：** 2026-09-24
**用途：** 确定首个受控 AIOps Action 的真实接入点；本图不代表 M1 治理链已启用。

## AIOps 诊断

```text
POST /incidents/{id}/diagnose
  → Gateway 会话 tenant/user → tenant 内 Incident 查询
  → CustomAgent 查询：同租户 + 本人/tenant-shared
  → build_incident_diagnosis_prompt（读取信号、相似事件、变更）
  → _run_diagnosis_background_task
  → LangGraph SDK threads.create / runs.stream(context={agent_name,user_id,tenant_id})
  → make_lead_agent → get_available_tools(groups=agent_config.tool_groups)
  → Lead Agent Tool 调用 → Sandbox / 社区工具 / MCP
```

代码位置：`backend/app/gateway/routers/alerts.py` 的 `diagnose_incident`、`_run_diagnosis_background_task`；`backend/app/alerting/diagnosis_helper.py`；`backend/packages/harness/deerflow/agents/lead_agent/agent.py`；`backend/packages/harness/deerflow/tools/tools.py`。

- Gateway 诊断入口校验会话、tenant、Agent 所有者/共享范围；本分支已补 `CustomAgent.enabled` 过滤和跨租户/停用反例测试。Lead Agent 对显式指定但不可用的 Agent 也已拒绝默认回退。背景任务把 tenant/user/agent 写入 LangGraph context；这组字段在直通 LangGraph 浏览器路径中仍不能视为可信授权。
- 此前 `get_available_tools(groups=...)` 忽略 `groups`；本分支已让 DB 自定义 Agent 的 `tool_groups` 按 MCP 服务器精确名称过滤，并按所选服务器隔离缓存和 deferred tool_search。空数组现在表示不加载 MCP；未指定组的默认/旧调用者继续使用原有 MCP 集合。内置沙箱和社区工具仍可用，`tool_groups` 不能替代对 `bash`、`write_file` 等 Action 的 Policy。`diagnosis_helper.py` 中的工具分组提示依然只是 Prompt。
- Lead Agent 的 GuardrailMiddleware 只在 `guardrails.enabled` 且配置 Provider 时装配；当前 Provider 只返回布尔 allow/deny，没有平台 PolicyDecision 或持久审批。
- `agent_name == "terminal-agent"` 才进入内置 Terminal Agent 分支。普通 AIOps 自定义 Agent 并不因 Golden fixture 中的 `terminal.execute` 获得 SSH Terminal 工具。因此 fixture 只证明平台 Schema 可容纳该 Action，**不是实际 AIOps Agent→Terminal 执行证据**。

## Alert 事件副作用

```text
Alert source → process_alert → find_or_create_incident → DB commit
  ├─ schedule_notification → _publish → message bus publish → IncidentAction audit
  ├─ _schedule_escalation_evaluation → apply_escalation_actions
  │   ├─ severity / owner DB 修改
  │   └─ auto_ticket → create_ticket_webhook → httpx POST
  └─ _schedule_agent_diagnosis → LangGraph Agent
```

代码位置：`backend/app/alerting/ingest.py`、`escalation.py`、`ticket_provider.py`、`notify.py`。通知和工单是**真实外部副作用**，但目前由规则/后台任务触发，不是诊断 Agent 的 Tool 调用。`_publish` 在消息发送后才尝试写 IncidentAction；M1 要求的关键审计先于副作用不能由该记录替代。

## Terminal 入口

```text
POST /terminal/invoke（会话 tenant/user）
  → terminal_graph.security_node → ask_approval interrupt（MemorySaver）
  → terminal_graph.execute_node → session.execute_command
  → CommandAuditLog（命令执行后写入）
```

代码位置：`backend/app/gateway/routers/terminal.py`、`backend/app/agent/terminal_graph.py`。另一条 `terminal_tools.execute_command` 路径也可调用 `session.execute_command`。两个底层调用点必须分别核验或汇入共同 PEP，不能只拦其中一个。当前 Terminal 审批不是持久平台 Approval。

## M1 接入决定与验证门

1. 只读候选为诊断 Agent 已注册的 `read_file`。沙箱 `write_file` 会改变文件，但同一 Agent 还可经 `bash`、`str_replace` 及其他 Tool 修改文件；只给 `write_file` 加 PEP 无法证明无绕过。因此首个副作用选择新增有界的 Agent→AIOps 工单 webhook Action Adapter，调用已有 `create_ticket` Provider，但由受控入口独占该 Agent Tool 的提交路径。规则触发的 `auto_ticket` 和独立 Terminal 演示都不能替代这个真实 Agent Action。当前 `ticket_provider.create_ticket` 未传幂等键；人工 `/incidents/{id}/ticket` 与规则 `auto_ticket` 仍各自直接调用 Provider。M1 内部 Adapter 现已先占用本地唯一提交标识，超时保留 unknown 且不自动重发；Provider 可传幂等键，但接收端是否去重仍未知。Adapter 默认关闭且尚未注册为 Agent Tool；可信执行入口通过前不开放真实调用。
2. 诊断 Gateway 的 Agent enabled 与跨租户校验已补测试；通用浏览器 LangGraph 入口现经 Gateway 代理核验会话、tenant、Agent 和线程绑定；LangGraph 严格上下文开关默认关闭，真实部署放量仍待工作包 11。Tool registry 已在 MCP 发现前按服务器筛选，空选择不再隐式加载所有 MCP；旧 DB 自定义 Agent 的空数组会失去此前意外获得的 MCP 权限，这是有意的安全收紧。默认 Agent/未指定组调用者保持原有行为。内置 `bash`/文件工具仍需独立 PEP，不能把 MCP 筛选当作完整工具治理。
3. 统一 PEP 必须位于实际 Tool/Action 提交函数之前，Decision 与关键 Audit 同事务持久化成功才能进入副作用函数。对 Terminal 的两个执行路径和 AIOps 选定路径分别做 bypass 测试。
4. `terminal.execute` fixture 保留为解耦的契约样例；最终 Golden Scenario 另增真实路径测试，覆盖 allow、deny、require_approval、过期、重复提交和 Audit 故障。
