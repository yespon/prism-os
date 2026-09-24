import { fetchAuthApi } from "@/core/api/auth-client";

import type {
  AlertRule,
  AlertRuleCreate,
  AlertRuleUpdate,
  AlertSource,
  AlertSourceCreate,
  AlertSourceUpdate,
  AlertingSettings,
  IncidentDetail,
  IncidentSummary,
  IncidentStats,
  ChannelStatusResponse,
  TestNotificationRequest,
  TestNotificationResponse,
} from "./types";

function isObject(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function getErrorMessage(payload: unknown, fallback: string) {
  if (isObject(payload)) {
    const detail = payload.detail;
    if (typeof detail === "string" && detail.trim()) {
      return detail;
    }
    const message = payload.message;
    if (typeof message === "string" && message.trim()) {
      return message;
    }
  }
  return fallback;
}

export interface ListIncidentsParams {
  status?: string;
  severity?: string;
  service?: string;
  limit?: number;
  offset?: number;
}

export interface ListIncidentsResponse {
  incidents: IncidentSummary[];
  total: number;
}

export async function listIncidents(params: ListIncidentsParams = {}): Promise<ListIncidentsResponse> {
  const query = new URLSearchParams();
  if (params.status) query.set("status", params.status);
  if (params.severity) query.set("severity", params.severity);
  if (params.service) query.set("service", params.service);
  if (params.limit !== undefined) query.set("limit", params.limit.toString());
  if (params.offset !== undefined) query.set("offset", params.offset.toString());

  const queryString = query.toString();
  const response = await fetchAuthApi(`/api/incidents${queryString ? `?${queryString}` : ""}`);

  let json: unknown = null;
  try {
    json = await response.json();
  } catch {
    json = null;
  }

  if (!response.ok) {
    throw new Error(getErrorMessage(json, "加载告警事件失败"));
  }

  return json as ListIncidentsResponse;
}

export async function getIncident(incidentId: string): Promise<IncidentDetail> {
  const response = await fetchAuthApi(`/api/incidents/${encodeURIComponent(incidentId)}`);

  let json: unknown = null;
  try {
    json = await response.json();
  } catch {
    json = null;
  }

  if (!response.ok) {
    throw new Error(getErrorMessage(json, "加载告警详情失败"));
  }

  return json as IncidentDetail;
}

export interface GovernedTicketStatus {
  enabled: boolean;
  status: "denied" | "awaiting_approval" | "approved" | "rejected" | "expired" | "submitted" | "unknown" | null;
  decision_id?: string;
  approval_id?: string | null;
  tenant_id?: string;
  actor_id?: string | null;
  workload_id?: string;
  run_id?: string;
  policy_id?: string;
  policy_version?: string;
  reason_code?: string;
  ticket_id?: string | null;
  can_resume?: boolean;
}

export async function getGovernedTicketStatus(incidentId: string): Promise<GovernedTicketStatus> {
  const response = await fetchAuthApi(`/api/incidents/${encodeURIComponent(incidentId)}/governed-ticket`);
  if (!response.ok) throw new Error("加载受控建单状态失败");
  return response.json() as Promise<GovernedTicketStatus>;
}

export async function reviewGovernedTicket(approvalId: string, action: "approve" | "reject"): Promise<void> {
  const response = await fetchAuthApi(`/api/approvals/${encodeURIComponent(approvalId)}/${action}`, { method: "POST" });
  if (!response.ok) throw new Error(response.status === 403 ? "需要租户管理员审批权限" : "审批操作失败");
}

export async function resumeGovernedTicket(incidentId: string): Promise<GovernedTicketStatus> {
  const response = await fetchAuthApi(`/api/incidents/${encodeURIComponent(incidentId)}/governed-ticket/resume`, { method: "POST" });
  if (!response.ok) throw new Error(response.status === 403 ? "请求者权限已失效" : "恢复建单失败，请查看操作记录");
  return response.json() as Promise<GovernedTicketStatus>;
}

export interface DiagnoseResponse {
  status: string;
  incident_id: string;
  thread_id: string;
  agent_name: string;
  response: string;
}

export async function diagnoseIncident(incidentId: string): Promise<DiagnoseResponse> {
  const response = await fetchAuthApi(`/api/incidents/${encodeURIComponent(incidentId)}/diagnose`, {
    method: "POST",
  });

  if (!response.ok) {
    let detail = `Diagnosis failed: ${response.status}`;
    try {
      const payload = await response.json();
      if (payload.detail) detail = payload.detail;
    } catch {}
    throw new Error(detail);
  }

  return (await response.json()) as DiagnoseResponse;
}

export async function cancelDiagnosis(incidentId: string): Promise<{ status: string }> {
  const response = await fetchAuthApi(`/api/incidents/${encodeURIComponent(incidentId)}/diagnose/cancel`, {
    method: "POST",
  });
  return (await response.json()) as { status: string };
}

export async function suppressIncident(incidentId: string): Promise<{ status: string; incident_id: string }> {
  const response = await fetchAuthApi(`/api/incidents/${encodeURIComponent(incidentId)}/suppress`, {
    method: "POST",
  });

  let json: unknown = null;
  try {
    json = await response.json();
  } catch {
    json = null;
  }

  if (!response.ok) {
    throw new Error(getErrorMessage(json, "静默告警事件失败"));
  }

  return json as { status: string; incident_id: string };
}

export async function unsuppressIncident(incidentId: string): Promise<{ status: string; incident_id: string }> {
  const response = await fetchAuthApi(`/api/incidents/${encodeURIComponent(incidentId)}/unsuppress`, {
    method: "POST",
  });

  let json: unknown = null;
  try {
    json = await response.json();
  } catch {
    json = null;
  }

  if (!response.ok) {
    throw new Error(getErrorMessage(json, "恢复告警事件失败"));
  }

  return json as { status: string; incident_id: string };
}

export async function analyzeIncident(incidentId: string): Promise<{ status: string; incident_id: string }> {
  const response = await fetchAuthApi(`/api/incidents/${encodeURIComponent(incidentId)}/analyze`, {
    method: "POST",
  });

  let json: unknown = null;
  try {
    json = await response.json();
  } catch {
    json = null;
  }

  if (!response.ok) {
    throw new Error(getErrorMessage(json, "发起 AI 诊断分析失败"));
  }

  return json as { status: string; incident_id: string };
}

export async function claimIncident(incidentId: string): Promise<{ status: string; incident_id: string; owner_user_id: string }> {
  const response = await fetchAuthApi(`/api/incidents/${encodeURIComponent(incidentId)}/claim`, {
    method: "POST",
  });

  let json: unknown = null;
  try { json = await response.json(); } catch { json = null; }

  if (!response.ok) {
    throw new Error(getErrorMessage(json, "认领告警失败"));
  }

  return json as { status: string; incident_id: string; owner_user_id: string };
}

export async function assignIncident(incidentId: string, ownerUserId: string): Promise<{ status: string; incident_id: string; owner_user_id: string }> {
  const response = await fetchAuthApi(`/api/incidents/${encodeURIComponent(incidentId)}/assign`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ owner_user_id: ownerUserId }),
  });

  let json: unknown = null;
  try { json = await response.json(); } catch { json = null; }

  if (!response.ok) {
    throw new Error(getErrorMessage(json, "指派告警失败"));
  }

  return json as { status: string; incident_id: string; owner_user_id: string };
}

