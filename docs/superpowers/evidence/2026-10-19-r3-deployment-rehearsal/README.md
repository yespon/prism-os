# R3 部署演练：调度生命周期与幂等触发（2026-10-19）

分支 `codex/octop-integration`；R3 后端镜像 `sha256:771c6b3f…`（含三表迁移、调度服务、schedules API、治理工具）。N04 栈真实 HTTP + PostgreSQL；迁移 `p0j1k2l3m4n5o6` 真实执行。

## 演练结果（r3-rehearsal-result.json，complete: true）

1. **schedule-created**：POST /api/schedules 创建 interval 任务（真实认证 + 租户上下文）
2. **run-now-collision-single-execution**：同秒两次 run-now，第一次 `will_execute: true`、第二次 `false`——幂等键拦截重复触发
3. **single-occurrence**：occurrence 历史恰好一条
4. **cross-tenant-404**：跨租户 run-now 404
5. **disable-and-delete**：owner 启停删全链通过

## 部署过程修复

schedules 路由初版误用 `prefix="/schedules"`（与 knowledge 路由同款前缀问题），网关约定是 `/api/...`——本地测试因测试自挂载带 `/api` 前缀而通过，真实部署 404 暴露。已修并对齐。**这再次验证了真实部署演练不可省略。**

## 边界

- Worker 进程尚未加入 compose（本轮演练验证 API 与幂等事实层；Worker 容器编排与触发→执行全链在第三周演练）
- 触发执行接缝（execute 回调）在契约测试验证；真实 Gateway 运行入口接线在第三周

## 演练二：Worker boot 恢复（run_boot_recovery.py，complete: true）

1. 创建 30 秒 interval 任务（真实 API）
2. **重启 cron-worker 容器** → 从 DB 重新注册恰好 1 个 job（`cron worker booted with 1 job(s)`）
3. 等待一个周期 → 自动触发产生 1 个 `completed` occurrence
4. owner 清理删除

至此 R3 Spec 六场景中的 1/2/3/6（创建/触发/重启恢复/清理）有真实部署证据；4（纳管动作审批挂起）与 5（投递重试不重执行）在契约测试层验证，真实场景接线随后续批次补齐。

## cron-worker 容器编排

已加入 N04 compose：`uv run python -m app.scheduling.worker_entry`，单实例、`no-new-privileges`、依赖 postgres 健康检查。部署文档红线：多实例前必须先实现调度租约。
