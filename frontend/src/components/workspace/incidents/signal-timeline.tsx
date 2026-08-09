"use client";

import {
  ActivityIcon,
  BotIcon,
  CheckCircle2Icon,
  ClockIcon,
  DatabaseIcon,
  SparklesIcon,
  TicketIcon,
  UserIcon,
  UserPlusIcon,
  VolumeXIcon,
  WrenchIcon,
} from "lucide-react";
import { useState } from "react";

import { Badge } from "@/components/ui/badge";
import { formatDate, getSeverityBadgeStyles } from "@/core/alerting";
import type { Signal } from "@/core/alerting/types";

export interface TimelineEvent {
  type: "signal" | "ai_analysis" | "diagnosis" | "action" | "status_change";
  timestamp: string;
  title: string;
  detail: string | null;
  actor: string | null;
  metadata: Record<string, unknown> | null;
}

interface IncidentTimelineProps {
  signals?: Signal[];
  timeline?: TimelineEvent[];
  isLoading?: boolean;
}

function displayMetadataValue(value: unknown, fallback = ""): string {
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  if (value === null || value === undefined) return fallback;
  return JSON.stringify(value);
}

function metadataKey(metadata: Record<string, unknown>, type: string, timestamp: string): string {
  const signalId = metadata.signal_id;
  return typeof signalId === "string" || typeof signalId === "number"
    ? String(signalId)
    : `${type}-${timestamp}`;
}

const eventTypeConfig: Record<string, { icon: React.ComponentType<{ className?: string }>; color: string; bgColor: string }> = {
  signal: { icon: ActivityIcon, color: "text-rose-600 dark:text-rose-400", bgColor: "bg-rose-50 dark:bg-rose-950/20 border-rose-200 dark:border-rose-800" },
  ai_analysis: { icon: SparklesIcon, color: "text-violet-600 dark:text-violet-400", bgColor: "bg-violet-50 dark:bg-violet-950/20 border-violet-200 dark:border-violet-800" },
  diagnosis: { icon: WrenchIcon, color: "text-amber-600 dark:text-amber-400", bgColor: "bg-amber-50 dark:bg-amber-950/20 border-amber-200 dark:border-amber-800" },
  action: { icon: UserIcon, color: "text-indigo-600 dark:text-indigo-400", bgColor: "bg-indigo-50 dark:bg-indigo-950/20 border-indigo-200 dark:border-indigo-800" },
  status_change: { icon: CheckCircle2Icon, color: "text-emerald-600 dark:text-emerald-400", bgColor: "bg-emerald-50 dark:bg-emerald-950/20 border-emerald-200 dark:border-emerald-800" },
};

function EventIcon({ type }: { type: string }) {
  const config = eventTypeConfig[type];
  const Icon = config?.icon ?? ActivityIcon;
  const color = config?.color ?? "text-rose-600 dark:text-rose-400";
  const bgColor = config?.bgColor ?? "bg-rose-50 dark:bg-rose-950/20 border-rose-200 dark:border-rose-800";
  return (
    <span className={`absolute -left-[18.5px] top-1.5 flex h-7 w-7 items-center justify-center rounded-full border-2 bg-background ${bgColor}`}>
      <Icon className={`h-3.5 w-3.5 ${color}`} />
    </span>
  );
}

