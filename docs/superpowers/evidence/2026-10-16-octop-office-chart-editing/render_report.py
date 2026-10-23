from pathlib import Path
import json
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
v=json.loads((HERE/'validation.json').read_text())
assert v['complete']
r=v['results']
body=f'''# 原生 PPTX 图表数据编辑闭环

2026-10-16（Asia/Shanghai）。沿用 `codex/octop-integration` 与 `630a5f1`。

原 `office_pptx` 新增 `edit_charts` 和 `chart_changes`：按1起始的页码/图表序号批量更新类别、系列、数值与可选标题。现有柱状、折线、饼图类型保持；标题省略时保留，空标题移除。原位置、图表样式、已验证的系列颜色/标题字样和未选中的图表/工作表保持；原输入文件不覆盖。

缓存与可编辑XLSX数据同步更新。标签/系列名中的 `=...` 和URL保持普通文字，不自动转为公式或链接。复用已有200类别/8系列、32图表更新、2M输入及ZIP/XML/宏/外部关系/嵌套工作表限制。重复目标、失配数据、非有限数值、图表类型改变拒绝。多个图形或图表共用图表/工作表部分时明确拒绝，防止修改一个目标而连带更改其他图表；独立复制/完整组合图与高级样式往返仍待。

仍经原当前资源/账号/成员/租户/线程/Agent访问权限和持有祖先的不覆盖原子输出。原鉴权下载与跨成员拒绝、生成中实际撤权不发布通过，未创建另一套Policy/Approval/Action/Audit或持久执行事实。

## 实际验收

- 相关引擎/图表/权限集成：58通过；三种实际缓存/内嵌工作表、系列增减、颜色/标题样式/位置、其他图表字节和源文件保持均核对。
- 当前完整后端：{r['backend-full']}，本块应用修改不复用旧全量结论。
- 自有隔离PostgreSQL：{r['postgres']}。Auth夹具仍为原自有SQLite范围，不作目标数据库/真实模型验收。
- 当前默认权限、无网络镜像：{r['image-runtime']}；`{v['image']}`，当前文件匹配且容器已清理。
- b5→b6→b5：{' / '.join(r['upgrade'])}；{v['upgrade_inputs']}宿主契约固定、宿主未变。
- {v['frozen_inputs']}输入保持固定；原CI静态/品牌/空白门、原始日志与演示的暂存/提交字节检查保留，没有新增豁免。

前端/严格构建/追踪、字体独立证据、来源/分发/清单、外部SDK worker与provisioner只按 `historical-reuse.json` 未变范围复用。没有重新运行已通过且输入未变的前端或外部worker验证。新完整后端包含当前字体验证；实际模型、外部服务/工单和桌面Office仍待相应环境/退出门。

[编辑前](demo-original.pptx) / [编辑后](demo-edited.pptx)是实际PPTX与可编辑数据，非桌面渲染截图；完整高级图表和Office等价不据此完成。

完整N01–N15、O01–O42/F01–F12和原PrismOS M1–M7/Golden/五门保留。M1/N04真实模型→原受控工具→可计数工单、真实远端运行及全部工具、N07远端CI仍待；N08持久执行/委派不启动。继续原独立Office/外部接缝队列，未推送、部署、发布。
'''
(HERE/'README.md').write_text(body)
message='\n2026-10-16：沿用630a5f1接入原生PPTX图表数据编辑，[证据](../evidence/2026-10-16-octop-office-chart-editing/README.md)包含三类图表缓存/可编辑工作表同步、系列/类别/标题编辑、已验证样式/位置和其他图表保持、共享部分拒绝及原权限/下载/撤权；当前完整后端、隔离PG、当前镜像与固定宿主升级回退均新验收。未变前端/来源/制品/worker按范围复用，完整高级图表/Office与所有原N/O/F、PrismOS目标和M1/N04/N07/N08前置门保持。\n'
for name in ['2026-10-14-octop-functional-milestones.md','2026-10-09-octop-next-iterations.md']:
 p=ROOT/'docs/superpowers/plans'/name
 assert message not in p.read_text()
 with p.open('a') as stream:stream.write(message)
(HERE/'capability-delta.json').write_text(json.dumps({'base_commit':'630a5f1','source_imported':'No excluded Office source imported','functional_integration':'Original office_pptx edit_charts with current file authority and synchronized caches/editable workbook','actual_local_acceptance':r,'remaining':['Shared-part independent cloning','Advanced combination/type/layout/style/full Office fidelity','Real models/external tools/tickets, real remote and remote CI','All original N/O/F and PrismOS exits'],'M1_exited':False,'N08_started':False},indent=2)+'\n')
print('Chart editing report and existing plan status updated')
