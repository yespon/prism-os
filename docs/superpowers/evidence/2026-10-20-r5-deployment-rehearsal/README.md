# R5 部署演练：版本发布/评测门/回滚（2026-10-20）

分支 `codex/octop-integration`；R5 镜像 `sha256:cdee96da…`（lifecycle/versioning/evaluation 三表 + 流水线 API）。N04 栈真实 HTTP + PostgreSQL；三条 R5 迁移（r2l3m4n5o6p7 / s3m4n5o6p7q8 / t4n5o6p7q8r9）真实执行。

## 结果（r5-rehearsal-result.json，complete: true）

1. **gate-refuses-no-evaluation**：全新 agent 版本直接部署 → 409
2. **gate-refuses-low-score**：0.3 分 → 409 gate failed
3. **gate-probe-deployed-after-pass**：0.95 分 → 202 部署
4. **v1 发布并部署**（幂等重跑时映射既有版本）
5. **v2 发布**（prompt 变更产生新哈希）→ 部署（previous 指向 v1）
6. **rolled-back-to-v1**：回滚端点恢复 v1 部署
7. **history-intact**：两版本仍在历史中——历史 Run 可解析当时的配置快照

## 过程修复（真实演练再次拦截）

- **publish 路由 async 缺陷**：`session.get` 同步调用 async session——契约测试 mock 了 loader 没抓住，真实栈 500 暴露
- **agents 路由按 name 不按 id**：演练初版用 id 调 PUT/GET 404

## 边界

- 演练证明 API 层发布/门/回滚闭环；Run 执行时对版本快照的实际引用（运行中 agent 采用 deployment 指针）在 R6 打通
