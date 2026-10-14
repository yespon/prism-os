# 范围与复用

默认Agent原“全部当前”语义复用同一current_skill_resources：仅该成员的public/tenant/personal启用实例，成员和租户当前有效。旧具名Agent在每次工具使用前按原私有优先查询一次，固定真实id，原ThreadBinding归属和名字必须匹配；后续按该id及配置、资源完整成员快照复验，不能换同名对象。未绑定旧空skills可执行拥有者线程命令，资源集合为空；非空旧名字必须使用已有API明确scope/resource_id，不自动处理歧义。

Prompt、成员目录/文本/图像以及命令共用解析。原共享Agent禁止固定个人资源不变，当前租户资源启用/撤回检查不变。宿主tenant身份没有provider或provider返回None拒绝全局回退；无租户的独立Harness仍按原路径。

Frontend跟踪输入自e0c7f29以来无变化，复用499文件既有完整249用例、生产构建/双安装/50traces。原902成员、外部4包7制品、锁、wheel/sdist、Alembic链保持既有历史覆盖；本批另只读verify来源/目录/品牌。完整后端不能复用旧结果，当前完整门待终态。新数据库/镜像/升级证据范围按validation明确。

整个M1未退出；Terminal SSH上下文/资产/Keychain、远端全部工具、copy/share目标重授权、通用Secret目的及N04真实环境/N07CI仍待。默认/旧合法路径不等于完整C1/C2或所有Octop能力完成。原N/O/F及PrismOS Policy/Approval/Action/Audit、N08启动门不变。

最终完整后端另修正test_lead_agent_model_resolution的单测隔离fixture；只改变该模型单测文件，运行/成员/命令及本批新增回归输入未改。原已通过PostgreSQL/镜像65+AIO1/固定82宿主输入升级范围可复用，不将其声称覆盖该模型单测修正；模型11和新完整后端另验。
