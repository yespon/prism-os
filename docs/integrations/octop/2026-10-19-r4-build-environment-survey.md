# R4-D2 构建环境盘点报告

**日期：** 2026-10-19
**状态：** R4 立项前置事实。决定 R4 切入顺序。
**依据：** [排期修订 §3 R4 行](../strategy/2026-10-17-octop-integration-schedule-revision.md)；[R0 复盘 §重估](./2026-10-18-r0-review.md)（R4 是 24–36 周窗口最大不确定项）

## 桌面壳事实（上游 b6 固定提交）

| 项 | 事实 | 影响 |
| --- | --- | --- |
| 框架 | **Wails v3.0.0-beta.13**（`wailsapp/wails/v3`） | beta 框架；升级风险自担 |
| Go 版本 | `go 1.25.0`（go.mod） | 本机 Go 1.22.2 **不满足**；需安装 1.25+（官方最新 1.26.9 可下载） |
| 默认模式 | `ensurePortable` + `startOctop` 启动自带便携后端 | **第二宿主红线**——不可照搬默认启动逻辑 |
| 远程模式 | **`OCTOP_DESKTOP_URL` 环境变量**：设置后 `waitHealth` + `showDashboard(url)` 直连远端 | ✅ 上游已内置远程客户端模式——改造点集中且小 |
| 打包 | `package-release.sh` 六平台矩阵（darwin/linux/windows × amd64/arm64）；依赖 `portable/_common.sh` 便携后端打包 | Windows/macOS 制品需对应平台构建环境（WSL 只能产 Linux 制品） |

## 本机环境现状

| 能力 | 状态 |
| --- | --- |
| Go | 1.22.2（需升 1.25+） |
| Wails CLI | 未安装（`wails not found`；v3 beta 需 `go install ...@latest`） |
| Linux 制品 | ✅ WSL 可产（linux-amd64） |
| Windows 制品 | ⚠️ 理论可交叉编译（Go cross-compile），但 Wails v3 的 WebView2 绑定与打包需实测；无签名证书 |
| macOS 制品 | ❌ WSL 无法产（需 macOS + 签名） |

## R4 切入顺序结论（据盘点修正）

1. **先做远程壳改造（纯代码，环境无关）**：以 `OCTOP_DESKTOP_URL` 模式为基础，改 branding（PrismOS 标识/端口/默认 URL 指向 Gateway :2026），删除/禁用便携后端启动路径（第二宿主红线），接 v1 客户端契约（Bearer token 会话、断线重连读服务端事实）。**不依赖任何构建环境**。
2. **Linux 制品首验**（安装 Go 1.26 + Wails v3 beta CLI 后 `linux-amd64` 构建）——R4 的“单平台先验”锚点。
3. **Windows 交叉编译实测**：可行则纳入 R4 交付；WebView2 打包问题则降级 PWA 优先（排期修订 R4 降级条款）。
4. **macOS 制品**：记入差距账本（无 macOS 环境与签名证书），R6 前解决或明确豁免。

## PWA 现状

主应用前端已是 Next.js 响应式（PWA 基础在）；service manifest/offline 策略未做——R4 低成本切片。

## 风险记录

- Wails **v3 beta**：上游若升 beta.14+ 可能破坏 API；固定 beta.13 并在账本记录
- `OCTOP_DESKTOP_URL` 是上游接口，无稳定性承诺——改造后 Fork 语义自管