export async function resolveIncident(incidentId: string, resolutionNote?: string): Promise<{ status: string; incident_id: string }> {
  const response = await fetchAuthApi(`/api/incidents/${encodeURIComponent(incidentId)}/resolve`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ resolution_note: resolutionNote ?? null }),
  });

  let json: unknown = null;
  try { json = await response.json(); } catch { json = null; }

  if (!response.ok) {
    throw new Error(getErrorMessage(json, "恢复告警失败"));
  }

  return json as { status: string; incident_id: string };
}

export async function createTicket(incidentId: string): Promise<{ ticket_id: string; ticket_url: string | null; provider: string; incident_id: string }> {
  const response = await fetchAuthApi(`/api/incidents/${encodeURIComponent(incidentId)}/ticket`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ provider: "webhook" }),
  });

  let json: unknown = null;
  try { json = await response.json(); } catch { json = null; }

  if (!response.ok) {
    throw new Error(getErrorMessage(json, "创建工单失败"));
  }

  return json as { ticket_id: string; ticket_url: string | null; provider: string; incident_id: string };
}

export async function getIncidentTimeline(incidentId: string): Promise<Array<{ type: string; timestamp: string; title: string; detail: string | null; actor: string | null; metadata: Record<string, unknown> | null }>> {
  const response = await fetchAuthApi(`/api/incidents/${encodeURIComponent(incidentId)}/timeline`);

  let json: unknown = null;
  try { json = await response.json(); } catch { json = null; }

  if (!response.ok) {
    throw new Error(getErrorMessage(json, "加载事件时间线失败"));
  }

  return json as Array<{ type: string; timestamp: string; title: string; detail: string | null; actor: string | null; metadata: Record<string, unknown> | null }>;
}

