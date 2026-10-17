# AgentOS 战略资料

本目录保存 PrismOS / AgentOS 的战略基线、白皮书和路线图资料。文档按“来源与用途”区分，避免把讨论草稿误当作当前实施规范。

## 文档索引

| 文档 | 状态 | 用途 |
| --- | --- | --- |
| [agentos-whitepaper.md](./agentos-whitepaper.md) | 正式重构版 | AgentOS 的定位、能力边界、架构原则、治理模型和长期演进方向；当前战略基线。 |
| [agentos-prismos-gap-roadmap-review.md](./agentos-prismos-gap-roadmap-review.md) | 校验报告 | 对白皮书与 PrismOS 当前实现进行双向审查，记录可行性、逻辑风险、差距矩阵和推荐路线。 |
| [governed-agent-platform-roadmap.md](./governed-agent-platform-roadmap.md) | 推荐路线草案 | 以能力基线和产品楔入为核心的版本化路线草案，用于拆分里程碑。 |
| [2026-09-24-octop-research-adoption-plan.md](./2026-09-24-octop-research-adoption-plan.md) | 外部项目调研与实施建议 | 基于 Octop 固定提交的代码调研，将可借鉴能力映射到 PrismOS 已批准路线、退出门和近期迭代。 |
| [2026-10-08-octop-full-capability-roadmap-review.md](./2026-10-08-octop-full-capability-roadmap-review.md) | 全量覆盖与规划一致性复核 | 固定 Octop 最新源码和发布，盘点 42 组当前能力、12 项官方路线与 8 个配套工作包；保留 PrismOS 原平台阶段，明确新增产品范围与独立验收。 |
| [2026-10-08-octop-integration-priority-and-delivery-plan.md](./2026-10-08-octop-integration-priority-and-delivery-plan.md) | 优先级与排期修订建议 | 在允许批量复用源码的前提下，提出纵向交付、必要平台切片提前与 R0–R6 节奏；保留原设计和最终退出门，明确候选排期与容量假设。 |
| [agentos-whitepaper-original.md](./agentos-whitepaper-original.md) | 原始草稿归档副本 | 保留原始生成稿的正文内容；仅做 Markdown 行尾空白规范化，供追溯决策来源；不作为实施规范。 |

## 使用约定

1. 以正式重构版白皮书确定产品定位和非目标。
2. 以双向校验报告判断当前实现是否支持某项主张，并识别验证债务。
3. 以路线草案拆分工程任务；如果路线与校验报告冲突，以校验报告中已验证的能力边界为准。
4. 原始草稿只用于追溯，不直接用于开发、发布或对外承诺。
5. Octop 最新状态与完整覆盖以 2026-10-08 全量复核补充历史采纳计划；PrismOS 阶段、依赖和退出门以已批准 Capability Roadmap 为准。新增目标范围不代表原里程碑已完成或新增日历已获承诺。
6. 批量复用源码后的交付顺序参见同日优先级修订建议；它明确提出调整原串行排期、提前有限依赖切片，尚不覆盖 Approved 路线。能力清单继续复用全量复核，实施前将相关契约与排期修订落入增量 Spec。

## 资料边界

本目录不保存本地 `.env`、数据库、凭证、运行时目录、构建产物或临时工作流状态。此类数据应留在本机并通过 Git 忽略规则排除。
