# N09-A：完整来源资源声明与只读格式预检

2026-10-12，基线 `fddc307`。本批完成 N09 的资源声明/摘要与只读宿主格式预检；N09 整体未完成，资源未安装/授权/执行，M1 未退出。N08 仅形成设计候选，没有创建生命周期模型/Worker/迁移。

## 修改与覆盖

新增认证/租户 GET `/api/agent-catalog/templates/{template_id}/resources?locale=zh|en`。固定原来源和 bundle/member digest，逐文件核对受保护输入；支持 warm catalog 下的变更/新增/符号链接拒绝。预检复用原 Skill validator；没有放宽规则或改写原样字节。

全 18 专家保留源 **352** 个成员全部核对，包含 **297** 资源文件和 **55** persona/manifest 文件。旧 bundle 只有 270 文件，新声明补齐 **27** 个参考资料、知识种子、USER/AGENTS 等辅助模板。USER/MEMORY 是上游静态种子，不代表当前私有用户资料；本批不复制到活动会话。subagent 的固定模板来源另列，不虚构配套资源。

60 个资源组中，24 个 Skill frontmatter 格式 compatible，3 个 needs_adapter，33 个非 Skill 资源 binding_required。这些都是来源/格式事实，**不是已安装、依赖已具备或执行权限**。`installation_checked`、`runtime_dependencies_checked`、`execution_ready`、`permission_grants` 明确为 false。四个受限 Office 子树继续保留独立实现目标。

## 验证

| 检查 | 实际结果 |
| --- | --- |
| 新资源契约 | 27 通过：18 专家完整成员/digest、双语言、辅助文件、格式缺口、subagent、warm-cache 篡改/新增/别名、鉴权与无写入 |
| 完整后端 | 1,577 通过、18 跳过、30 warnings；跳过不记通过 |
| 完整前端 | 43 文件 / 128 通过；本批前端源未修改 |
| 统一候选构建 | 214 后端 / 37 前端、类型、原目录/人格/头像、真实 Uvicorn 认证、全 18 专家资源 API、902 成员 wheel/sdist、生产构建通过 |
| 独立候选 | fresh fddc307 检出+记录候选 overlay，自有 `.venv`/`node_modules`，原锁定安装；同一构建入口通过，NFT 均在自有 frontend 内 |
| 升级/回退 | 新取得固定 b5 原始来源、验证并过滤；b5→b6→b5 三轮各 80 项相同宿主契约通过；11 份宿主源码/测试摘要全程固定 |
| 静态门 | 修改面及 CI Ruff、来源/清单/品牌/差异检查通过；远端 CI 未运行 |

[summary.json](summary.json) 给出计数与三处实际格式缺口；[declarations.json](declarations.json) 保存全部成员和来源；[upgrade.json](upgrade.json)、[gateway.json](gateway.json)、[independence.json](independence.json)、[candidate-code.json](candidate-code.json) 与日志由 [validation.json](validation.json) 记录 SHA。日志保留已有 warning，不通过升级依赖掩盖。

## 下一批与完整范围

先将预检/实际安装状态接入 UI；核对名称/来源冲突、个人/租户拥有与共享可见/复制/使用/编辑/撤回，再实施有界原子安装与失败恢复。三处格式差异需要保持原字节的派生宿主适配：CVM-cluster 的名称、Office file_reader 的名称、TencentCloud API 的扩展 frontmatter。

允许安装配置不等于授权执行；脚本需要 tool/schema/PEP/Sandbox，知识种子需要 N10/M6 的私有索引/ACL，子 Agent 委派和固定执行引用依赖 N08。完整 N09 要逐一验收 18 专家，至少两个有资源专家和一个实际委派，不能用本批来源/格式检查替代。完整 O01–O42/F01–F12 与原 PrismOS 门保持不变；N07-B 远端 CI、N04 真实环境仍待验。