export interface IncidentStatsSummary {
  total_firing: number;
  total_resolved: number;
  total_suppressed: number;
  severity_distribution: Record<string, number>;
  mttr_minutes: number | null;
  mtta_minutes: number | null;
  recent_trend: Array<{ date: string; count: number }>;
}

export async function getIncidentStatsSummary(): Promise<IncidentStatsSummary> {
  const response = await fetchAuthApi("/api/incidents/stats/summary");

  let json: unknown = null;
  try { json = await response.json(); } catch { json = null; }

  if (!response.ok) {
    throw new Error(getErrorMessage(json, "加载仪表盘数据失败"));
  }

  return json as IncidentStatsSummary;
}

export interface SourceHealthItem {
  source_id: string;
  source_name: string;
  source_type: string;
  status: string;
  last_received_at: string | null;
  total_received_24h: number;
  total_errors_24h: number;
  health: string; // healthy, warning, error, unknown
}

export async function getSourceHealth(): Promise<SourceHealthItem[]> {
  const response = await fetchAuthApi("/api/alert-sources/health");

  let json: unknown = null;
  try { json = await response.json(); } catch { json = null; }

  if (!response.ok) {
    throw new Error(getErrorMessage(json, "加载告警源健康状态失败"));
  }

  return json as SourceHealthItem[];
}



export async function listAlertSources(): Promise<AlertSource[]> {
  const response = await fetchAuthApi("/api/alert-sources");

  let json: unknown = null;
  try {
    json = await response.json();
  } catch {
    json = null;
  }

  if (!response.ok) {
    throw new Error(getErrorMessage(json, "加载告警源失败"));
  }

  return json as AlertSource[];
}

export async function createAlertSource(data: AlertSourceCreate): Promise<AlertSource> {
  const response = await fetchAuthApi("/api/alert-sources", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(data),
  });

  let json: unknown = null;
  try {
    json = await response.json();
  } catch {
    json = null;
  }

  if (!response.ok) {
    throw new Error(getErrorMessage(json, "创建告警源失败"));
  }

  return json as AlertSource;
}

