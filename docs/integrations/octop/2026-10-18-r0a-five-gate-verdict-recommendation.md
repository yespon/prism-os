# M1 五门重裁建议（R0-A 收口）

**日期：** 2026-10-18
**状态：** 已确认。用户于 2026-10-18 确认五门裁定，M1 正式退出。`deployment.json` 已更新 `m1_exited: true`；worktree 与主仓门禁记录均已追加 2026-10-18 重裁段。
**依据：** [五门缺口对账](./2026-10-18-r0a-gate-reconciliation.md)、[M1 门禁记录](../../strategy/2026-09-25-m1-exit-gate-evidence.md)、worktree evidence 2026-10-16/17 各批次

## 建议裁定

| 门 | 判定 | 证据链 |
| --- | --- | --- |
| Contract | **通过** | 平台契约 130 + 相邻安全 48；唯一 head `n8h9i0j1k2l3`；严格图上下文（required）真实部署激活 12 次且双服务配置一致断言；Gateway/LangGraph 严格身份传播经 approval-matrix 真实路径验证 |
| Golden Scenario | **通过** | 真实模型 `gpt-5.6-luna` 三态矩阵（V2 计数）：deny 不发送、allow 单次、批准等待/通过单次、重启恢复单次；接收端幂等回执全链核对 |
| Quality | **通过** | 完整后端 `2453 passed / 18 skipped / 0 failed`（13,631 冻结输入不变）；前端全量 + 类型 + 生产构建通过；失败基线未恶化；跳过项均为 live/LLM/S3 环境条件且真实环境演练独立完成 |
| Migration | **通过** | 三数据库（prismos/auth/checkpoints）真实 dump + SHA + 恢复库核对；head 一致；非空降级保护有测试；14 个配置快照备份；升级/回退循环（runtime-cycle）通过 |
| Security | **通过** | 四类安全反例全部有真实部署证据：跨租户 outsider 404；Secret 撤回/并发轮换单胜者且不发送；副作用每次触发仅一次（V2 计数）；审批到期 409/撤权阻断/Policy 与关键 Audit 写故障 fail-closed；GovernedReadMiddleware 覆盖共享二进制读取路径；Secret 不入公开证据（check_public_secrets 通过） |

## 已完成的对账修正

- `deployment.json` 已更新 `real_model_verified: true`（V2 矩阵证据成立）
- fault-expiry 时点的 remaining 两项已澄清：(a) 只读 PEP 其他入口复核——governed-readers 批次 + 10-17 真实 MCP/Office/SSH/child 入口复验已覆盖；(b) 完整配置/制品回退——runtime-cycle（镜像回退+重应用）+ 22 次 activation 的 off 恢复 + 14 个配置快照已覆盖

## 用户确认后需执行的动作

1. 更新 `deployment.json` `m1_exited: true`
2. 在 worktree 的 `docs/strategy/2026-09-25-m1-exit-gate-evidence.md` 追加 2026-10-18 五门重裁段（逐门判定 + 证据链接）
3. 在主仓同步该门禁记录更新
4. R1 编码解禁（按 R0–R1 实施方案的 R1 启动门：M1 退出 + R0 复盘完成）

## 明确不属于 M1 门的事项

- 远端 CI 首次运行（未推送）：随分支合并执行
- 八台及更多真实外部业务系统对接：自建接收端不等价企业 Jira，此边界保留在后续阶段
- R0-E3 复盘（迁入成本实测汇总）：与 M1 裁定独立，worktree 已有 b5→b6 演练成本记录，待汇总入 R0 复盘
