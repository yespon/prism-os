# 客户端公共 API、审批与重连契约（R1-D1 冻结版）

**日期：** 2026-10-19
**状态：** 冻结为 R4 客户端开发的依赖契约。协议变化需独立版本化；本文描述的是 v1 表面。
**依据：** [R0–R1 实施方案](../../superpowers/plans/2026-10-17-octop-r0-r1-implementation-plan.md) R1-D1；[排期修订](../../strategy/2026-10-17-octop-integration-schedule-revision.md) §3（R4 首平台客户端以此为依赖）
**实现基线：** `codex/octop-integration`（`langgraph_proxy.py` / `approvals.py` / `auth.py` 及 N04 真实部署验证的现有表面）

## 1. 契约范围与原则

覆盖 R4 桌面客户端（Wails 壳改造版）与 PWA 消费的**既有** API 表面：

- **不新建第二套 API**：客户端与 Web 工作台消费同一 Gateway API，同一认证、同一租户边界；
- **不引入 Octop 登录/管理员/模型账户**（2026-10-08 建议 §3.3 红线）；
- 身份一律来自认证会话（Bearer token），客户端提交的 `tenant_id`/`user_id`/`agent_name` 字段**不是**授权证据——服务端从会话与线程绑定重查（M1 严格图上下文已验证）；
- 本契约只冻结 v1；v2 变更走独立版本与迁移评审，不允许静默破坏。

## 2. 认证与会话

| 端点 | 方法 | 契约 |
| --- | --- | --- |
| `/api/auth/login` | POST | 邮箱+密码 → `session.token`；客户端仅存 token，不存密码 |
| `/api/auth/session` | GET | 返回当前 `user.id`；用于启动时令牌有效性检查与静默续期 |
| `X-Tenant-Id` 头 | — | 请求级租户上下文；服务端校验 Membership，跨租户 404/403 |

**重连语义：** 令牌过期 → 401 → 客户端用保存的凭据重新登录或引导重登；不缓存过期会话状态。

## 3. 执行与流（LangGraph 代理面）

所有 LangGraph 操作经 `/api/langgraph/` 由 Gateway 代理，可用操作**白名单化**：

| 操作 | 方法与路径 | 契约 |
| --- | --- | --- |
| 创建线程 | `POST threads` | 服务端写 owner 元数据并绑定创建者 |
| 列出/搜索线程 | `GET threads` / `POST threads/search` | 只返回当前用户可见线程（绑定或可信归属） |
| 线程详情/状态/历史 | `GET threads/{id}`、`GET/POST threads/{id}/state`、`history` | 只读；identity 键不可被客户端覆写 |
| 发起运行（流式） | `POST threads/{id}/runs/stream` | 身份由 Gateway 重写；`configurable` 中 identity 键被剥离 |
| 取消运行 | `POST threads/{id}/runs/{run_id}/cancel` | 白名单操作 |
| 复制线程 | `POST threads/{id}/copy` | 新线程继承 owner 与 agent 绑定 |
| 删除线程 | `DELETE threads/{id}` | 仅 owner |

**未列入白名单的操作一律 403**（"Thread/LangGraph operation unavailable"）。SSE 流原样透传；断线后客户端以 `GET threads/{id}/state` 与 Run 事实恢复显示，**不**依赖缓存的流状态。

## 4. 审批与治理（R1 新增 run 投影）

| 端点 | 方法 | 契约 |
| --- | --- | --- |
| `/api/approvals/{id}` | GET | 审批详情；只有绑定的审批人（tenant_admin）可读 |
| `/api/approvals/{id}/approve` / `reject` | POST | 操作时服务端重查租户启用、成员角色、请求者有效身份；状态迁移 CAS |
| `/api/incidents/{id}/governed-ticket` | GET | 治理状态 + **`run` 投影**（v1 新增）：`{state, started_at, finished_at, snapshot{agent_name, agent_id, model_name, source}}` |
| `/api/incidents/{id}/governed-ticket/resume` | POST | 仅原请求者；服务端重查 Decision/Approval/当前 Policy |

**run 投影契约：** `run` 字段可为 `null`（run 事实尚未写入——投影不是门）。客户端必须容忍 `null` 并回退到既有 status 展示。`snapshot` 只含引用与名称，**永不**含凭据。

## 5. 文件与产物

沿用现有 `/api/threads/{id}/uploads`、artifacts、files 路由（ACL 由服务端按当前成员资格重查）。v1 不新增字段；大文件上传的分块协议留 v2。

## 6. 客户端行为红线

1. **禁止**第二登录入口或本地管理员账户；
2. **禁止**把 `owner_user_id`/`owner_tenant_id`/`agent_name` 写进请求 identity 键（服务端剥离，但客户端不得依赖该行为做授权）；
3. 断线恢复以服务端事实（thread state、run 投影、审批状态）为准，不以本地缓存推断；
4. `unknown` 提交状态显示"需人工核对"，客户端不提供自动重发按钮（M1 门禁语义）；
5. Wails 壳**不**启动自带便携后端（第二宿主红线）；只作为连接 PrismOS Gateway 的远程客户端。

## 7. 版本化与变更规则

- 本 v1 契约冻结后，破坏性变更需：新版本号 + 迁移评审 + 双版本并存期；
- 新增可选字段不构成破坏（客户端必须忽略未知字段）；
- 契约测试锚点：`tests/contracts/test_public_contract_api.py`（平台符号）、`tests/test_incident_diagnosis.py`（治理链与 run 投影）、`tests/test_graph_execution_context.py`（代理白名单）。
