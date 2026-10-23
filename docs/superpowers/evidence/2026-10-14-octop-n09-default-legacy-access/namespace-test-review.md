# 镜像内嵌套命令验收运行条件

默认Docker只读/proc/sys使bubblewrap --disable-userns无法建立嵌套隔离，实际首次镜像5失败/66通过日志保留，未改隔离代码、未跳过宿主和PostgreSQL真实命令。

自动审批拒绝--privileged验收容器，理由为宽泛宿主能力和设备访问超出已授权有界namespace测试；该命令未执行，没有通过另一方式授予同等权限。

采用原有受控AIO临时租约（readonly root/source、capdropALL/no-new-privileges、资源界限、当前身份/资源检查和清理）在最终镜像执行默认命令，1实际通过；镜像内65权限回归通过/6嵌套Local命令明确未覆盖。宿主与自有PostgreSQL包含全部13新增真实Local命令/撤权测试。标准Docker内Local嵌套namespace可用性仍待，不能将AIO证明改写为该配置通过。
