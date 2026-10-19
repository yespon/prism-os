# R4 桌面壳 linux-amd64 制品验证（2026-10-19）

## 制品

- `desktop-shell-fork/src/build/bin/prismos-desktop-linux-amd64`（17.7MB）
- Wails v3.0.0-beta.13 / Go 1.27.2 / CGO_ENABLED=1
- 运行时环境：Ubuntu 24.04，GTK 4.14.5 + WebKitGTK 2.52.6（需 `libwebkitgtk-6.0-dev`、`libgtk-4-dev`——webkit2gtk-4.1 不满足 Wails v3 beta）

## 启动验证（WSL headless）

1. **不设 PRISMOS_DESKTOP_URL**：壳启动但不进入便携后端路径（第二宿主红线成立；systray 在无桌面环境的注册失败为预期警告）
2. **设 PRISMOS_DESKTOP_URL=http://localhost:18026**：waitHealth 检查 `/api/health`（N04 返回 401，属 <500 通过范围——上游语义），壳进入远程连接流程，无 health 超时错误输出

## 构建链记录

- Go 1.27.2 经 golang.google.cn 镜像下载（proxy.golang.org 超时；gzip 完整性验证）
- GOPROXY=goproxy.cn 拉取 Wails v3 模块
- pkg-config 依赖：gtk4 + webkitgtk-6.0（补装 libwebkitgtk-6.0-dev）
- wails3 CLI 未装成（同 gtk4 pkg-config 依赖），**直接 go build 即可产制品**——CLI 非必需

## 待真实桌面环境验证

WSL headless 无法验证窗口渲染与拖拽（tray/GPU 警告为环境限制）。窗口内登录/会话/审批交互的端到端验证待 Windows/macOS 或带显示的 Linux 环境。
