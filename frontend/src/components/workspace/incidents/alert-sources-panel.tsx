"use client";

import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import {
  AlertCircleIcon,
  ArrowRightIcon,
  CheckCircle2Icon,
  Code2Icon,
  CopyIcon,
  ExternalLinkIcon,
  EyeIcon,
  EyeOffIcon,
  GlobeIcon,
  KeyIcon,
  LayersIcon,
  Loader2Icon,
  PencilIcon,
  PlayIcon,
  PlusIcon,
  RefreshCwIcon,
  SaveIcon,
  SendIcon,
  ShieldCheckIcon,
  SignalIcon,
  Trash2Icon,
  WebhookIcon,
  WifiIcon,
  XCircleIcon,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "@/components/ui/dialog";
import {
  useAlertSources,
  useCreateAlertSource,
  useUpdateAlertSource,
  useDeleteAlertSource,
  type AlertSource,
  type AlertSourceCreate,
} from "@/core/alerting";

const SOURCE_TYPES = [
  { value: "webhook", label: "通用 Webhook", icon: WebhookIcon, desc: "任意 JSON 负载，通过字段映射解析" },
  { value: "alertmanager", label: "Alertmanager", icon: LayersIcon, desc: "Prometheus Alertmanager 标准格式" },
  { value: "grafana", label: "Grafana", icon: GlobeIcon, desc: "Grafana Alerting webhook 格式" },
  { value: "cloudwatch", label: "CloudWatch", icon: WifiIcon, desc: "AWS CloudWatch SNS 格式" },
];

const AUTH_MODES = [
  { value: "none", label: "无认证" },
  { value: "token", label: "Token 认证" },
];

interface FieldMappingEntry {
  field: string;
  jsonpath: string;
}

const DEFAULT_FIELD_MAPPINGS: FieldMappingEntry[] = [
  { field: "title", jsonpath: "$.alert.name" },
  { field: "summary", jsonpath: "$.alert.description" },
  { field: "severity", jsonpath: "$.alert.severity" },
  { field: "service", jsonpath: "$.labels.service" },
  { field: "environment", jsonpath: "$.labels.env" },
  { field: "status", jsonpath: "$.status" },
  { field: "labels", jsonpath: "$.labels" },
];

const FIELD_LABELS: Record<string, string> = {
  title: "告警标题",
  summary: "告警摘要",
  severity: "严重度",
  service: "服务名",
  environment: "环境",
  status: "状态",
  labels: "标签",
};

export function AlertSourcesPanel() {
  const { data: sources = [], isLoading, refetch } = useAlertSources();
  const { mutate: createSource, isPending: creating } = useCreateAlertSource();
  const { mutate: updateSource, isPending: updating } = useUpdateAlertSource();
  const { mutate: deleteSource } = useDeleteAlertSource();

  const [dialogOpen, setDialogOpen] = useState(false);
  const [editingSource, setEditingSource] = useState<AlertSource | null>(null);
  const [testDialogOpen, setTestDialogOpen] = useState(false);
  const [testSourceId, setTestSourceId] = useState<string | null>(null);
  const [testPayload, setTestPayload] = useState("");
  const [testResult, setTestResult] = useState<string | null>(null);
  const [testError, setTestError] = useState<string | null>(null);
  const [testing, setTesting] = useState(false);

  // Form state
  const [formName, setFormName] = useState("");
  const [formType, setFormType] = useState("webhook");
  const [formAuthMode, setFormAuthMode] = useState("none");
  const [formToken, setFormToken] = useState("");
  const [formTokenHeader, setFormTokenHeader] = useState("X-Alert-Token");
  const [showToken, setShowToken] = useState(false);
  const [fieldMappings, setFieldMappings] = useState<FieldMappingEntry[]>([]);

  const openCreate = () => {
    setEditingSource(null);
    setFormName("");
    setFormType("webhook");
    setFormAuthMode("none");
    setFormToken("");
    setFormTokenHeader("X-Alert-Token");
    setShowToken(false);
    setFieldMappings(DEFAULT_FIELD_MAPPINGS.map(m => ({ ...m })));
    setDialogOpen(true);
  };

  const openEdit = (source: AlertSource) => {
    setEditingSource(source);
    setFormName(source.name);
    setFormType(source.type);
    setFormAuthMode(source.auth_mode || "none");
    const config = source.config_json || {};
    setFormToken((config.token as string) || "");
    setFormTokenHeader((config.token_header as string) || "X-Alert-Token");
    setShowToken(false);
    const mappings = (config.field_mapping as Record<string, string>) || {};
    const entries: FieldMappingEntry[] = DEFAULT_FIELD_MAPPINGS.map(d => ({
      field: d.field,
      jsonpath: (mappings[d.field] as string) || d.jsonpath,
    }));
    setFieldMappings(entries);
    setDialogOpen(true);
  };

  const updateMapping = (field: string, jsonpath: string) => {
    setFieldMappings(prev => prev.map(m => m.field === field ? { ...m, jsonpath } : m));
  };

  const buildConfigJson = (): Record<string, unknown> => {
    const config: Record<string, unknown> = {};
    if (formAuthMode === "token") {
      config.token = formToken;
      config.token_header = formTokenHeader;
      config.auth_mode = "token";
    }
    // Build field_mapping
    const mapping: Record<string, string> = {};
    for (const entry of fieldMappings) {
      if (entry.jsonpath.trim()) {
        mapping[entry.field] = entry.jsonpath.trim();
      }
    }
    if (Object.keys(mapping).length > 0) {
      config.field_mapping = mapping;
    }
    return config;
  };

  const handleSave = () => {
    if (!formName.trim()) {
      toast.error("请输入告警源名称");
      return;
    }

    const config_json = buildConfigJson();

    if (editingSource) {
      updateSource(
        { sourceId: editingSource.id, data: { name: formName, type: formType, auth_mode: formAuthMode, config_json } },
        {
          onSuccess: () => {
            toast.success("告警源已更新");
            setDialogOpen(false);
          },
          onError: (err) => toast.error(err instanceof Error ? err.message : "更新失败"),
        }
      );
    } else {
      createSource(
        { name: formName, type: formType, auth_mode: formAuthMode, config_json },
        {
          onSuccess: () => {
            toast.success("告警源已创建");
            setDialogOpen(false);
          },
          onError: (err) => toast.error(err instanceof Error ? err.message : "创建失败"),
        }
      );
    }
  };

  const handleDelete = (sourceId: string, sourceName: string) => {
    if (confirm(`确定要删除告警源「${sourceName}」吗？`)) {
      deleteSource(sourceId, {
        onSuccess: () => toast.success("告警源已删除"),
        onError: (err) => toast.error(err instanceof Error ? err.message : "删除失败"),
      });
    }
  };

  const handleTest = (sourceId: string) => {
    setTestSourceId(sourceId);
    setTestPayload(JSON.stringify({
      alert: {
        name: "Test Alert",
        description: "This is a test alert for source verification",
        severity: "warning",
      },
      labels: {
        service: "test-service",
        env: "staging",
      },
      status: "firing",
    }, null, 2));
    setTestResult(null);
    setTestError(null);
    setTestDialogOpen(true);
  };

  const handleSendTest = async () => {
    if (!testSourceId) return;
    setTesting(true);
    setTestResult(null);
    setTestError(null);

    try {
      let payload: unknown;
      try {
        payload = JSON.parse(testPayload);
      } catch {
        setTestError("JSON 格式无效，请检查 payload 语法");
        setTesting(false);
        return;
      }

      const response = await fetch(`/api/alert-sources/${encodeURIComponent(testSourceId)}/test`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ payload }),
      });

      const json = await response.json();
      if (response.ok) {
        setTestResult(JSON.stringify(json, null, 2));
      } else {
        setTestError(json.detail || "测试发送失败");
      }
    } catch (err) {
      setTestError(err instanceof Error ? err.message : "请求失败");
    } finally {
      setTesting(false);
    }
  };

  const getWebhookUrl = (sourceId: string) => {
    const base = typeof window !== "undefined" ? `${window.location.protocol}//${window.location.host}` : "";
    return `${base}/api/ingest/${sourceId}`;
  };

  const copyToClipboard = (text: string) => {
    navigator.clipboard.writeText(text).then(() => toast.success("已复制到剪贴板"));
  };

  return (
    <div className="rounded-2xl border border-zinc-200/80 bg-background p-6 shadow-sm dark:border-zinc-800/80">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-sm font-semibold tracking-tight text-zinc-900 dark:text-zinc-50 flex items-center gap-2">
            <SignalIcon className="h-4 w-4 text-violet-500" />
            告警源管理 (Alert Sources)
          </h3>
          <p className="mt-1 text-xs text-muted-foreground">
            配置外部告警源的连接信息、字段映射和认证方式
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={() => refetch()} className="gap-1">
            <RefreshCwIcon className="h-3 w-3" />
            刷新
          </Button>
          <Button size="sm" onClick={openCreate} className="gap-1.5">
            <PlusIcon className="h-3.5 w-3.5" />
            添加告警源
          </Button>
        </div>
      </div>

      <div className="mt-5">
        {isLoading ? (
          <div className="space-y-2">
            {[1, 2].map(i => (
              <div key={i} className="h-20 animate-pulse rounded-lg bg-zinc-100 dark:bg-zinc-800" />
            ))}
          </div>
        ) : sources.length === 0 ? (
          <div className="py-8 text-center rounded-lg border border-dashed border-zinc-200 dark:border-zinc-800">
            <WebhookIcon className="h-8 w-8 mx-auto text-zinc-300 dark:text-zinc-600" />
            <p className="mt-2 text-sm text-muted-foreground">暂无告警源</p>
            <p className="text-xs text-muted-foreground mt-1">添加告警源以开始接收外部告警数据</p>
          </div>
        ) : (
          <div className="space-y-2">
            {sources.map(source => {
              const config = source.config_json || {};
              const mapping = config.field_mapping as Record<string, string> | undefined;
              const mappingCount = mapping ? Object.keys(mapping).length : 0;

              return (
                <div
                  key={source.id}
                  className="flex items-start justify-between p-4 rounded-xl border border-zinc-200/80 dark:border-zinc-800/80 bg-zinc-50/30 dark:bg-zinc-900/10 hover:bg-zinc-50 dark:hover:bg-zinc-900/20 transition-colors"
                >
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <WebhookIcon className="h-4 w-4 shrink-0 text-violet-500" />
                      <span className="text-sm font-semibold text-zinc-800 dark:text-zinc-200 truncate">{source.name}</span>
                      <Badge variant="outline" className="text-[9px] px-1 py-0 rounded font-mono">
                        {source.type}
                      </Badge>
                      <Badge
                        variant="outline"
                        className={`text-[9px] px-1 py-0 rounded ${
                          source.status === "active"
                            ? "text-emerald-600 border-emerald-300 bg-emerald-50"
                            : "text-zinc-400"
                        }`}
                      >
                        {source.status === "active" ? "活跃" : "停用"}
                      </Badge>
                    </div>
                    <div className="mt-1.5 flex flex-wrap items-center gap-2 text-[10px] text-muted-foreground">
                      <span className="flex items-center gap-1 font-mono">
                        <Code2Icon className="h-3 w-3" />
                        {getWebhookUrl(source.id)}
                      </span>
                      <button
                        type="button"
                        onClick={() => copyToClipboard(getWebhookUrl(source.id))}
                        className="hover:text-zinc-600 dark:hover:text-zinc-300"
                        title="复制 URL"
                      >
                        <CopyIcon className="h-3 w-3" />
                      </button>
                    </div>
                    <div className="mt-1 flex flex-wrap items-center gap-1.5">
                      {source.auth_mode !== "none" && (
                        <span className="flex items-center gap-1 text-[9px] text-amber-600 bg-amber-50 px-1.5 py-0.5 rounded">
                          <KeyIcon className="h-2.5 w-2.5" />
                          {source.auth_mode} 认证
                        </span>
                      )}
                      {mappingCount > 0 && (
                        <span className="text-[9px] text-violet-600 bg-violet-50 px-1.5 py-0.5 rounded">
                          {mappingCount} 个字段映射
                        </span>
                      )}
                    </div>
                  </div>
                  <div className="flex items-center gap-1 ml-3 shrink-0">
                    <Button
                      variant="ghost"
                      size="icon"
                      className="h-7 w-7"
                      onClick={() => handleTest(source.id)}
                      title="测试发送"
                    >
                      <PlayIcon className="h-3.5 w-3.5 text-emerald-500" />
                    </Button>
                    <Button
                      variant="ghost"
                      size="icon"
                      className="h-7 w-7"
                      onClick={() => openEdit(source)}
                      title="编辑"
                    >
                      <PencilIcon className="h-3.5 w-3.5" />
                    </Button>
                    <Button
                      variant="ghost"
                      size="icon"
                      className="h-7 w-7 text-rose-500 hover:text-rose-600"
                      onClick={() => handleDelete(source.id, source.name)}
                      title="删除"
                    >
                      <Trash2Icon className="h-3.5 w-3.5" />
                    </Button>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* Create / Edit Dialog */}
      <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
        <DialogContent className="max-w-2xl max-h-[85vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <SignalIcon className="h-5 w-5 text-violet-500" />
              {editingSource ? "编辑告警源" : "新建告警源"}
            </DialogTitle>
            <DialogDescription>
              配置外部告警源的连接信息、字段映射和认证方式
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-5 py-3">
            {/* Basic Info */}
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-1.5">
                <label className="text-xs font-semibold text-zinc-700 dark:text-zinc-300">告警源名称</label>
                <Input
                  placeholder="如: Prometheus K8s"
                  value={formName}
                  onChange={(e) => setFormName(e.target.value)}
                />
              </div>
              <div className="space-y-1.5">
                <label className="text-xs font-semibold text-zinc-700 dark:text-zinc-300">类型</label>
                <select
                  value={formType}
                  onChange={(e) => setFormType(e.target.value)}
                  className="w-full h-9 px-3 text-xs rounded-md border border-zinc-200 dark:border-zinc-800 bg-background outline-none"
                >
                  {SOURCE_TYPES.map(t => (
                    <option key={t.value} value={t.value}>{t.label}</option>
                  ))}
                </select>
              </div>
            </div>

            {/* Auth */}
            <div className="rounded-xl border border-zinc-200/80 bg-zinc-50/30 p-4 dark:border-zinc-800/80 dark:bg-zinc-900/10 space-y-3">
              <div className="flex items-center gap-2">
                <ShieldCheckIcon className="h-4 w-4 text-amber-500" />
                <span className="text-xs font-bold text-zinc-800 dark:text-zinc-200">认证配置</span>
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-1.5">
                  <label className="text-[10px] text-zinc-500">认证方式</label>
                  <select
                    value={formAuthMode}
                    onChange={(e) => setFormAuthMode(e.target.value)}
                    className="w-full h-8 px-2 text-xs rounded-md border border-zinc-200 dark:border-zinc-800 bg-background outline-none"
                  >
                    {AUTH_MODES.map(m => (
                      <option key={m.value} value={m.value}>{m.label}</option>
                    ))}
                  </select>
                </div>
                {formAuthMode === "token" && (
                  <div className="space-y-1.5">
                    <label className="text-[10px] text-zinc-500">Token Header</label>
                    <Input
                      placeholder="X-Alert-Token"
                      value={formTokenHeader}
                      onChange={(e) => setFormTokenHeader(e.target.value)}
                      className="h-8 text-xs"
                    />
                  </div>
                )}
              </div>
              {formAuthMode === "token" && (
                <div className="space-y-1.5">
                  <label className="text-[10px] text-zinc-500">Token 值</label>
                  <div className="relative">
                    <Input
                      type={showToken ? "text" : "password"}
                      placeholder="输入 token..."
                      value={formToken}
                      onChange={(e) => setFormToken(e.target.value)}
                      className="h-8 text-xs pr-8"
                    />
                    <button
                      type="button"
                      onClick={() => setShowToken(!showToken)}
                      className="absolute right-2 top-1/2 -translate-y-1/2 text-zinc-400 hover:text-zinc-600"
                    >
                      {showToken ? <EyeOffIcon className="h-3.5 w-3.5" /> : <EyeIcon className="h-3.5 w-3.5" />}
                    </button>
                  </div>
                </div>
              )}
            </div>

            {/* Field Mapping */}
            <div className="rounded-xl border border-zinc-200/80 bg-zinc-50/30 p-4 dark:border-zinc-800/80 dark:bg-zinc-900/10 space-y-3">
              <div className="flex items-center gap-2">
                <ArrowRightIcon className="h-4 w-4 text-violet-500" />
                <span className="text-xs font-bold text-zinc-800 dark:text-zinc-200">字段映射 (Field Mapping)</span>
              </div>
              <p className="text-[10px] text-muted-foreground">
                使用 JSONPath 表达式将外部 payload 字段映射到 PrismOS 告警字段
              </p>
              <div className="space-y-2">
                {fieldMappings.map(entry => (
                  <div key={entry.field} className="flex items-center gap-2">
                    <span className="w-24 shrink-0 text-[10px] font-semibold text-zinc-600 dark:text-zinc-400 text-right">
                      {FIELD_LABELS[entry.field] || entry.field}
                    </span>
                    <ArrowRightIcon className="h-3 w-3 shrink-0 text-zinc-400" />
                    <Input
                      placeholder={`$.${entry.field}`}
                      value={entry.jsonpath}
                      onChange={(e) => updateMapping(entry.field, e.target.value)}
                      className="h-7 text-xs font-mono flex-1"
                    />
                  </div>
                ))}
              </div>
            </div>

            {/* Webhook URL Preview (for new sources after creation) */}
            {editingSource && (
              <div className="rounded-xl border border-violet-200/80 bg-violet-50/30 p-4 dark:border-violet-800/60 dark:bg-violet-950/10">
                <div className="flex items-center gap-2">
                  <WebhookIcon className="h-4 w-4 text-violet-500" />
                  <span className="text-xs font-bold text-zinc-800 dark:text-zinc-200">Webhook URL</span>
                </div>
                <div className="mt-2 flex items-center gap-2">
                  <code className="flex-1 text-[10px] font-mono bg-background px-2 py-1.5 rounded border border-zinc-200 dark:border-zinc-800 break-all">
                    {getWebhookUrl(editingSource.id)}
                  </code>
                  <Button
                    variant="outline"
                    size="icon"
                    className="h-7 w-7 shrink-0"
                    onClick={() => copyToClipboard(getWebhookUrl(editingSource.id))}
                  >
                    <CopyIcon className="h-3.5 w-3.5" />
                  </Button>
                </div>
              </div>
            )}
          </div>

          <DialogFooter className="mt-4">
            <Button variant="outline" size="sm" onClick={() => setDialogOpen(false)}>
              取消
            </Button>
            <Button size="sm" onClick={handleSave} disabled={creating || updating} className="gap-1">
              {(creating || updating) ? <Loader2Icon className="h-3.5 w-3.5 animate-spin" /> : <SaveIcon className="h-3.5 w-3.5" />}
              {editingSource ? "保存修改" : "创建告警源"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Test Dialog */}
      <Dialog open={testDialogOpen} onOpenChange={setTestDialogOpen}>
        <DialogContent className="max-w-2xl max-h-[85vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <PlayIcon className="h-5 w-5 text-emerald-500" />
              测试告警源
            </DialogTitle>
            <DialogDescription>
              发送一条模拟告警 payload 到该告警源，验证配置是否正确
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-4 py-3">
            <div className="space-y-1.5">
              <label className="text-xs font-semibold text-zinc-700 dark:text-zinc-300">测试 Payload (JSON)</label>
              <textarea
                value={testPayload}
                onChange={(e) => setTestPayload(e.target.value)}
                rows={12}
                className="w-full rounded-lg border border-zinc-200 dark:border-zinc-800 bg-zinc-50 dark:bg-zinc-900 p-3 text-xs font-mono outline-none focus:border-violet-400 focus:ring-1 focus:ring-violet-200 resize-y"
              />
            </div>

            <Button onClick={handleSendTest} disabled={testing} className="w-full gap-2">
              {testing ? <Loader2Icon className="h-4 w-4 animate-spin" /> : <SendIcon className="h-4 w-4" />}
              {testing ? "发送中..." : "发送测试告警"}
            </Button>

            {testError && (
              <div className="rounded-lg border border-rose-200 bg-rose-50 p-3 dark:border-rose-800 dark:bg-rose-950/20">
                <div className="flex items-center gap-2 mb-1">
                  <XCircleIcon className="h-4 w-4 text-rose-500" />
                  <span className="text-xs font-semibold text-rose-700 dark:text-rose-400">测试失败</span>
                </div>
                <pre className="text-[10px] text-rose-600 dark:text-rose-400 whitespace-pre-wrap font-mono">{testError}</pre>
              </div>
            )}

            {testResult && (
              <div className="rounded-lg border border-emerald-200 bg-emerald-50 p-3 dark:border-emerald-800 dark:bg-emerald-950/20">
                <div className="flex items-center gap-2 mb-1">
                  <CheckCircle2Icon className="h-4 w-4 text-emerald-500" />
                  <span className="text-xs font-semibold text-emerald-700 dark:text-emerald-400">测试成功</span>
                </div>
                <pre className="text-[10px] text-emerald-600 dark:text-emerald-400 whitespace-pre-wrap font-mono max-h-40 overflow-y-auto">{testResult}</pre>
              </div>
            )}
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
