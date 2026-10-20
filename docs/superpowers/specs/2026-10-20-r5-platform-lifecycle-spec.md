# R5 Spec：平台完整生命周期收口

**日期：** 2026-10-20
**状态：** 已批准（R4 环境边界项冻结后启动）
**范围：** M2 Run 状态机 / M4 AgentVersion / M3 评测门 / M7 扩展包的最小可验收切片
**非目标：** 完整 Workflow DAG（依赖 M4 验证后的 M5 立项）；公共市场；Runtime 替换（C1 硬证据未现）

## 1. 交付块

### A. Run 状态机收口（M2 最小版）
R1 的 RunFact（created/completed/failed 三态）扩展为完整生命周期：
- Task/Run/Attempt 状态机（pending/running/succeeded/failed/cancelled/timeout）
- 取消传播（父 Run 取消 → 子 Run 取消）；重试计数；unknown 离散化（unknown → 人工 resolve 为 succeeded/failed，不自动重试）
- **已有基础**：RunFact 表、execution capability、审批恢复语义（M1）、occurrence 幂等（R3）

### B. AgentVersion + Deployment（M4 最小版）
- AgentDefinition（逻辑身份）+ AgentVersion（不可变配置快照：prompt/model/tool_groups/meta_info 的内容哈希——已有 `_agent_revision` 哈希作为版本标识基础）
- 发布/回滚：Deployment 指向 version；历史 Run 可解析当时的 version
- **不变量**：版本不可变（发布后配置冻结）；回滚不改历史 Run 的版本引用

### C. 评测门（M3 最小版）
- EvaluationRecord：数据集（golden 场景 fixture）+ 评分 + 关联 version
- 版本发布门：新 version 部署前须过评测门（可配置的最低分阈值）
- 双 Golden 场景（AIOps + 企业研究）复用 R2 知识场景作为第二个 fixture

### D. 扩展包生命周期（M7 最小版）
- 不可信代码不在 Gateway 主进程加载（红线，已有）；包 manifest + 来源 digest + 权限声明
- 企业私有目录（本地目录枚举 + 安装/启停/回滚）；签名机制本切片只做 digest 校验

## 2. 节奏（4–6 周，含 R4 冻结项）

| 周 | 交付 |
| --- | --- |
| 1–2 | Run 状态机 + AgentVersion/Deployment（数据模型 + 迁移 + 服务 + API） |
| 3 | 评测门 + 发布流水线（version → evaluation → deploy） |
| 4 | 扩展包 manifest/目录/安装回滚 |
| 5–6 | 真实部署演练（发布/回滚/评测门拒绝路径）+ R5 退出证据 |

## 3. 验收门

1. 版本发布/回滚演示：发布 v2 → 回滚 v1 → 历史 Run 仍解析 v2 的配置快照
2. 评测门：低分 version 被拒绝部署（可审计的拒绝记录）
3. 扩展包：安装未声明权限的包被拒绝；回滚恢复
4. Run 生命周期：取消传播 + unknown 人工处置演示
5. 迁移升降级 + 非空保护；四类安全反例（跨租户/Secret/副作用/审批）全程真实部署验证
