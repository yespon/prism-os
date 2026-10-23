# N09-B 资源预检、安装事实与固定来源包证据

2026-10-12；实施基线 `06875f8`，分支 `codex/octop-integration`。本批接续 N09-A，保留完整 N01–N15、O01–O42/F01–F12 与原 PrismOS 设计及退出门。完整 N09、N04/M1、N07 远端 CI 未完成；N08 持久执行未启动。

## 实际用户路径及宿主接缝

创建/编辑专家可按需核对完整资源及安装事实。当前 tenant/current user/shared 行和 public 根按原宿主可见语义读取；公共同名 shared 行作为该租户禁用覆盖，与原 `get_available_skills` 一致。查询不调用会 ensure_user_config 的聚合入口，不改 Agent 草稿，不返回安装绝对路径、私有内容或执行权限。模板/语言/租户/关闭会丢弃旧结果并中止迟到预检/下载。

18 专家全部 352 个保留源成员仍核对，资源 297 个及额外辅助文件 27 个、四项 Office 独立实现缺口继续展示。27 个 Skill 可显式下载固定来源包；原始格式 24 处兼容，三处已知差异按有限映射派生。其余 SKILL 原字节保留；逐成员 source/host SHA、来源 revision、上游根版权文本 `LICENSE.octop` 与固定摘要随包交付。未知格式、保留资源篡改、版权文本缺失/篡改/别名均拒绝。

下载入口只读取固定公开上游专家库和已固定根版权文本；初次复合修改因可能泄露租户安装内容被自动审查拒绝。提供 [来源边界证明](source-boundary.json) 并增加固定上游前缀限制后，缩小的公开源码入口获重审通过。包构造器不读租户安装目录、运行配置或 Secret Resolver，不自动传输到外部接收端。无未解除的审批阻塞。

原 personal import 曾传递 installer 不支持的 is_custom/tenant_id 参数；现以原 target_relative_path=tenant/user 接入已有 personal 根，保持原 TenantSkill 注册/冲突处理。真实 native installer 和 SQLite 行验证 27 个包、重复冲突、跨租户/用户、修改/缺失/禁用/不可信路径，以及公共禁用只影响当前租户。DB 与文件系统的跨阶段中断恢复、并发同名和完整资源 ACL 仍待 N09-C，不将本批修复称为完整原子安装。

## 验证与构建恢复

完整结果由 [validation.json](validation.json) 记录。

| 实际验证 | 结果 |
| --- | --- |
| 最终完整后端 | 1,618 通过 / 18 跳过 / 30 warnings |
| 当前及独立完整前端 | 44 文件 / 140 通过 |
| 独立统一构建 | make 退出 0；255 后端 / 49 前端、类型、真实 Gateway、制品与生产构建 |
| 包与安装事实 | 27 个包实际 native 安装；31 包/许可 + 10 安装事实/API 用例 |
| 上游升级/回退 | b5→b6→b5 各 121 项；18 个宿主输入固定 |
| 源码/制品路径 | 902 原样源成员；两份 wheel/sdist SHA 相同；50 NFT / 16,995 引用均在自身 frontend |
| 本批未退出门 | 完整 N09、N04/M1、N07 远端 CI；未实施 N08 持久执行 |

真实 uvicorn、Better Auth 会话/租户成员、全部专家只读声明、无配置写入及鉴权 ZIP/版权附件分别在当前源和独立检出验证。31 个包/许可完整性用例与 10 个真实安装事实/API 用例通过；格式测试未执行资源脚本、模型、工具或 webhook。

构建先遇到镜像 Hatchling TLS 失败；整体换索引又触发 `--locked` 的更新拒绝，宿主锁未修改。最终只对独立 wheel 构建使用官方索引，锁定安装继续原索引。实际 wrapper 在 logs/build-index-wrapper.sh，失败及成功日志均保留。

内存 8 GiB、交换 4 GiB 的本机出现交换耗尽与高 memory PSI，独立 Vitest worker 启动/用例超时。停止仅属于本轮的构建后，串行重试。发现 Next 编译图与类型 worker 叠加仍有压力，正式 build/preview 改为 `next typegen`→严格 `tsc --noEmit`→生产编译；成功后的子进程才跳过重复类型 worker，直接 Next 默认仍检查。页面 worker 固定为 2；本轮 CPU affinity=0,1、Node heap cap=2048 MiB、Rayon=2。

[build-gate.json](build-gate.json) 与负向日志证明真实新路由 GET 返回不合法类型时，在编译之前退出 2。初次探针放在下划线私有目录，未被 Next 发现，不能计作类型拒绝；已改为真实路由并保留两次日志。既有断言和测试超时未放宽。

独立检出记录 19 个候选代码文件摘要，前后端依赖目录实际属于自身，模块来源及 NFT 路径见 [independence.json](independence.json)。两份 wheel/sdist SHA 相同；前端制品分别实际构建，不宣称 Next BUILD_ID 字节相同。最终独立统一构建在串行恢复后完整重跑；之前被资源压力中断的 make 结果单独保留，不抹去失败。

## 证据及剩余范围

[materialization.json](materialization.json) 保存全部包和成员摘要；[gateway.json](gateway.json)、[upgrade.json](upgrade.json)、[candidate-code.json](candidate-code.json)、[frontend-report.json](frontend-report.json)、[resource-pressure.json](resource-pressure.json) 与日志由 validation.json 记录 SHA。追加的 [能力账本](capability-delta.json) 承接 N06 完整静态清单，历史证据保持原样。b5→b6→b5 三轮覆盖新增包与原 personal import，固定 18 个宿主输入（包括原 installer/validator）。

下一批按 [N09-C 计划](../../plans/2026-10-12-octop-n09-resource-installation-plan.md) 先加固安装发布、同名冲突和中断恢复，再推进拥有/共享/复制/撤回、33 个非 Skill 组绑定、真实工具/schema/PEP/Sandbox/依赖与 18 专家实际行为。独立 Office 等价实现、两个有资源专家和子 Agent 委派仍保留；执行绑定依赖原 N08/M1 门。

本轮未重跑 N07 Docker/Compose，既有容器证据不能证明本轮代码；远端 CI、目标环境、模型/webhook、M2 生命周期均不计通过。两个依赖锁、原 Runtime Adapter、平台持久模型及唯一 Alembic head 保留。
