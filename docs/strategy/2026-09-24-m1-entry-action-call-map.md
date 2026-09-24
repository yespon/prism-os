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
- `get_available_tools(groups=...)` 的函数注释明确表示 `groups` 被忽略；普通自定义 Agent 获得沙箱内置工具、社区工具和已缓存 MCP 工具。`diagnosis_helper.py` 中的工具分组提示是 Prompt，不是执行授权。
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

1. 首个 Agent Action 候选为诊断 Agent 可实际调用的沙箱 `write_file`/`bash`；它们会改变沙箱状态，需通过测试证明外部副作用定义和完整追溯是否满足 M1。若不能满足，先增加有界的 Agent→受控 AIOps Action Adapter，不能以规则触发的 `auto_ticket` 或独立 Terminal 演示替代。
2. 诊断 Gateway 的 Agent enabled 与跨租户校验已补测试；通用 LangGraph 入口仍待同等验证。Tool registry 分组的强制过滤仍未落地；测试必须证明未授权 Tool 在执行前被拒绝。已存的 `tool_groups=[]` 与未设置组的兼容语义需在实现前明确，并且不能让空配置意外获得高风险工具。
3. 统一 PEP 必须位于实际 Tool/Action 提交函数之前，Decision 与关键 Audit 同事务持久化成功才能进入副作用函数。对 Terminal 的两个执行路径和 AIOps 选定路径分别做 bypass 测试。
4. `terminal.execute` fixture 保留为解耦的契约样例；最终 Golden Scenario 另增真实路径测试，覆盖 allow、deny、require_approval、过期、重复提交和 Audit 故障。
