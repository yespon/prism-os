"use client";

import { useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangleIcon,
  ClockIcon,
  ExternalLinkIcon,
  Loader2Icon,
  PlusIcon,
  SaveIcon,
  ShieldIcon,
  Trash2Icon,
  UserPlusIcon,
  ZapIcon,
} from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from "@/components/ui/sheet";
import { useAlertRules, useCreateAlertRule, useDeleteAlertRule, useUpdateAlertRule } from "@/core/alerting";
import type { AlertRule } from "@/core/alerting/types";

const SEVERITY_OPTIONS = ["critical", "major", "warning", "minor", "info"];
const ACTION_OPTIONS = [
  { value: "escalate_severity", label: "提升严重度" },
  { value: "notify_channel", label: "发送通知" },
  { value: "auto_assign", label: "自动指派" },
  { value: "auto_ticket", label: "自动创建工单" },
];

export function EscalationRulesPanel() {
  const { data: allRules = [], isLoading } = useAlertRules();
  const escalationRules = allRules.filter(r => r.rule_type === "escalation");
  const { mutate: createRule, isPending: creating } = useCreateAlertRule();
  const { mutate: deleteRule } = useDeleteAlertRule();

  const [sheetOpen, setSheetOpen] = useState(false);
  const [editingRule, setEditingRule] = useState<AlertRule | null>(null);

  // Form state
  const [formName, setFormName] = useState("");
  const [formSeverity, setFormSeverity] = useState<string[]>(["critical"]);
  const [formService, setFormService] = useState("");
  const [formSource, setFormSource] = useState("");
  const [formMinDuration, setFormMinDuration] = useState(15);
  const [formAction, setFormAction] = useState("escalate_severity");
  const [formActionConfig, setFormActionConfig] = useState("");

  const openCreate = () => {
    setEditingRule(null);
    setFormName("");
    setFormSeverity(["critical"]);
    setFormService("");
    setFormSource("");
    setFormMinDuration(15);
    setFormAction("escalate_severity");
    setFormActionConfig("");
    setSheetOpen(true);
  };

  const openEdit = (rule: AlertRule) => {
    setEditingRule(rule);
    setFormName(rule.name);
    const conditions = (rule.condition_json || {});
    setFormSeverity((conditions.severity as string[]) || []);
    setFormService((conditions.service as string) || "");
    setFormSource((conditions.source as string) || "");
    setFormMinDuration((conditions.min_duration_minutes as number) || 15);
    const actions = (rule.action_json || {});
    setFormAction((actions.action as string) || "escalate_severity");
    setFormActionConfig((actions.user_id ?? actions.channel) as string ?? "");
    setSheetOpen(true);
  };

  const toggleSeverity = (sev: string) => {
    setFormSeverity(prev =>
      prev.includes(sev) ? prev.filter(s => s !== sev) : [...prev, sev]
    );
  };

  const handleSave = () => {
    if (!formName.trim()) {
      toast.error("请输入规则名称");
      return;
    }

    const condition_json: Record<string, unknown> = {};
    if (formSeverity.length > 0) condition_json.severity = formSeverity;
    if (formService.trim()) condition_json.service = formService.trim();
    if (formSource.trim()) condition_json.source = formSource.trim();
    condition_json.min_duration_minutes = formMinDuration;

    const action_json: Record<string, unknown> = { action: formAction };
    if (formAction === "auto_assign" && formActionConfig.trim()) {
      action_json.user_id = formActionConfig.trim();
    } else if (formAction === "notify_channel" && formActionConfig.trim()) {
      action_json.channel = formActionConfig.trim();
    }

    if (editingRule) {
      // Edit not supported yet via simple API; delete + recreate
      deleteRule(editingRule.id, {
        onSuccess: () => {
          createRule(
            { name: formName, rule_type: "escalation", enabled: true, condition_json, action_json },
            {
              onSuccess: () => {
                toast.success("规则已更新");
                setSheetOpen(false);
              },
              onError: (err) => toast.error(err instanceof Error ? err.message : "保存失败"),
            }
          );
        },
      });
    } else {
      createRule(
        { name: formName, rule_type: "escalation", enabled: true, condition_json, action_json },
        {
          onSuccess: () => {
            toast.success("升级规则已创建");
            setSheetOpen(false);
          },
          onError: (err) => toast.error(err instanceof Error ? err.message : "创建失败"),
        }
      );
    }
  };

  const handleDelete = (ruleId: string) => {
    if (confirm("确定要删除这条升级规则吗？")) {
      deleteRule(ruleId, {
        onSuccess: () => toast.success("规则已删除"),
        onError: (err) => toast.error(err instanceof Error ? err.message : "删除失败"),
      });
    }
  };

  return (
    <div className="rounded-2xl border border-zinc-200/80 bg-background p-6 shadow-sm dark:border-zinc-800/80">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-sm font-semibold tracking-tight text-zinc-900 dark:text-zinc-50 flex items-center gap-2">
            <ZapIcon className="h-4 w-4 text-amber-500" />
            告警升级规则 (Escalation Rules)
          </h3>
          <p className="mt-1 text-xs text-muted-foreground">
            当告警满足条件时自动触发升级操作：提升严重度、发送通知、指派人员或创建工单
          </p>
        </div>
        <Sheet open={sheetOpen} onOpenChange={setSheetOpen}>
          <SheetTrigger asChild>
            <Button size="sm" onClick={openCreate} className="gap-1.5">
              <PlusIcon className="h-3.5 w-3.5" />
              添加规则
            </Button>
          </SheetTrigger>
          <SheetContent className="w-full sm:max-w-lg overflow-y-auto">
            <SheetHeader>
              <SheetTitle>{editingRule ? "编辑升级规则" : "新建升级规则"}</SheetTitle>
              <SheetDescription>
                配置告警升级条件和触发动作
              </SheetDescription>
            </SheetHeader>
            <div className="mt-6 space-y-5">
              {/* Rule Name */}
              <div className="space-y-1.5">
                <label className="text-xs font-semibold">规则名称</label>
                <Input
                  placeholder="如: Critical 告警 15 分钟无人认领自动升级"
                  value={formName}
                  onChange={(e) => setFormName(e.target.value)}
                />
              </div>

              {/* Severity Filter */}
              <div className="space-y-1.5">
                <label className="text-xs font-semibold">告警级别 (多选)</label>
                <div className="flex flex-wrap gap-1.5">
                  {SEVERITY_OPTIONS.map(sev => (
                    <button
                      key={sev}
                      type="button"
                      onClick={() => toggleSeverity(sev)}
                      className={`px-2.5 py-1 rounded-md text-[10px] font-semibold uppercase border transition-colors ${
                        formSeverity.includes(sev)
                          ? "bg-primary text-primary-foreground border-primary"
                          : "bg-background text-muted-foreground border-zinc-200 dark:border-zinc-700 hover:border-zinc-400"
                      }`}
                    >
                      {sev}
                    </button>
                  ))}
                </div>
              </div>

              {/* Service Filter */}
              <div className="space-y-1.5">
                <label className="text-xs font-semibold">限定服务 (可选)</label>
                <Input
                  placeholder="如: payment-service"
                  value={formService}
                  onChange={(e) => setFormService(e.target.value)}
                />
              </div>

              {/* Source Filter */}
              <div className="space-y-1.5">
                <label className="text-xs font-semibold">限定告警源 (可选)</label>
                <Input
                  placeholder="如: prometheus-prod"
                  value={formSource}
                  onChange={(e) => setFormSource(e.target.value)}
                />
              </div>

              {/* Min Duration */}
              <div className="space-y-1.5">
                <label className="text-xs font-semibold">最低持续时间 (分钟)</label>
                <div className="flex items-center gap-2">
                  <Input
                    type="number"
                    min={1}
                    max={1440}
                    value={formMinDuration}
                    onChange={(e) => setFormMinDuration(Number(e.target.value))}
                    className="w-24"
                  />
                  <span className="text-xs text-muted-foreground">告警触发超过此时间后执行升级</span>
                </div>
              </div>

              {/* Action */}
              <div className="space-y-1.5">
                <label className="text-xs font-semibold">升级动作</label>
                <div className="grid grid-cols-2 gap-2">
                  {ACTION_OPTIONS.map(opt => (
                    <button
                      key={opt.value}
                      type="button"
                      onClick={() => { setFormAction(opt.value); setFormActionConfig(""); }}
                      className={`p-2.5 rounded-lg border text-left transition-colors ${
                        formAction === opt.value
                          ? "border-amber-300 bg-amber-50 dark:border-amber-800 dark:bg-amber-950/30 text-amber-800 dark:text-amber-200"
                          : "border-zinc-200 dark:border-zinc-700 hover:border-zinc-400"
                      }`}
                    >
                      <div className="text-xs font-semibold">{opt.label}</div>
                      <div className="text-[10px] text-muted-foreground mt-0.5">
                        {opt.value === "escalate_severity" && "提升至下一级别"}
                        {opt.value === "notify_channel" && "发送 IM 通知"}
                        {opt.value === "auto_assign" && "指派给指定用户"}
                        {opt.value === "auto_ticket" && "自动创建外部工单"}
                      </div>
                    </button>
                  ))}
                </div>
              </div>

              {/* Action Config */}
              {(formAction === "auto_assign" || formAction === "notify_channel") && (
                <div className="space-y-1.5">
                  <label className="text-xs font-semibold">
                    {formAction === "auto_assign" ? "指派用户 ID" : "通知渠道名称"}
                  </label>
                  <Input
                    placeholder={formAction === "auto_assign" ? "如: user-123" : "如: feishu-prod"}
                    value={formActionConfig}
                    onChange={(e) => setFormActionConfig(e.target.value)}
                  />
                </div>
              )}

              {/* Save Button */}
              <Button onClick={handleSave} disabled={creating} className="w-full gap-1.5">
                {creating ? <Loader2Icon className="h-4 w-4 animate-spin" /> : <SaveIcon className="h-4 w-4" />}
                {editingRule ? "保存修改" : "创建规则"}
              </Button>
            </div>
          </SheetContent>
        </Sheet>
      </div>

      {/* Rules List */}
      <div className="mt-5">
        {isLoading ? (
          <div className="space-y-2">
            {[1, 2].map(i => (
              <div key={i} className="h-16 animate-pulse rounded-lg bg-zinc-100 dark:bg-zinc-800" />
            ))}
          </div>
        ) : escalationRules.length === 0 ? (
          <div className="py-8 text-center rounded-lg border border-dashed border-zinc-200 dark:border-zinc-800">
            <ShieldIcon className="h-8 w-8 mx-auto text-zinc-300 dark:text-zinc-600" />
            <p className="mt-2 text-sm text-muted-foreground">暂无升级规则</p>
            <p className="text-xs text-muted-foreground mt-1">点击 &quot;添加规则&quot; 配置第一条告警升级策略</p>
          </div>
        ) : (
          <div className="space-y-2">
            {escalationRules.map(rule => {
              const conditions = (rule.condition_json || {});
              const actions = (rule.action_json || {});
              const actionLabel = ACTION_OPTIONS.find(o => o.value === (actions.action as string))?.label ?? (actions.action as string) ?? "unknown";
              return (
                <div
                  key={rule.id}
                  className="flex items-center justify-between p-3 rounded-lg border border-zinc-200/80 dark:border-zinc-800/80 bg-zinc-50/50 dark:bg-zinc-900/20"
                >
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-semibold text-zinc-800 dark:text-zinc-200 truncate">{rule.name}</span>
                      {rule.enabled ? (
                        <Badge variant="outline" className="text-[9px] px-1 py-0 text-emerald-600 border-emerald-300 bg-emerald-50">启用</Badge>
                      ) : (
                        <Badge variant="outline" className="text-[9px] px-1 py-0 text-zinc-400">停用</Badge>
                      )}
                    </div>
                    <div className="mt-1 flex flex-wrap items-center gap-1.5 text-[10px] text-muted-foreground">
                      {Boolean(conditions.severity) && Array.isArray(conditions.severity) && (
                        <span className="flex items-center gap-1">
                          <AlertTriangleIcon className="h-3 w-3" />
                          {(conditions.severity as string[]).join(", ")}
                        </span>
                      )}
                      {Boolean(conditions.min_duration_minutes) && (
                        <span className="flex items-center gap-1">
                          <ClockIcon className="h-3 w-3" />
                          ≥{String(conditions.min_duration_minutes)}分钟
                        </span>
                      )}
                      {Boolean(conditions.service) && (
                        <span>服务: {String(conditions.service)}</span>
                      )}
                      <span className="text-zinc-400">→</span>
                      <span className="flex items-center gap-1 font-semibold text-amber-600 dark:text-amber-400">
                        <ZapIcon className="h-3 w-3" />
                        {String(actionLabel)}
                      </span>
                      {Boolean(actions.user_id) && <span className="text-zinc-400">({String(actions.user_id)})</span>}
                    </div>
                  </div>
                  <div className="flex items-center gap-1 ml-3">
                    <Button variant="ghost" size="icon" className="h-7 w-7" onClick={() => openEdit(rule)}>
                      <span className="text-[10px]">编辑</span>
                    </Button>
                    <Button variant="ghost" size="icon" className="h-7 w-7 text-rose-500 hover:text-rose-600" onClick={() => handleDelete(rule.id)}>
                      <Trash2Icon className="h-3.5 w-3.5" />
                    </Button>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
