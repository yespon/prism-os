# R0-A 执行状态：N04 WSL 栈恢复与五门重裁准备

**日期：** 2026-10-18
**状态：** 执行中。本文记录 R0-A 环境恢复事实，不构成任何门的通过声明。
**执行分支：** `codex/octop-integration` worktree（`/root/.codex/worktrees/octop-integration/prism-os`），HEAD `3c95c4c7`
**依据：** [R0–R1 实施方案](../../../superpowers/plans/2026-10-17-octop-r0-r1-implementation-plan.md) R0-A；[M1 门禁记录](../../strategy/2026-09-25-m1-exit-gate-evidence.md)

## 重要发现：并行 R0 进展校准

主仓 `codex/octop-research-plan`（`dd1574c3`）与 worktree `codex/octop-integration`（`3c95c4c7`，领先 65 提交）是两条并行工作线。worktree 已实质完成 R0 的多项内容，主仓文档需按以下事实校准：

| R0 任务 | worktree 已完成的事实 | 证据 |
| --- | --- | --- |
| R0-B 上游镜像/清单 | **已完成**：b6 归档 3,771 源文件 + 逐文件哈希 + 1,035 原样文件入独立能力包（`backend/packages/octop-capabilities`、`backend/app/integrations/octop`），vendor manifest 12,085 行 | [2026-10-09 迁入交付](../../strategy/2026-10-09-octop-import-delivery.md)；`vendor/octop/manifest.json` |
| R0-C 迁入试验/成本实测 | **大部分完成**：b5→b6 同宿主升级演练 9 契约通过；纯模块无变化；octop-harness SDK 接入及真实 MCP/Office/SSH/child 任务闭环已验收 | `evidence/2026-10-17-octop-*` 各目录 |
| R0-A A1 Provider 注入 | **已实施**（2026-10-09 记录："Provider 的最小引用注入、人工/规则兼容与旧配置默认 dry-run 迁移已实施"，57 项定向测试通过） | M1 门禁记录 2026-10-09 增量 |
| R0-E2 发布账本 | **已初始化**：42 项能力账本 JSON | `evidence/2026-10-09-octop-source-import/capability-ledger.json` |

主仓本轮新建文档（排期修订、R0–R1 实施方案、R0-B 基线文档、CI 四 job）与 worktree 工作互补不冲突：主仓 CI 矩阵（`.github/workflows/ci-matrix.yml`）与 worktree 的 `make octop-*` 本地门禁入口待合并时统一。

## 环境恢复事实

N04 WSL 栈（`scripts/octop_wsl_test_env.py`，loopback-only）已恢复：

- 服务：postgres 16（healthy）、gateway（healthy）、langgraph（healthy）、frontend、nginx（18026）、ticket-receiver（18443/8443）
- 数据库 head：`n8h9i0j1k2l3`（与镜像一致）
- 治理开关：`PRISMOS_TRUSTED_GRAPH_CONTEXT=off`、`PRISMOS_GOVERNED_TICKET_ACTION=off`、verdict=deny、admin tenant 空 —— 全部安全默认
- 接收端回执基线：26 条（与 2026-10-17 MCP 证据 `final-proof-current.json` 一致）
- 真实模型：`gpt-5.6-luna` 已配置启用（凭据不导出）
- 测试账号：live-fixture.json 三账号 + 双租户（requester/approver/outsider，t-276660… / t-983bf4…）

## 五门剩余缺口（据 2026-10-16 N04 live README"仍需推进的原退出条件"）

1. Policy/Audit 实际写故障注入（真实部署）
2. 审批实际到期（wall-clock）——已有 `wall-clock-expiry-*.log` 需核对是否已覆盖
3. 旧审计投递故障与恢复
4. 只读文件 PEP / 其他入口真实复核
5. 完整目标配置备份/制品回退演练
6. `deployment.json` 的 `m1_exited/real_model_verified` 仍为 false——真实模型 Tool 调用矩阵已在 2026-10-16 V2 计数下完成（allow/批准/重启各一次、反例不发送），待与门禁记录第 3 步逐项对账

## 下一步（按 R0-A 表格）

1. 与门禁记录"目标部署验收顺序"逐步对账：第 2 步（严格图上下文 required 验证）→ 第 3 步（deny → require_approval → allow 真实矩阵，已有 V2 证据待核对）→ 第 4 步（故障注入矩阵缺口补齐）→ 第 5 步（回退演练）
2. 补齐上述五门缺口后更新 `deployment.json` 与 M1 门禁记录，重裁五门
3. M1 退出判定达成后，R1 编码解禁
