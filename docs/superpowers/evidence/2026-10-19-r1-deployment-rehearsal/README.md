# R1 部署演练：Run 事实跨重启持久（2026-10-19）

分支 `codex/octop-integration`；R1 后端镜像 `sha256:cac5df95551083f02729fb3793d2628d2e8a20da2a90a275b4bfe3deecaf6bfd`（含 R1-A/R1-C3 提交）。在已部署的 N04 WSL 栈演练，沿用真实 HTTP 登录、配置的 `gpt-5.6-luna`、PostgreSQL 与独立 HTTPS 接收端。

## 部署与迁移

- compose 五处镜像引用更新为 R1 镜像（原 compose 备份为 `compose-before-r1-image.yaml`）
- `db-init` 真实执行新迁移：`n8h9i0j1k2l3 -> o9i0j1k2l3m4`（Add minimal platform run facts with frozen snapshots），`platform_run_facts` 表在目标 PostgreSQL 建立
- 演练前三库备份（prismos / prismos_auth_db / prismos_checkpoints）+ SHA256 记录于私有 runtime `backup-r1-rehearsal/`

## 演练结果（r1-rehearsal-result.json，complete: true）

1. **pre-health**：全服务 healthy（演练中发现并修复 nginx 旧容器路由失效——容器重建后 nginx 未重启，重启后恢复；该失败保留在首次运行记录中）
2. **policy-allow**：单租户 canary `ticket.create` allow + 严格图上下文 required，版本 `r1-allow-1792381562`
3. **run-fact-recorded**：真实模型诊断 → 治理工具执行 → status 端点返回 `run` 投影：`state=created`，快照键 `agent_id/agent_name/model_name/source` 齐全。首次运行的失败（未绑定 SecretRef → 目标解析失败）保留为过程记录；修复脚本后通过
4. **restart-preserved**：重启 gateway+langgraph → 重读 status，run 投影**逐字段一致**（`snapshot_identical: true`）——冻结快照跨重启持久
5. **rollback-off**：canary 关闭后 status 返回 `enabled: false`，旧视图可用

## 数据侧核对

- 今日 Policy 决策 1 条（allow）、Action 提交 1 条（submitted）、run facts 2 条（含首次失败演练的 1 条 created 事实，保留不删）
- 接收端回执 26 → 27：**恰好一次**真实副作用提交（幂等计数口径 V2）
- AlertSource 凭据经 `/ticket-secret` SecretRef 端点绑定（内联凭据被 M1 边界拒绝——首次演练的实际反例验证）

## 边界

- 演练证明的是 R1 范围：run 事实投影 + 快照冻结 + 跨重启持久；完整 Task/Run 状态机、审批等待场景的 run 投影（require_approval 路径）留 R2 演练
- 秘钥、配置、模型原始回复仅在私有 runtime；公开 receipt 只含状态与 ID
