# 独立构建能力工作台承接方案（R1-C1，R0-D 收口）

**日期：** 2026-10-19
**状态：** 方案冻结。Octop Dashboard（React 18/Vite/AntD）页面迁入的承接架构。
**依据：** [2026-10-08 建议 §3.3](../../../strategy/2026-10-08-octop-integration-priority-and-delivery-plan.md)、[客户端 API 契约 v1](./2026-10-19-r1-client-api-contract.md)
**运行事实：** native profile（18036）+ 主应用（18026）双入口已在 N04 真实运行并验证会话/租户边界

## 1. 承接架构（三层）

```text
Nginx :2026
  ├── /                 → PrismOS Next.js 工作台（现有，React 19）
  ├── /api/             → PrismOS Gateway（认证、租户、治理）
  └── /workbench/       → Octop 能力工作台（独立构建，React 18/Vite/AntD）
        └── 经 API facade 调 /api/（同一会话、同一租户头）
```

- **短期（R2–R4）**：保留两套构建。能力工作台作为同域名路由挂载，不合并 React 依赖
- **长期（R5+）**：逐步统一视觉与关键页面，最终单一 Next.js 构建

## 2. 接缝清单（每项已验证或有验证方案）

| 接缝 | 方案 | 验证状态 |
| --- | --- | --- |
| 会话 | 能力工作台读取主应用同域 Cookie/Bearer；不提供自己的登录页 | native proxy 已实现同域转发，真实登录验证通过 |
| 租户切换 | 复用 `X-Tenant-Id` 头 + Membership 校验；工作台内切换走 `/api/auth/session` | 主应用模式，已验证 |
| CSP/资源 base | Vite 构建 `base: '/workbench/'`；CSP 允许同域静态资源 | 部署时按 Nginx 配置验证 |
| 路由 | Nginx location 精确匹配 `/workbench/`；不与 `/api/`、`/api/langgraph/` 冲突 | compose Nginx 已有同模式分流 |
| WebSocket/SSE | 透传；治理流式走 `/api/langgraph/` 白名单代理 | M1 严格模式已验证 SSE 透传 |
| API facade | 能力工作台只调用 v1 客户端契约端点；Octop 原生 API 路由不暴露 | 契约文档已冻结 |
| 审批交互 | 工作台审批卡片调 `/api/approvals/*`；run 状态读 `run` 投影 | R1-C3 已实现 |

## 3. 红线（不变）

1. 不出现第二登录/管理员/模型账户（Octop 原生 auth 路由不迁入）
2. 能力工作台不得直连 LangGraph 或数据库——一切经 Gateway
3. 迁入页面不携带 Octop 的 owner/shared 可见性逻辑；数据展示走租户过滤后的 API
4. 每 batch 迁入页面过 `make octop-check` + 前端全量回归 + 真实登录冒烟

## 4. 迁入节奏

R2 起每轮迁入对应能力的页面组（R2 知识库页面、R3 定时任务/团队页面、R4 多模态/设备页面）；每批以完整用户路径为迁入单位，不以页面数计进度。
