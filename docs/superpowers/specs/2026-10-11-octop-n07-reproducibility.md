# N07：独立构建与部署验收增量设计

开始于 2026-10-11；2026-10-12 继续实施，基线 `a4c1531`。保留完整 N01–N15、O01–O42/F01–F12 与原 PrismOS 退出门；N04 真实环境待位置/配置引用，M1 未退出，不启动 N08。

先解除迁入工作树的 node_modules 外部链接，以锁文件独立安装并记录实际来源及安装结果；干净源视图应独立安装前后端，来源、制品、Gateway 和构建不借用原工作区。常规注册表缓存可用于校验安装，目录/模块解析不能指向原工作区。上游当前固定来源来自版本库；旧版本升级输入由固定原始摘要取得并过滤，不依赖先前 `/tmp` 路径。

明确 frontend 的 Turbopack/文件追踪根。模拟 Artifact/History 路径仅读取 public/demo/threads 范围，保留原 URL，拒绝遍历和跨目录符号链接；缺少可选 demo 返回未找到，不读取业务库或配置。Docker 的锁定安装和 COPY 上下文必须保留能力包全部来源数据，进入镜像后实际验完整性；不得以仅 YAML 合法或宿主测试代替容器运行。

隔离验证使用唯一命名的容器、网络、卷和临时配置，只清理本次创建资源。验证实际部署 Dockerfile/Compose 的前端、Gateway、LangGraph、迁移、PostgreSQL、认证与内容闭环，并核对制品成员、head、依赖版本、状态和回退。未取得的真实模型/webhook/M1 或远端 CI 证据保持待验，不把本地部署冒烟替代它们。

配置依据：[Next Turbopack root](https://nextjs.org/docs/app/api-reference/config/next-config-js/turbopack)、[Output tracing](https://nextjs.org/docs/app/api-reference/config/next-config-js/output)，并对照本地锁定 Next 16.2.11 类型与真实构建结果。复现与验收记录随实际执行补齐。


实际部署核对补充：生产与本地 Nginx 显式转发 `/api/agent-catalog`。首次部署 PostgreSQL 的身份表由 Gateway 创建，复用原 TEXT 时间/INTEGER 标记结构，不新增身份仓库或 Alembic 分支；初始化使用 PostgreSQL 事务 advisory lock，保留现有表与数据。既有部署身份字段的兼容升级仍需 N04 目标环境核对。

后端 Node/npm 来自官方 Node Debian 镜像的构建阶段，替代本次实际失败的 NodeSource TLS 获取；继续保留 npx/MCP 能力，依赖按原锁文件安装。Compose 启动使用 `uv run --frozen`，能力包 Markdown 在 `.dockerignore` 中作为运行数据保留。静态 demo 根与线程别名的符号链接不能把读取范围转到其他目录，缺省数据保持空列表/404。

验收通过后写入 [N07 证据](../evidence/2026-10-12-octop-n07-reproducibility/README.md)。远端 CI 和真实模型→受控 Tool→测试工单接收端分别保留待验，不用本地容器健康检查替代。