export function IncidentTimeline({ signals, timeline, isLoading }: IncidentTimelineProps) {
  const [expandedPayloads, setExpandedPayloads] = useState<Record<string, boolean>>({});
  const [expandedLabels, setExpandedLabels] = useState<Record<string, boolean>>({});

  const togglePayload = (sigId: string) => {
    setExpandedPayloads(prev => ({ ...prev, [sigId]: !prev[sigId] }));
  };

  const toggleLabels = (sigId: string) => {
    setExpandedLabels(prev => ({ ...prev, [sigId]: !prev[sigId] }));
  };

  // If we have a unified timeline, render it; otherwise fall back to signals-only
  const hasTimeline = timeline && timeline.length > 0;
  const hasSignals = signals && signals.length > 0;

  const totalEvents = hasTimeline ? timeline.length : hasSignals ? signals.length : 0;

  return (
    <div className="rounded-2xl border border-zinc-200/80 bg-background p-6 shadow-sm dark:border-zinc-800/80">
      <h3 className="text-sm font-semibold tracking-tight text-zinc-900 dark:text-zinc-50 flex items-center gap-2 border-b pb-3 border-zinc-100 dark:border-zinc-800">
        <ClockIcon className="h-4 w-4 text-zinc-500" />
        {hasTimeline ? "事件时间线 (Incident Timeline)" : "关联告警信号时间线 (Signals Timeline)"}
        <span className="ml-auto rounded-full bg-zinc-100 dark:bg-zinc-800 px-2.5 py-0.5 text-xs text-muted-foreground">
          共 {totalEvents} 个事件
        </span>
      </h3>

      {isLoading ? (
        <div className="mt-6 space-y-4 pl-4 ml-2.5">
          {[1, 2, 3].map(i => (
            <div key={i} className="animate-pulse flex gap-3 pl-5">
              <div className="h-7 w-7 rounded-full bg-zinc-100 dark:bg-zinc-800" />
              <div className="flex-1 space-y-2 py-1">
                <div className="h-4 w-3/4 rounded bg-zinc-100 dark:bg-zinc-800" />
                <div className="h-3 w-1/2 rounded bg-zinc-50 dark:bg-zinc-900" />
              </div>
            </div>
          ))}
        </div>
      ) : (
        <div className="mt-6 relative pl-4 border-l-2 border-zinc-200 dark:border-zinc-800 space-y-5 ml-2.5">
          {hasTimeline ? (
            // Unified timeline rendering
            timeline.map((event, idx) => {
              const config = eventTypeConfig[event.type];
              const bgColor = config?.bgColor ?? "bg-rose-50 dark:bg-rose-950/20 border-rose-200 dark:border-rose-800";
              const color = config?.color ?? "text-rose-600 dark:text-rose-400";
              return (
                <div key={`${event.type}-${event.timestamp}-${idx}`} className="relative pl-5">
                  <EventIcon type={event.type} />

                  <div className={`rounded-xl border p-4 ${bgColor}`}>
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <div className="flex items-center gap-2">
                        <Badge variant="outline" className={`text-[9px] px-1.5 rounded py-0 font-medium ${color} border-current/20`}>
                          {event.type === "signal" ? "信号" :
                           event.type === "ai_analysis" ? "AI 解读" :
                           event.type === "diagnosis" ? "Agent 诊断" :
                           event.type === "action" ? "用户操作" : "状态变更"}
                        </Badge>
                        {event.actor && event.actor !== "system" && (
                          <span className="text-[10px] text-zinc-500 font-mono">{event.actor}</span>
                        )}
                      </div>
                      <span className="text-[10px] text-zinc-500 font-medium">
                        {formatDate(event.timestamp, true)}
                      </span>
                    </div>

                    <h4 className="mt-2 text-xs font-semibold text-zinc-800 dark:text-zinc-200 leading-snug">
                      {event.title}
                    </h4>

                    {event.detail && (
                      <p className="mt-1.5 text-[11px] text-zinc-600 dark:text-zinc-400 leading-relaxed line-clamp-3">
                        {event.detail}
                      </p>
                    )}

                    {/* Signal-specific metadata */}
                    {event.type === "signal" && event.metadata && (
                      <>
                        <div className="mt-2 flex items-center gap-3 text-[10px] text-zinc-500">
                          <span>来源: <span className="font-semibold text-zinc-700 dark:text-zinc-400 uppercase">{displayMetadataValue(event.metadata.source)}</span></span>
                          {Boolean(event.metadata.service) && <span>服务: <span className="font-medium">{String(event.metadata.service)}</span></span>}
                          <Badge variant="outline" className={`${getSeverityBadgeStyles(displayMetadataValue(event.metadata.severity, "warning"))} border text-[9px] px-1.5 rounded py-0`}>
                            {displayMetadataValue(event.metadata.severity, "warning")}
                          </Badge>
                        </div>

                        {/* Labels JSON */}
                        {event.metadata.labels_json && typeof event.metadata.labels_json === "object" && Object.keys(event.metadata.labels_json as Record<string, unknown>).length > 0 && (() => {
                          const labelsKey = metadataKey(event.metadata, event.type, event.timestamp);
                          const isExpanded = expandedLabels[labelsKey];
                          const labelCount = Object.keys(event.metadata.labels_json as Record<string, unknown>).length;
                          return (
                          <div className="mt-3 border-t border-zinc-200/40 dark:border-zinc-800/60 pt-3">
                            <div className="flex items-center justify-between mb-2">
                              <span className="text-[9px] font-bold text-zinc-400 uppercase tracking-wider">信号关联属性 (Labels JSON)</span>
                              <button
                                type="button"
                                onClick={() => toggleLabels(labelsKey)}
                                className="flex items-center gap-1 text-[10px] text-zinc-500 hover:text-zinc-700 dark:hover:text-zinc-300 transition-colors cursor-pointer"
                              >
                                <span>{isExpanded ? "收起" : "展开"}</span>
                                <span className="text-[9px] text-zinc-400">({labelCount} 项)</span>
                              </button>
                            </div>
                            {isExpanded && (
                            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5 bg-zinc-100/30 dark:bg-zinc-900/30 p-2.5 rounded-lg border border-zinc-200/40 dark:border-zinc-800/40">
                              {Object.entries(event.metadata.labels_json as Record<string, unknown>).map(([key, val]) => (
                                <div key={key} className="flex flex-col gap-0.5 text-[10px] min-w-0">
                                  <span className="text-zinc-400 font-mono select-none truncate text-[9px] font-semibold">{key}</span>
                                  <span className="text-zinc-700 dark:text-zinc-300 font-mono break-all font-medium leading-relaxed">
                                    {typeof val === "string" ? val : (typeof val === "number" || typeof val === "boolean" || val === null || val === undefined ? String(val) : JSON.stringify(val))}
                                  </span>
                                </div>
                              ))}
                            </div>
                            )}
                          </div>
                          );
                        })()}

                        {/* Raw Payload */}
                        {event.metadata.raw_payload && (
                          <div className="mt-3 pt-2.5 border-t border-dashed border-zinc-200/60 dark:border-zinc-800">
                            <button
                              type="button"
                              onClick={() => togglePayload(metadataKey(event.metadata ?? {}, event.type, event.timestamp))}
                              className="flex items-center gap-1 text-[10px] text-indigo-600 dark:text-indigo-400 font-semibold hover:text-indigo-500 transition-colors cursor-pointer"
                            >
                              {expandedPayloads[metadataKey(event.metadata ?? {}, event.type, event.timestamp)] ? "收起原始告警 Payload (Collapse)" : "查看原始告警 Payload (Expand)"}
                            </button>

                            {expandedPayloads[metadataKey(event.metadata ?? {}, event.type, event.timestamp)] && (
                              <pre className="mt-2 p-3 rounded-lg bg-zinc-950 text-zinc-100 text-[10px] font-mono overflow-x-auto border border-zinc-800/80 shadow-inner select-all leading-normal max-h-60">
                                {typeof event.metadata.raw_payload === "string" ? event.metadata.raw_payload : JSON.stringify(event.metadata.raw_payload, null, 2)}
                              </pre>
                            )}
                          </div>
                        )}
                      </>
                    )}
                  </div>
                </div>
              );
            })
          ) : hasSignals ? (
            // Legacy signal-only rendering
            signals.map((sig, idx) => (
              <div key={sig.id} className="relative pl-5">

                <span className={`absolute -left-[21.5px] top-1.5 flex h-3 w-3 items-center justify-center rounded-full border bg-background ${
                  idx === 0
                    ? "border-primary ring-4 ring-primary/10"
                    : "border-zinc-300 dark:border-zinc-700"
                }`}>
                  <span className={`h-1.5 w-1.5 rounded-full ${idx === 0 ? "bg-primary" : "bg-zinc-300 dark:bg-zinc-700"}`} />
                </span>

                <div className="rounded-xl border border-zinc-100 bg-zinc-50/50 p-4 dark:border-zinc-900 dark:bg-zinc-900/10">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div className="flex items-center gap-2">
                      <Badge variant="outline" className={`${getSeverityBadgeStyles(sig.severity)} border text-[9px] px-1.5 rounded py-0`}>
                        {sig.severity}
                      </Badge>
                      <span className="text-[10px] font-mono text-zinc-400">Fingerprint: {sig.fingerprint.slice(0, 8)}...</span>
                    </div>
                    <span className="text-[10px] text-zinc-500 font-medium">
                      {formatDate(sig.occurred_at ?? "", true)}
                    </span>
                  </div>

                  <h4 className="mt-2 text-xs font-semibold text-zinc-800 dark:text-zinc-200 leading-snug">
                    {sig.title}
                  </h4>

                  <div className="mt-2 flex items-center gap-3 text-[10px] text-zinc-500">
                    <span>告警源: <span className="font-semibold text-zinc-700 dark:text-zinc-400 uppercase">{sig.source}</span></span>
                    {sig.service && <span>服务: <span className="font-medium">{sig.service}</span></span>}
                  </div>

                  {sig.labels_json && Object.keys(sig.labels_json).length > 0 && (() => {
                    const isExpanded = expandedLabels[sig.id];
                    const labelCount = Object.keys(sig.labels_json).length;
                    return (
                    <div className="mt-3 border-t border-zinc-200/40 dark:border-zinc-800/60 pt-3">
                      <div className="flex items-center justify-between mb-2">
                        <span className="text-[9px] font-bold text-zinc-400 uppercase tracking-wider">信号关联属性 (Labels JSON)</span>
                        <button
                          type="button"
                          onClick={() => toggleLabels(sig.id)}
                          className="flex items-center gap-1 text-[10px] text-zinc-500 hover:text-zinc-700 dark:hover:text-zinc-300 transition-colors cursor-pointer"
                        >
                          <span>{isExpanded ? "收起" : "展开"}</span>
                          <span className="text-[9px] text-zinc-400">({labelCount} 项)</span>
                        </button>
                      </div>
                      {isExpanded && (
                      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5 bg-zinc-100/30 dark:bg-zinc-900/30 p-2.5 rounded-lg border border-zinc-200/40 dark:border-zinc-800/40">
                        {Object.entries(sig.labels_json).map(([key, val]) => (
                          <div key={key} className="flex flex-col gap-0.5 text-[10px] min-w-0">
                            <span className="text-zinc-400 font-mono select-none truncate text-[9px] font-semibold">{key}</span>
                            <span className="text-zinc-700 dark:text-zinc-300 font-mono break-all font-medium leading-relaxed">
                              {typeof val === "string" ? val : (typeof val === "number" || typeof val === "boolean" || val === null || val === undefined ? String(val) : JSON.stringify(val))}
                            </span>
                          </div>
                        ))}
                      </div>
                      )}
                    </div>
                    );
                  })()}

                  {sig.raw_payload && (
                    <div className="mt-3 pt-2.5 border-t border-dashed border-zinc-200/60 dark:border-zinc-800">
                      <button
                        type="button"
                        onClick={() => togglePayload(sig.id)}
                        className="flex items-center gap-1 text-[10px] text-indigo-600 dark:text-indigo-400 font-semibold hover:text-indigo-500 transition-colors cursor-pointer"
                      >
                        {expandedPayloads[sig.id] ? "收起原始告警 Payload (Collapse)" : "查看原始告警 Payload (Expand)"}
                      </button>

                      {expandedPayloads[sig.id] && (
                        <pre className="mt-2 p-3 rounded-lg bg-zinc-950 text-zinc-100 text-[10px] font-mono overflow-x-auto border border-zinc-800/80 shadow-inner select-all leading-normal max-h-60">
                          {JSON.stringify(sig.raw_payload, null, 2)}
                        </pre>
                      )}
                    </div>
                  )}
                </div>

              </div>
            ))
          ) : (
            <p className="text-sm text-muted-foreground py-2 pl-2">暂无事件记录。</p>
          )}
        </div>
      )}
    </div>
  );
}
