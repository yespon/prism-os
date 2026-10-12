# N09-C1：原 Skill 导入的发布与恢复接缝

2026-10-12；基线 `97d5ab0`。本批实施 N09-C1 的后端接缝和固定来源显式安装 API，完整 C1 用户界面及完整 N09 仍待后续。原 N01–N15、O01–O42/F01–F12 与 PrismOS 身份/资源/治理设计保留。M1 未退出，不实施 N08 持久执行。

修复前真实故障探针重现三项失败：部分 copytree 留下最终半成品目录；同名并发返回 FileExistsError 而非原冲突类型；数据库已提交后响应失败仍删除已注册文件。原 `/api/skills/install`、personal/tenant import 现在共用一个注册服务，客户端仍使用同一原安装器。

## 发布与归属

先在目标父目录创建唯一隐藏暂存，校验完整归档、严格 SKILL frontmatter、复制前后全部成员 SHA 和目录 identity，再以排他重命名发布。现有目录即使为空或内容相同也不覆盖。暂存和最终目录在相同文件系统；不能安全发布时报错，不能降为覆写 rename。

Linux 使用 [renameat2 / RENAME_NOREPLACE](https://man7.org/linux/man-pages/man2/rename.2.html)，macOS 使用 [renamex_np / RENAME_EXCL](https://developer.apple.com/documentation/foundation/urlresourcevalues/volumesupportsexclusiverenaming)，Windows 使用拒绝已有目标的 os.rename。Linux 实际验证；macOS/Windows 分支不据此声称运行或断电耐久通过。Linux 暂存文件、目录和原子收据更新执行 fsync；Windows stdlib 不提供目录 fsync，不能扩展本轮 Linux 耐久结论。

每次操作在目标父目录保存 `.prismos-import-<uuid>.json`，含 scope、目标名、暂存名、目录 dev/inode、全部文件摘要、归档摘要和阶段。记录位于 Skill 目录之外，不改变原 SKILL/来源/版权附件，也不成为第二套 Skill 注册表。原 TenantSkill 及其 tenant/user/name 唯一约束仍是登记事实。隐藏暂存没有登记，不会由原数据库驱动 custom loader 发现。

只在发布前删除可证明属于本操作的暂存目录。发布后的错误、取消或进程退出都不能据 Python 异常删除最终文件；数据库提交与文件发布不是单事务。数据库已成功返回才标记 registered；超时或未知结果保留发布文件及收据供核对。

## 原生恢复 API

personal：`GET /api/skills/personal/imports`、`GET /api/skills/personal/imports/{operation_id}`、`POST .../{operation_id}/recover` 和 `POST .../{operation_id}/abort`。tenant 对应 `/api/tenants/skills/imports`，使用原 require_tenant_admin。所有目标由当前认证 tenant/actor 计算；用户/租户变更不能读取其他 scope 的记录。响应不返回绝对路径或文件内容。

恢复时核对当前原生行、目录 identity 与全部成员摘要。已登记且路径/内容相符只观察现有行，不猜测原操作创建了该行，也不再次登记或启用已禁用资源。没有原生行时，明确 POST 可以登记完整的自有发布文件；完整自有暂存可在再次排他发布后登记。已有行指向别处、被替换目录、内容变更或状态无法核对都拒绝并保留现状。

放弃只针对 allocated/staging/prepared 的自有暂存。已发布、已登记或发布后结果未知的文件必须走原资源管理，不能借 abort 删除。不同 inode 的替换暂存也拒绝删除。操作收据保留以便诊断与幂等核对，自动 GC 尚未加入。

## 固定来源安装

`POST /api/agent-catalog/templates/{template_id}/resources/{resource_id}/install`，body 仅接受 scope=personal|tenant 与确认过的 bundle_sha256；额外 tenant/user/path 参数拒绝。服务器重读固定公开来源和源成员、校验确认摘要、有限格式映射与版权附件，再调用同一安装/登记服务。tenant scope 仍要求原管理员。源改变、同名冲突和未知结果分别拒绝或返回操作 ID；不自动绑定 Agent、安装依赖、授予 Secret 或执行权限。

后续用户界面应在创建/编辑预检中确认个人/租户导入，并明确展示冲突、未知结果、记录核对、继续恢复和放弃自有暂存。客户端中止请求不证明服务器回滚，必须先核对当前操作。C2 拥有/共享/复制/撤回，非 Skill 绑定、工具/schema/PEP/Sandbox、18 专家实际行为及独立 Office 能力继续保留。

## 验证要求

原三项故障先红后绿；部分复制不可见、复制缺成员、晚出现空目录、暂存替换/内容变更、scope symlink、真实 DB 提交后超时/响应失败、唯一约束与登记冲突、进程在发布前后退出、恢复重试/禁用/权限/跨 scope 均使用真实文件系统及 SQLite/隔离 PostgreSQL。原 scope 测试不再用接受错误参数的假安装器证明成功；请求上下文契约的注册回调仍明确为 mock，完整事实由独立 SQLite/PG 用例证明。

后端完整回归、前端完整回归、统一构建、真实认证 Gateway（仅隔离 Skill 根）、独立锁定安装/构建、固定宿主 b5→b6→b5、唯一 head、源码/品牌/制品均按原门执行。新 CI PostgreSQL 步骤仅配置，远端运行仍待 N07-B。N04 真实环境、M1/M2 和完整 N09 不据本批退出。
