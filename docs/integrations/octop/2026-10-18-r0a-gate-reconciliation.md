# R0-A 五门缺口对账记录

**日期：** 2026-10-18
**状态：** 对账完成，待五门最终裁定。本文不宣布 M1 退出。
**执行分支：** `codex/octop-integration` worktree，HEAD `3c95c4c7`
**对照基准：** [M1 门禁记录](../../strategy/2026-09-25-m1-exit-gate-evidence.md) 目标部署验收顺序五步；[2026-10-16 fault-expiry validation.json](../../../superpowers/evidence/2026-10-16-octop-n04-fault-expiry/validation.json)

## 对账结论

此前记录的五门剩余缺口，经与 worktree evidence 目录逐项核对，**大部分已在 2026-10-16/17 的真实部署演练中取得证据**。最新遗留清单（fault-expiry validation.json `remaining`）只剩两项：

1. 完整目标配置/制品回退（部分覆盖，见下）
2. 原五门最终裁定

## 逐项对账

| 门禁记录目标部署验收步骤 | 要求 | 已有真实证据 | 判定 |
| --- | --- | --- | --- |
| 第 2 步：严格图上下文 | Gateway/LangGraph 同设 `required`；浏览器不能签发范围；后台可一次性消费 | `policy-activations.jsonl`：required 模式真实激活 12 次（deny×3 / require_approval×4 / allow×5），最后回 off；approval-matrix 含 outsider 跨租户 404 反例 | ✅ 已覆盖 |
| 第 3 步：真实模型三态矩阵 | deny → require_approval → allow 各验证真实 Tool 调用 | 2026-10-16 live V2 计数：allow 及批准/重启各只发送一次；deny/撤权/撤回/并发轮换/Policy 变更均不发送；接收端终态 23（本批）；后续批次至 26 | ✅ 已覆盖 |
| 第 4 步 a：撤权/审批矩阵 | approve/reject/revoke_agent/withdraw_secret/rotate_secret(并发单胜者)/restart | `run_approval_matrix.py` 六场景真实执行，各 `*-result.json` complete | ✅ 已覆盖 |
| 第 4 步 b：审批实际到期 | wall-clock 到期、迟到批准 409、恢复 expired、计数不增 | fault-expiry：真实等待 296.895 秒到期；23→23 | ✅ 已覆盖 |
| 第 4 步 c：Policy/Audit 写故障 | 关键写失败阻断副作用 | fault-expiry：四个 SQLSTATE 55000 触发点各真实命中一次（policy / audit_policy / audit_result / legacy_action）；前两类 23→23 无副作用；结果 Audit unknown；旧投递失败恢复只补时间线不重发 | ✅ 已覆盖 |
| 第 4 步 d：HTTP 超时 unknown | 503 / 30s 超时保持 unknown 不自动重发 | live 证据：provider-failure/timeout 系列，unknown 保持 | ✅ 已覆盖 |
| 第 4 步 e：旧审计投递故障恢复 | JSONL 失败可重放、不重发工单 | `jsonl-failure-replay.json`：恢复后只补一条旧时间线记录 | ✅ 已覆盖 |
| 第 5 步：开关回退 | 关闭后旧诊断视图可用、无新增副作用 | 各批 README："最终运行开关均 off"；回退后已有事实保留 | ✅ 已覆盖 |
| 只读文件 PEP 其他入口 | `bash` 等其他读取路径经同一 Policy | governed-readers：GovernedReadMiddleware 接管共享二进制读取；读取前/后 Audit 故障反例真实命中；reader-related/history-topology 回归 | ✅ 已覆盖（10-17 各任务进一步在真实 MCP/Office/SSH/child 入口复验） |
| 备份/恢复 | 目标库备份、恢复、回退规程 | fault-expiry final-backup：三库 dump+SHA+恢复库核对，head `n8h9i0j1k2l3`；多个 backup-* 目录 | ✅ 已覆盖 |
| 完整制品回退 | 上一已验收镜像回退+重应用 | child/mcp runtime-cycle：restart/previous accepted image/reapply 全通过，产物哈希与 ACL 保持 | ⚠️ 基本覆盖，validation.json `remaining` 仍列"complete target configuration/artifact rollback"——需确认该项与 runtime-cycle 的差距口径 |
| 五门最终裁定 | 更新门禁记录、五门重裁 | 所有五门的实质证据链已闭合（见上），但无一份汇总文档做出最终裁定；`deployment.json` 的 `m1_exited/real_model_verified` 仍为 false | ❌ 待执行 |

## 质量基线（截至 2026-10-17）

- 完整后端：`2453 passed, 18 skipped, 0 failed`（child-user-task 批次，13,631 冻结输入不变）
- 前端全量 Vitest + 类型 + 生产构建：通过
- 平台契约 130 + 相邻 48；唯一 head `n8h9i0j1k2l3`
- 远端 CI：未执行（未推送）；本地 CI 矩阵已由主仓 `ci-matrix.yml` 补齐，待合并推送后首次运行

## 待执行（五门最终裁定的剩余动作）

1. **裁定"完整目标配置/制品回退"差距口径**：runtime-cycle 已验证镜像回退+重应用；确认 validation.json 该 remaining 项指什么（目标环境完整配置回退 vs 镜像生命周期），必要时补一次全栈配置回退演练（compose-before-live.yaml 备份已存在）
2. **更新 `deployment.json`**：`real_model_verified: true`（V2 矩阵证据成立后）；`m1_exited` 待五门裁定
3. **更新 M1 门禁记录**：追加 2026-10-16/17 五门重裁段，逐门给出判定与证据链接
4. **裁定五门**：Contract ✅（130/48/head + 严格模式真实部署）｜Golden ✅（真实模型三态+故障矩阵）｜Quality ✅（2453/18 + 前端）｜Migration ✅（三库备份恢复 + 升降级）｜Security ✅（四类安全反例全部有真实部署证据：跨租户 404、Secret 撤回/轮换不发送、副作用单次、审批到期/撤权阻断）——若第 1 项差距确认已覆盖，五门可裁定通过
5. 远端 CI 首次运行不属于 M1 门（门禁记录未列入），随主仓合并推送执行
