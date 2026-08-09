# PrismOS 快速开始

[English](./QUICKSTART.md) | 中文

本指南使用 Docker 启动一个本地 PrismOS alpha 实例，从空仓库到首次登录工作台。
它不会自动替你建立生产环境的安全边界。

## 前置条件

- 本地运行中的 Docker Desktop 或 Docker Engine，以及 Compose v2
- 一个管理后台支持的模型厂商 API key
- 建议至少提供 8 GB 可用内存，以运行核心服务

默认 `LocalSandboxProvider` 会在宿主机上执行。使用不可信代码前，请先阅读
[安全策略](./SECURITY.md) 中的 sandbox 警告。

## 1. 克隆并生成配置

```bash
git clone https://github.com/yespon/prism-os.git
cd prism-os
make config
```

`make config` 只在文件不存在时创建本地 `config.yaml` 和 `frontend/.env`。
加入凭据后不要提交这两个文件。

新部署使用 `PRISMOS_*` 变量和 `backend/.prismos`。已有部署在修改数据目录前，
请先阅读[品牌迁移指南](./docs/migrations/prismos-brand-migration.md)。

## 2. 启动 PrismOS

```bash
make up
```

该命令会初始化数据库、构建本地镜像，并启动反向代理、前端、gateway 和
LangGraph 服务。通过公开入口检查 gateway：

```bash
curl http://localhost:2026/health
```

然后打开 <http://localhost:2026>。

## 3. 完成首次管理员初始化

首次访问会进入初始化向导，用于创建初始管理员。未登录时也可以查看 bootstrap
状态：

```bash
curl http://localhost:2026/api/auth/bootstrap-status
```

完成初始化后登录，并立即更换临时凭据。不要把凭据或厂商 API key 放入 Issue、
终端日志或提交的配置文件。

## 4. 添加模型

进入管理后台 **Settings → Models**，选择厂商模板，填写 API key 和模型名并保存。
模型记录存储在数据库中，再分配给租户；生产环境不要把模型配置写入 `config.yaml`。

## 5. 使用工作台

- 开始一次对话并查看生成的 artifacts。
- 上传文件，检查线程文件流程。
- 创建或导入 Skill，并使用其 sandbox 测试流程。
- 只有在审查命令、网络访问、凭据和租户作用域后，才配置 MCP Server。
- 在 **Settings** 中管理用户、租户、模型、Skill、MCP Server 和可选垂直插件。

AI 运维可以作为验证场景，但不是平台运行的前提，也不是 PrismOS 的架构边界。

## 容器镜像

首个 alpha release 计划为支持的架构发布 GHCR 镜像：

```bash
docker pull ghcr.io/yespon/prism-os:v0.1.0-alpha.1
```

请使用 release notes 中的精确版本号。PrismOS alpha 不发布、也不暗示存在 `latest`
标签。当前 Compose 文件默认构建本地服务镜像，具体镜像使用方式以版本说明为准。

## 开发命令

```bash
make check                 # 检查本地依赖
make install               # 安装 uv 与 pnpm 依赖
make dev                   # 启动带热重载的本地服务
make docker-init           # 准备 Docker 开发镜像
make docker-start          # 启动 Docker 开发模式
make docker-logs           # 查看 Docker 开发日志
make stop                  # 停止本地开发进程
make down                  # 停止生产 Compose 服务
```

本地开发的公开入口仍为 <http://localhost:2026>。gateway 提供 `/api/*`，
LangGraph 流量通过 `/api/langgraph/*` 暴露。

## 故障排查

### health 无响应

```bash
docker compose ps
docker compose logs --tail=200 gateway langgraph nginx
```

如果配置来自较早的 checkout，请检查 `PRISMOS_CONFIG_PATH` 和运行时数据目录，
并按照迁移指南操作，不要直接删除已有运行数据。

### 模型请求失败

检查厂商 key、base URL、模型名、租户分配和厂商服务状态。health 只证明服务可用，
不会验证外部模型厂商。

### Sandbox 执行失败

本地模式会在宿主机执行。Docker 模式请检查 Docker socket 权限并拉取配置的 sandbox
镜像。Kubernetes provisioner 模式请阅读
[provisioner 指南](./docker/provisioner/README.md)，检查 kubeconfig 挂载和 namespace 权限。

## 停止与重置

```bash
make down
```

`make clean` 只清理临时开发状态和日志，并保留 PrismOS 运行时数据及数据库卷。
`make clean-db` 具有破坏性，执行前请先备份数据。
