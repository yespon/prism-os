# N09-C1 本地退出审查

本审查承接 2026-10-12 resource-installation-plan 的第一个可交付切片及 2026-10-13 install-controls 的未退出项。各行只证明 C1 本地边界，不能替代完整 N09、远端 CI、N04/M1 或持久执行验收。最终状态由 validation.json 及直接核对的日志/代码摘要决定。

| 要求 | 权威实现及证据 | 不扩大结论的边界 |
| --- | --- | --- |
| 原安装故障、同文件系统完整暂存、排他发布、禁止覆盖 | install_receipts.py / installer.py；原 test_skill_import_recovery 中真实部分复制、同名并发、空目录、目录替换和发布前后进程退出；原失败证据保留在前批提交 | 实际 Linux 主机验证，不推断其他平台已实测 |
| 原 TenantSkill 唯一约束与 DB/FS 中断恢复、不同租户/用户、管理员共享 | skill_imports.py / skills.py；原 27 项矩阵继续在本轮 46 项模块中运行，SQLite/隔离 PostgreSQL 均核对真实原生行、文件字节和禁用 | 文件系统与 DB 不是单事务；未知不猜测成功、不补偿删除已发布内容 |
| 固定公开来源、有限适配、摘要和角色/目标约束 | agent_catalog.py / 原资源包构造；原来源篡改、客户端目标注入、普通成员共享拒绝及真实 Gateway/Auth/membership；wheel/sdist 核对 902 成员，三处映射/原版权保留 | 不安装依赖、不绑定 Agent、不授予执行权限；Office 仍独立实现 |
| 个人/共享确认、同名/未知、核对/继续/放弃及生命周期 | SourceSkillInstall / SkillImportOperations / 原上传隔离；已有确认、身份/关闭/语言/来源晚响应测试保持，本轮新增追加去重、失效/临时失败、旧恢复结果和坏收据无动作 | UI 提供意图，所有写入仍由服务端重新授权并核对文件/登记 |
| 超过 100 项、状态更新、并发新增及坏记录仍能定位 | 126 真实操作和最旧待登记恢复；恢复改写 mtime、页间新增三种标识范围与重查、游标 actor/tenant/shared/page_size、别名/并发损坏和 DB 不可用；真实鉴权两页冒烟 | 实时分页，不声称冻结快照；新增进入已访问区间须重新检查 |
| 明确保留及显式维护 | retain_all / automatic_deletion=false / owned_stage_abort_only；古老/登记/禁用/放弃收据字节不变；原 owned abort、被替换目录和已发布拒绝保持 | 不新增记录删除/TTL/GC 或自动认领复制恢复目录；原备份/恢复与后续 C2 继续适用 |
| 可运行/可验证候选、独立检出与持续源融入 | 完整前后端、当前/独立默认 make octop-build、真实 Gateway、固定 21 宿主输入 b5→b6→b5、锁/head/来源/索引/制品摘要 | 远端 CI 与真实 DB/模型/工单位置缺失的 N04 仍未退出 |

全部最终本地证据成立时，C1 按已定义的原生安装、恢复、确认、分页及保留策略退出；后续 C2 资源拥有/共享/复制/撤回、C3 非 Skill 绑定、C4 工具/依赖/执行治理、C5 专家行为/委派及独立 Office 继续保持。N08 持久执行仍依原 M1 门。
