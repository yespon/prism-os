# AgentOS 战略资料

本目录保存 PrismOS / AgentOS 的战略基线、白皮书和路线图资料。文档按“来源与用途”区分，避免把讨论草稿误当作当前实施规范。

## 文档索引

| 文档 | 状态 | 用途 |
| --- | --- | --- |
| [agentos-whitepaper.md](./agentos-whitepaper.md) | 正式重构版 | AgentOS 的定位、能力边界、架构原则、治理模型和长期演进方向；当前战略基线。 |
| [agentos-prismos-gap-roadmap-review.md](./agentos-prismos-gap-roadmap-review.md) | 校验报告 | 对白皮书与 PrismOS 当前实现进行双向审查，记录可行性、逻辑风险、差距矩阵和推荐路线。 |
| [governed-agent-platform-roadmap.md](./governed-agent-platform-roadmap.md) | 推荐路线草案 | 以能力基线和产品楔入为核心的版本化路线草案，用于拆分里程碑。 |
| [agentos-whitepaper-original.md](./agentos-whitepaper-original.md) | 原始草稿归档副本 | 保留原始生成稿的正文内容；仅做 Markdown 行尾空白规范化，供追溯决策来源；不作为实施规范。 |

## 使用约定

1. 以正式重构版白皮书确定产品定位和非目标。
2. 以双向校验报告判断当前实现是否支持某项主张，并识别验证债务。
3. 以路线草案拆分工程任务；如果路线与校验报告冲突，以校验报告中已验证的能力边界为准。
4. 原始草稿只用于追溯，不直接用于开发、发布或对外承诺。

## 资料边界

本目录不保存本地 `.env`、数据库、凭证、运行时目录、构建产物或临时工作流状态。此类数据应留在本机并通过 Git 忽略规则排除。
