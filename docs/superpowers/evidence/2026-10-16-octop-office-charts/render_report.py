from pathlib import Path
import json
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
v=json.loads((HERE/'validation.json').read_text())
assert v['complete']
r=v['results']
body=f'''# 独立 XLSX 与 PPTX 图表

2026-10-16（Asia/Shanghai），沿用 `codex/octop-integration` 与 `de2fbc0`。

## 当前可用功能

| 入口 | 新增能力 | 本块边界 |
| --- | --- | --- |
| 原 `office_xlsx` | 工作簿生成柱状/折线/饼图、标题、位置、本表类别与带表头的数值系列；读取图表信息；编辑单元格保留图表引用、其他内容与原文件 | 不执行公式或刷新计算缓存；饼图单系列非负；完整透视、函数、桌面渲染仍待 |
| 原 `office_pptx` | 生成三类图表、缓存值、中文类别/标题和可编辑内嵌XLSX；读取系列/类别；编辑正文/备注保留图表及数据字节 | 工具内的图表数据修改、复杂组合/轴/样式/动画、桌面渲染仍待 |

创建最多32图/文档、每图200类别/8系列，XLSX每表16图。XLSX只接受本表有界矩形范围，标题行/类别对齐、实际有限数值；未计算公式不能充当已算图表值。PPTX类别与系列是字面数据；替换引擎默认工作表后，`=...`与URL标签不会自动成为公式/链接。内嵌工作表复用原包、公式、尺寸门，检查宏/外部关系和总展开量，保留原ZIP/XML/二进制拒绝门。原受限源码未复制，锁与引擎版本不变。

仍走原当前文件资源/租户/成员/线程/Agent授权、不覆盖原子输出与原下载接口。跨成员拒绝，生成中成员实际撤回不发布；图表不是新权限通道。原Policy/Approval/Action/Audit保持。

## 实际验收

- 相关集成：{r['related-final']}。
- 当前完整后端：{r['backend-full']}，不是旧全量结论复用。
- 自有隔离PostgreSQL：{r['postgres']}，实际成员/线程/资源事实；Auth夹具按原范围自有SQLite，不是目标环境N04。
- 当前默认权限、无网络后端镜像：{r['image-runtime']}；`{v['image']}`，10当前文件与宿主匹配，临时容器已清理。
- b5→b6→b5：{' / '.join(r['upgrade'])}；{v['upgrade_inputs']}固定宿主输入、宿主未改变。
- {v['frozen_inputs']}覆盖输入保持不变；CI静态、品牌和空白门按原要求执行，没有新增豁免。原始日志及演示在暂存/提交逐字节核对。

图表关系、实际工作表数值、PPTX缓存、可编辑内嵌数据由独立读取器/实际OOXML核对。没有Word/Excel/PowerPoint桌面渲染进程，不能将这些测试写成视觉兼容验收。图表名称/缓存检查不替代真实用户的模型行为。

前端、外部worker与来源/分发/清单/provisioner仅复用 `historical-reuse.json` 的未变输入范围；没有重复启动前端构建或外部镜像。后端应用改变，因此完整后端、Office PG、后端镜像和相关升级均新运行。

## 演示与后续退出条件

[可编辑工作簿](demo-charts.xlsx)、[可编辑演示文稿](demo-charts.pptx)包含柱状/折线/饼图及中文系列；是引擎实际文件，不是桌面截图或真实模型调用。工具schema明确操作和未完成边界。

第一里程碑、完整Office/专家/子Agent/外部接缝、N01–N15、O01–O42/F01–F12及原PrismOS M1–M7/Golden/五门全部保留。M1/N04真实模型→受控工具→可计数工单、真实远端运行/全部工具、N07远端CI等仍待；N08持久执行/委派不提前实施。下一步继续可独立的Office能力（含Unicode字体/中文PDF、表单/高级编辑）与外部业务接缝。未推送、部署、发布。
'''
(HERE/'README.md').write_text(body)
message='\n2026-10-16：沿用de2fbc0接入独立XLSX/PPTX三类图表，[证据](../evidence/2026-10-16-octop-office-charts/README.md)包含实际数据/图表关系、可编辑内嵌工作表、原当前权限/撤权/下载、新完整后端/隔离PG/无网络镜像与固定宿主升级回退。标签保持字面值，内嵌数据继续检查宏/外部关系/有界内容；原锁/引擎不变。前端与外部worker只按未变输入复用，未声称桌面渲染或完整Office退出。继续Unicode/中文PDF等独立能力，完整M1/N04/N07/N08依赖与全部原N/O/F、PrismOS退出条件保持。\n'
for name in ['2026-10-14-octop-functional-milestones.md','2026-10-09-octop-next-iterations.md']:
 p=ROOT/'docs/superpowers/plans'/name
 assert message not in p.read_text()
 with p.open('a') as stream:stream.write(message)
(HERE/'capability-delta.json').write_text(json.dumps({'base_commit':'de2fbc0','source_imported':'No newly copied upstream or excluded Office source','functional_integration':'Original office_xlsx/office_pptx create, inspect and text/cell edits now support bounded real chart packages and editable data','actual_acceptance':r,'remaining':['Desktop rendering','Advanced chart editing/formatting and full Office fidelity','Unicode/Chinese PDF, OCR/forms','All original expert/delegation/external runtime goals','M1/N04/N07 exits'],'M1_exited':False,'N08_started':False},indent=2)+'\n')
p=ROOT/'docs/superpowers/plans/2026-10-14-octop-functional-milestones.md'
s=p.read_text().replace('四外部包仅来源／制品验收', '四外部包来源/制品及独立SDK/MCP兼容已本地验收，未注册业务worker').replace('独立四格式基础读写/实际下载', '独立四格式基础读写、XLSX/PPTX三类图表/实际下载')
p.write_text(s)
print('Current chart evidence and existing plan status updated')
