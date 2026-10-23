from pathlib import Path
import json
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
v=json.loads((HERE/'validation.json').read_text())
assert v['complete']
r=v['results']
body=f'''# 原生 DOCX 的当前授权图片插入

2026-10-16（Asia/Shanghai），沿用 `codex/octop-integration` 与 `26eaca7`。

原 `office_docx` 新增 `add_images`/`images`：从当前有权读取的PNG/JPEG文件插入内嵌图片，支持尺寸和替代文字，按比例追加到最终section之前。正文/表格/页眉页脚和其他包成员保持；图片去重、drawing/relationship标识避开已有值。原文件不覆盖，输出仍由原鉴权下载/呈现入口交付。

图片限16张、单张4MiB、累计8MiB、8192边长/1600万像素，规范化为静态PNG。JPEG方向先校正，EXIF/ICC等元数据不带入；SVG/动画/非法图片拒绝。宽度0.1..6.2英寸，按比例高度不得超过9英寸；替代文字有界。保留原ZIP/XML/宏/外部关系/文件大小门。复杂锚点、裁剪、文字环绕和Word桌面布局仍待。

输入DOCX、每张图片和输出均复用原账号/成员/租户/线程/Agent/资源授权。处理后重查全部来源，撤权拒绝发布，输出使用原不覆盖原子创建。原Policy/Approval/Action/Audit保持，无新执行生命周期。

## 实际验收

- 当前相关：{r['related-final']}；实际图片字节/像素、关系/尺寸/替代文字、连续插入/去重、mammoth独立读取、原下载和实际撤权通过。
- 当前完整后端：{r['backend-full']}，不是历史全量复用。
- 自有隔离PostgreSQL：{r['postgres']}；Auth夹具仍为原自有SQLite范围，不作N04目标环境验收。
- 当前默认权限、无网络镜像：{r['image-runtime']}；`{v['image']}`，当前源码/测试/锁匹配，容器清理。
- b5→b6→b5：{' / '.join(r['upgrade'])}；{v['upgrade_inputs']}固定宿主输入，宿主未变。
- {v['frozen_inputs']}输入冻结；原CI静态/品牌/空白门及原始日志/示例的暂存与提交字节核对保留，没有新增豁免。

初次相关验收2失败/68通过：图片本身新增空正文的绘图段落、工具schema新增images，旧预期未覆盖；随后明确保留原段落前缀/其他内容，并更新精确schema预期。原日志不改写，JPEG方向/元数据另有真实回归。

[原DOCX](demo-source.docx)、[图文DOCX](demo-pictured.docx)、[内嵌数据图](demo-source.png)是独立引擎实际文件；mammoth实际识别img与替代文字，不是Word桌面渲染或真实模型/专家调用。未复制任何受限Office源码。

前端/严格构建/追踪、来源/制品/清单、外部SDK worker和provisioner仅按historical-reuse.json未变输入复用；应用改变后完整后端/相关PG/镜像/升级均新验收。独立Office完整高级能力、专家/委派/外部运行和原N01–N15、O01–O42/F01–F12及PrismOS M1–M7/Golden/五门保留。M1/N04真实模型→受控工具→可计数工单、真实远端运行及全部工具、N07远端CI仍待；N08不提前启动。未推送、发布、部署。
'''
(HERE/'README.md').write_text(body)
message='\n2026-10-16：沿用26eaca7接入原生DOCX授权图片插入，[证据](../evidence/2026-10-16-octop-office-docx-images/README.md)包含实际PNG/JPEG规范化/方向/元数据清理、内嵌关系/尺寸/替代文字、原正文/表格/页眉页脚保持、独立读取与原权限/下载/撤权，当前完整后端/隔离PG/镜像/固定宿主升级回退新验收。初始断言失败保留，源Office排除不变；高级版式/环绕/桌面渲染和所有原目标/退出条件保持，M1/N04/N07待验，N08不启动。\n'
for name in ['2026-10-14-octop-functional-milestones.md','2026-10-09-octop-next-iterations.md']:
 p=ROOT/'docs/superpowers/plans'/name
 assert message not in p.read_text()
 with p.open('a') as stream:stream.write(message)
(HERE/'capability-delta.json').write_text(json.dumps({'base_commit':'26eaca7','source_imported':'No excluded Office source copied','functional_integration':'Original office_docx add_images with current authorized files, normalized inline PNG, aspect ratio and alt text','actual_local_acceptance':r,'remaining':['Advanced placement/wrapping/cropping/full Office fidelity','Desktop rendering','Actual expert/delegation/external runtime and original platform goals','M1/N04/N07 exits'],'M1_exited':False,'N08_started':False},indent=2)+'\n')
print('DOCX images evidence and existing plan status updated')
