# R0-B：Octop 上游基线镜像与清单

**日期：** 2026-10-18
**状态：** R0-B 交付物；镜像仅作追溯用，不运行第二宿主（见排期修订 §5.3）
**上游基线：** Octop `v1.0.2b6`，固定提交 `eb28011249c02cafd389b2d424294c6c1b9cf422`（2026-10-05 07:47:33 +0800，"chore: release 1.0.2b6 (#1612)"）
**镜像位置：** `/root/workspace/octop-b6-mirror`（可恢复：`git checkout eb280112`）

## 1. 主仓锁定

| 项 | 值 |
| --- | --- |
| 主仓 | https://github.com/TencentCloud/Octop.git |
| commit | `eb28011249c02cafd389b2d424294c6c1b9cf422` |
| tag | `v1.0.2b6` |
| 许可证 | MIT（Copyright (c) 2026 Octop） |
| 路由模块数 | 77（与全量复核 §9.3 盘点一致） |
| 顶级目录 | `src`（服务端）、`dashboard`（React 18/Vite/AntD）、`desktop`（Wails 壳）、`plugins`、`fnos`（NAS）、`docker`、`docs`、`tests` |

## 2. 外部能力包锁定（uv.lock 解出）

| 包 | 锁定版本 | 用途 |
| --- | --- | --- |
| `octop-harness[all]` | 1.0.1 | Agent 执行 harness（主仓直接依赖） |
| `octop-memory` | 1.0.0 | 记忆 |
| `octop-gateway` | 1.0.0 | 通道 |
| `octop-browser` | 1.0.0 | 浏览器 |

注意：主仓 `pyproject.toml` 声明的是 `>=` 范围，锁定值以 `uv.lock` 为准。只复制主仓无法取得完整行为（2026-10-08 建议 §3.1 已警示），迁入前须确认各包源码可得性。

## 3. 关键依赖版本对照与冲突点初判

| 依赖 | Octop b6 锁定 | PrismOS 现状 | 预授权走向（排期修订 §5.2） |
| --- | --- | --- | --- |
| `langgraph` | 1.2.11 | 未直接依赖（经 DeerFlow harness） | 待查 DeerFlow 传递依赖后判定 |
| `langgraph-sdk` | **0.4.2** | `>=0.1.51` | 大概率可通融（宽范围），需实测 |
| `langgraph-checkpoint-postgres` | **3.1.0** | `>=2.1` | 同上 |
| `langchain` | 1.3.18（含 anthropic/openai/community 等全家桶） | 仅 `langchain-ollama>=1.1.0` | 不可通融项候选：迁入模块若硬依赖 langchain 1.x 全家桶 → 隔离能力 Worker |
| `fastapi` | 0.138.2 | `>=0.141.1` | **疑似反向不兼容**：Octop 锁定版本低于 PrismOS 下限，需实测 API 兼容面 |
| `pydantic` | 待查 | 待查 | 待实测 |

**初判结论：** 接缝冲突大概率集中在 `langchain` 1.x 全家桶与 `fastapi` 版本带；按预授权规则，这两类先尝试就地解决，失败则隔离能力 Worker，不为迁入升级/降级 PrismOS 核心依赖。

## 4. 迁入模块来源映射（infra 目录 → 全量复核 O 编号）

| infra 目录 | O 编号 | 候选迁入策略（2026-10-08 §3.1） |
| --- | --- | --- |
| `agents/`（含 teams、plugins、security、subagents） | O04–O09/O36/O38 | B 类（身份/执行接缝重） |
| `knowledge/` | O20 | B 类（owner/shared → tenant/ACL） |
| `connectors/` | O24/O25 | B 类（SecretRef 接缝） |
| `cron/` | O13 | B 类（Run/Occurrence 接缝） |
| `proactive/` | O14 | B 类（依赖 cron 接缝） |
| `channels`（在 octop-gateway 包内） | O12 | B 类（通道绑定接缝） |
| `browser/`、`desktop/`、`mobile/` | O30–O33 | B/C 类（依赖 octop-browser 包） |
| `bridge/` | O41 | C 类（协议复用为主） |
| `voice/` | O18 | B 类（输入输出 Adapter） |
| `auth/`（OIDC/OAuth/LDAP） | O03 | C 类（身份接缝由 PrismOS 承担，复用协议逻辑） |
| `backup/`、`setup/`、`users/` | O01/O40 | C 类（系统责任不照搬） |

专家/子 Agent/MBTI 内容、内置 Skill 资料、i18n 文案属 A 类内容迁入（R1-B1 执行），迁入时保留来源 commit 与许可证清单。

## 5. 许可证核对

- 主仓 MIT 已核对（LICENSE 文件）。
- 四个外部能力包与内置素材（专家头像、MBTI 题库、模型模板等）的许可证**待逐包核对**——不得只记录主仓许可证（2026-10-08 建议 §7 第 2 条）。此项为 R0-B 遗留项，阻塞 R2 起 B 类迁入，不阻塞 R0-C 试验与 R1 A 类内容迁入。