export async function updateAlertSource(sourceId: string, data: AlertSourceUpdate): Promise<AlertSource> {
  const response = await fetchAuthApi(`/api/alert-sources/${encodeURIComponent(sourceId)}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });

  let json: unknown = null;
  try { json = await response.json(); } catch { json = null; }

  if (!response.ok) {
    throw new Error(getErrorMessage(json, "更新告警源失败"));
  }

  return json as AlertSource;
}

export async function deleteAlertSource(sourceId: string): Promise<void> {
  const response = await fetchAuthApi(`/api/alert-sources/${encodeURIComponent(sourceId)}`, {
    method: "DELETE",
  });

  if (!response.ok) {
    let json: unknown = null;
    try { json = await response.json(); } catch { json = null; }
    throw new Error(getErrorMessage(json, "删除告警源失败"));
  }
}



export async function listAlertRules(ruleType?: string): Promise<AlertRule[]> {
  const query = ruleType ? `?rule_type=${encodeURIComponent(ruleType)}` : "";
  const response = await fetchAuthApi(`/api/alert-rules${query}`);

  let json: unknown = null;
  try { json = await response.json(); } catch { json = null; }

  if (!response.ok) {
    throw new Error(getErrorMessage(json, "加载告警规则失败"));
  }

  return json as AlertRule[];
}

export async function createAlertRule(data: AlertRuleCreate): Promise<AlertRule> {
  const response = await fetchAuthApi("/api/alert-rules", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });

  let json: unknown = null;
  try { json = await response.json(); } catch { json = null; }

  if (!response.ok) {
    throw new Error(getErrorMessage(json, "创建告警规则失败"));
  }

  return json as AlertRule;
}

export async function updateAlertRule(ruleId: string, data: AlertRuleUpdate): Promise<AlertRule> {
  const response = await fetchAuthApi(`/api/alert-rules/${encodeURIComponent(ruleId)}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });

  let json: unknown = null;
  try { json = await response.json(); } catch { json = null; }

  if (!response.ok) {
    throw new Error(getErrorMessage(json, "更新告警规则失败"));
  }

  return json as AlertRule;
}

export async function deleteAlertRule(ruleId: string): Promise<void> {
  const response = await fetchAuthApi(`/api/alert-rules/${encodeURIComponent(ruleId)}`, {
    method: "DELETE",
  });

  if (!response.ok) {
    let json: unknown = null;
    try { json = await response.json(); } catch { json = null; }
    throw new Error(getErrorMessage(json, "删除告警规则失败"));
  }
}

export async function getAlertingSettings(): Promise<AlertingSettings> {
  const response = await fetchAuthApi("/api/alerting-settings");

  let json: unknown = null;
  try {
    json = await response.json();
  } catch {
    json = null;
  }

  if (!response.ok) {
    throw new Error(getErrorMessage(json, "加载告警设置失败"));
  }

  return json as AlertingSettings;
}

export async function updateAlertingSettings(data: AlertingSettings): Promise<AlertingSettings> {
  const response = await fetchAuthApi("/api/alerting-settings", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });

  let json: unknown = null;
  try {
    json = await response.json();
  } catch {
    json = null;
  }

  if (!response.ok) {
    throw new Error(getErrorMessage(json, "保存告警设置失败"));
  }

  return json as AlertingSettings;
}

export async function getIncidentStats(): Promise<IncidentStats> {
  const response = await fetchAuthApi("/api/incidents/stats");

  let json: unknown = null;
  try {
    json = await response.json();
  } catch {
    json = null;
  }

  if (!response.ok) {
    throw new Error(getErrorMessage(json, "加载告警统计数据失败"));
  }

  return json as IncidentStats;
}

export async function getChannelsStatus(): Promise<ChannelStatusResponse> {
  const response = await fetchAuthApi("/api/channels/");

  let json: unknown = null;
  try {
    json = await response.json();
  } catch {
    json = null;
  }

  if (!response.ok) {
    throw new Error(getErrorMessage(json, "获取通道状态失败"));
  }

  return json as ChannelStatusResponse;
}

export async function testNotification(data: TestNotificationRequest): Promise<TestNotificationResponse> {
  const response = await fetchAuthApi("/api/channels/test", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });

  let json: unknown = null;
  try {
    json = await response.json();
  } catch {
    json = null;
  }

  if (!response.ok) {
    throw new Error(getErrorMessage(json, "测试通道发送失败"));
  }

  return json as TestNotificationResponse;
}
