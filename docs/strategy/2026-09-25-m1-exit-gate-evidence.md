# M1 治理执行退出门复核

**日期：** 2026-09-25
**分支：** `codex/octop-research-plan`
**依据：** [批准路线](../superpowers/specs/2026-08-08-prismos-capability-roadmap-design.md) §8.1、§13；[M1 Spec](../superpowers/specs/2026-09-24-prismos-m1-governed-action-design.md)；[逐任务计划](../superpowers/plans/2026-09-24-prismos-m1-policy-approval-implementation.md)。
**结论：** 本地 Contract、Quality 与隔离 Migration 检查通过；Golden 的真实部署验证和专项 Security Gate 尚未通过。**M1 不宣布完成，M2 不启动；`ticket.create` 试点开关保持关闭。**

## 门禁结果

| 门 | 已取得的证据 | 尚需完成 | 判定 |
| --- | --- | --- | --- |
| Contract | `scripts/test-platform-contracts.sh`：129 个契约、48 个相邻安全测试通过；Alembic 唯一 head `m7g8h9i0j1k2`；平台包不导入 AIOps/Runtime 私有模块。 | 在目标部署验证 Gateway/LangGraph 同时启用严格图上下文及认证会话传播。 | 本地通过，部署待验 |
| Golden Scenario | 已认证的诊断 HTTP 请求经一次性 Incident 范围、模拟 LangGraph 流、Agent Tool 到模拟 Provider；allow、deny、等待/通过/拒绝/过期、撤权、Audit 故障、超时 unknown 和重复请求均有自动化断言。 | 用真实模型、目标 webhook、审批人和请求者运行同一路径；验证目标数据库并发及服务重启后恢复。 | 自动化通过，真实场景待验 |
| Quality | 全后端 `1382 passed, 18 skipped, 0 failed`；前端 `91 passed`、typecheck 与 Node 24 生产 build 通过；lint `0 errors, 168 warnings`。本轮首跑同一后端套件 `1373 passed, 18 skipped, 8 failed`；已修复 Harness 反向导入、Alembic 禁用应用 logger 的顺序污染，并让干净检出校验受版本控制的配置模板。 | 168 个前端 lint warning 保留为质量债；持续追踪。 | 本地通过 |
| Migration | SQLite 升降级回归通过；隔离 PostgreSQL 16 从 `l6f7g8h9i0j1` 升到 `m7g8h9i0j1k2`、降回、再升级通过，旧 `incident_actions` 表仍可读取；生产与开发 Compose 清单均通过语法检查（开发清单使用临时空 `.env`）。 | 在目标数据库备份后迁移、读历史审计、验证双写及回退；检验 Gateway JSONL 文件锁与并发。 | 隔离环境通过，目标部署待验 |
| Security | 浏览器不能伪造 Incident Action 范围；租户隔离、身份重查、关键 Audit 故障阻断副作用、提交 unknown 不自动重发、平台事实/投递不包含测试凭据均有测试。 | 现有 `AlertSource.config_json.ticket.headers` 可保存内联 webhook 凭据，缺少此 Action 的 `SecretRef` 注入边界；目标部署的副作用、Secret 与跨租户演练未执行。只读 `read_file` 的实际 PEP 仍需按 M1 Spec 复核。 | **未通过** |

`run_id` 在 M1 只用作诊断线程派生的关联 ID，不代表 M2 的持久 Run 生命周期。人工建单及规则 `auto_ticket` 仍是独立旧路径，不能算作受控 Agent Action 的证据。`terminal.execute` 契约 fixture 也不计作 AIOps 真实调用。

## 质量明细与可重复命令

- 后端完整套件：`cd backend && uv run pytest tests -q -rs --tb=short`，`1382 passed, 18 skipped, 30 warnings`。18 项跳过中：1 项缺少 live `config.yaml`，11 项缺少 LLM API 凭据，6 项缺少 S3 测试依赖。跳过项均不是平台核心契约。
- 平台契约：`UV_BIN=/root/.local/bin/uv ./scripts/test-platform-contracts.sh`，`129 passed`、相邻 `48 passed`、Ruff 通过、唯一迁移 head。
- 前端：在 Node `v24.11.1` 下运行 `npm run lint`、`npm run typecheck`、`npm run test:unit`、`SKIP_ENV_VALIDATION=1 npm run build`；分别为 0 error/168 warning、通过、39 文件/91 测试通过、构建通过。系统默认 Node 18 不能运行当前 Next.js build；使用已有 Node 24 后通过。
- 历史发布说明中的 `973 passed, 18 skipped, 184 failed` 属于不同提交和测试集合，不能直接算趋势。本轮同一集合的首次 8 失败已降为 0，未用 skip 或非阻塞标记掩盖失败。

## 迁移、回退与安全发现

隔离 PostgreSQL 16 的迁移观测依次为 `l6f7g8h9i0j1`（无 `action_incident_id`）、`m7g8h9i0j1k2`（有该列）、降回旧版（无该列）、再升级（有该列）；每一步旧 `incident_actions` 表仍存在。临时容器已删除。此结果不能替代目标数据库备份和升级验证。

本地开关回退测试证明 `PRISMOS_GOVERNED_TICKET_ACTION=off` 后 Agent 不装配受控 Tool，界面回到原有诊断路径，已记录事实保留。目标部署尚无 PrismOS Gateway/LangGraph 容器、`config.yaml`、`.env`、测试模型和目标 webhook；真实开关切换、服务重启、文件投递重放和部署回滚均未执行。

受控建单的测试源配置包含 `Authorization` 示例，现有实现只保证它不进入平台 Decision、Audit、提交与投递记录；`AlertSource.config_json` 本身仍允许保存内联 Header。正式放量前须提供租户范围的凭据引用和最小范围注入，或明确限制该 Action 只使用无凭据的测试 webhook，并补对应拒绝内联凭据的测试。后一种限制只能用于隔离演示，不能视为完整 Secret Gate 通过。

## 目标部署验收顺序

1. 准备隔离租户、请求者与另一名租户管理员、启用的诊断 Agent、可用模型、可核对幂等键的测试工单接收端；先解决上述凭据边界，并备份目标数据库及旧 JSONL。
2. 升级到唯一 head；在 Gateway 与 LangGraph 同时设置 `PRISMOS_TRUSTED_GRAPH_CONTEXT=required`，验证浏览器不能签发 Incident Action 范围、后台诊断可以一次性消费范围。保持 `PRISMOS_GOVERNED_TICKET_ACTION=off` 直到预检完成。
3. 仅对该租户启用 `ticket.create`，先以 `deny`、再以 `require_approval`、最后以受控 `allow` 验证真实模型 Tool 调用。每次规则变化提高 Policy version；核对 Decision、Approval、Audit、Submission、旧时间线和接收端调用次数。
4. 注入撤权、审批超时、Policy/Audit 写失败、webhook 超时、重复请求、进程重启与旧审计投递失败；`unknown` 必须人工核对，不能自动再发。记录通过、失败、跳过、请求 ID、run ID、结果和耗时。
5. 在 Gateway 与 LangGraph 同时关闭 Action 开关，确认旧诊断视图可用且没有新增副作用；再按备份和迁移回退规程演练。完成这些证据后重新裁定五道门，才可宣布 M1 退出并启动 M2。
