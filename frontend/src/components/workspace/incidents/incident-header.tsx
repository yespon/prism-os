"use client";

import {
  ArrowRightIcon,
  CheckCircle2Icon,
  ClockIcon,
  DownloadIcon,
  ExternalLinkIcon,
  RefreshCwIcon,
  SparklesIcon,
  TagIcon,
  TerminalIcon,
  UserIcon,
  UserPlusIcon,
  VolumeXIcon,
  TicketIcon,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { formatDate, getSeverityBadgeStyles } from "@/core/alerting";
import type { IncidentDetail } from "@/core/alerting/types";

interface IncidentHeaderProps {
  incident: IncidentDetail;
  onSuppress: () => void;
  onUnsuppress: () => void;
  onOpenDiagnosis: () => void;
  onExportReport: () => void;
  onClaim: () => void;
  onResolve: () => void;
  onCreateTicket: () => void;
  onGoToTerminal: () => void;
  suppressing: boolean;
  unsuppressing: boolean;
  diagnosing: boolean;
  claiming: boolean;
  resolving: boolean;
  creatingTicket: boolean;
  currentThreadId: string | null | undefined;
}

export function IncidentHeader({
  incident,
  onSuppress,
  onUnsuppress,
  onOpenDiagnosis,
  onExportReport,
  onClaim,
  onResolve,
  onCreateTicket,
  onGoToTerminal,
  suppressing,
  unsuppressing,
  diagnosing,
  claiming,
  resolving,
  creatingTicket,
  currentThreadId,
}: IncidentHeaderProps) {
  return (
    <div className="overflow-hidden rounded-2xl border border-zinc-200/80 bg-background p-6 shadow-sm dark:border-zinc-800/80">
      <div className="flex flex-col gap-5 md:flex-row md:items-start md:justify-between">

        <div className="flex-1 min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-mono text-xs font-semibold text-zinc-500 tracking-wider">
              {incident.incident_key}
            </span>

            <Badge variant="outline" className={`${getSeverityBadgeStyles(incident.severity)} border font-medium px-2 py-0.5 rounded text-[10px] uppercase`}>
              {incident.severity}
            </Badge>

            {incident.environment && (
              <Badge variant="secondary" className="px-2 py-0.5 rounded text-[10px] bg-zinc-100 dark:bg-zinc-800 dark:text-zinc-300">
                {incident.environment}
              </Badge>
            )}

            {incident.status === "firing" ? (
              <span className="inline-flex items-center gap-1.5 rounded-full bg-rose-50 px-2.5 py-0.5 text-xs font-medium text-rose-700 dark:bg-rose-950/20 dark:text-rose-400">
                <span className="h-1.5 w-1.5 rounded-full bg-rose-500 animate-pulse" />
                发生中
              </span>
            ) : incident.status === "resolved" ? (
              <span className="inline-flex items-center gap-1.5 rounded-full bg-emerald-50 px-2.5 py-0.5 text-xs font-medium text-emerald-700 dark:bg-emerald-950/20 dark:text-emerald-400">
                <CheckCircle2Icon className="h-3.5 w-3.5" />
                已恢复
              </span>
            ) : (
              <span className="inline-flex items-center gap-1.5 rounded-full bg-zinc-100 px-2.5 py-0.5 text-xs font-medium text-zinc-600 dark:bg-zinc-900 dark:text-zinc-400">
                <VolumeXIcon className="h-3.5 w-3.5" />
                已静默
              </span>
            )}

            {incident.owner_user_id && (
              <span className="inline-flex items-center gap-1 rounded-full bg-indigo-50 px-2.5 py-0.5 text-xs font-medium text-indigo-700 dark:bg-indigo-950/20 dark:text-indigo-400">
                <UserIcon className="h-3 w-3" />
                {incident.owner_user_id}
              </span>
            )}

            {incident.ticket_id && incident.ticket_url && (
              <a
                href={incident.ticket_url}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1 rounded-full bg-sky-50 px-2.5 py-0.5 text-xs font-medium text-sky-700 hover:text-sky-800 dark:bg-sky-950/20 dark:text-sky-400 dark:hover:text-sky-300 transition-colors"
              >
                <TicketIcon className="h-3 w-3" />
                工单: {incident.ticket_id}
                <ExternalLinkIcon className="h-3 w-3" />
              </a>
            )}
          </div>

          <h2 className="mt-3 text-lg font-bold tracking-tight text-zinc-900 dark:text-zinc-50 leading-snug">
            {incident.title ?? "未命名告警事件"}
          </h2>

          <div className="mt-3 flex flex-wrap items-center gap-x-6 gap-y-2 text-xs text-muted-foreground">
            {incident.service && (
              <span className="flex items-center gap-1.5">
                <TagIcon className="h-3.5 w-3.5" />
                服务: <span className="font-semibold text-zinc-700 dark:text-zinc-300">{incident.service}</span>
              </span>
            )}

            <span className="flex items-center gap-1.5">
              <ClockIcon className="h-3.5 w-3.5" />
              首次检测: {formatDate(incident.first_seen_at, true)}
            </span>

            <span className="flex items-center gap-1.5">
              <ClockIcon className="h-3.5 w-3.5" />
              最近发生: {formatDate(incident.last_seen_at, true)}
            </span>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2 shrink-0 border-t border-zinc-100 pt-4 md:border-none md:pt-0">
          {incident.status === "firing" && !incident.owner_user_id && (
            <Button
              variant="outline"
              size="sm"
              className="gap-1.5 h-9 border-indigo-300 dark:border-indigo-800 bg-indigo-50/50 hover:bg-indigo-100 dark:bg-indigo-950/20 dark:hover:bg-indigo-950/40 text-indigo-700 dark:text-indigo-400"
              onClick={onClaim}
              disabled={claiming}
            >
              <UserPlusIcon className="h-3.5 w-3.5" />
              {claiming ? "认领中..." : "认领"}
            </Button>
          )}

          {incident.status === "firing" && (
            <Button
              variant="outline"
              size="sm"
              className="gap-1.5 h-9"
              onClick={onSuppress}
              disabled={suppressing}
            >
              <VolumeXIcon className="h-3.5 w-3.5 text-zinc-500" />
              标记误报 (Suppress)
            </Button>
          )}

          {incident.status === "suppressed" && (
            <Button
              variant="outline"
              size="sm"
              className="gap-1.5 h-9 border-amber-300 dark:border-amber-900 bg-amber-500/10 hover:bg-amber-500/20 text-amber-800 dark:text-amber-300"
              onClick={onUnsuppress}
              disabled={unsuppressing}
            >
              <RefreshCwIcon className="h-3.5 w-3.5 text-amber-600 dark:text-amber-400" />
              撤销误报 (Revert Suppression)
            </Button>
          )}

          {incident.status !== "resolved" && (
            <Button
              variant="outline"
              size="sm"
              className="gap-1.5 h-9 border-emerald-300 dark:border-emerald-800 bg-emerald-50/50 hover:bg-emerald-100 dark:bg-emerald-950/20 dark:hover:bg-emerald-950/40 text-emerald-700 dark:text-emerald-400"
              onClick={onResolve}
              disabled={resolving}
            >
              <CheckCircle2Icon className="h-3.5 w-3.5" />
              {resolving ? "恢复中..." : "标记已恢复"}
            </Button>
          )}

          {incident.status === "firing" && (
            <Button
              size="sm"
              className="gap-1.5 h-9 bg-primary text-primary-foreground font-medium hover:bg-primary/95 transition shadow-sm"
              onClick={onOpenDiagnosis}
            >
              <SparklesIcon className="h-3.5 w-3.5" />
              {diagnosing || incident.diagnosis_status === "running"
                ? "诊断中..."
                : currentThreadId || incident.diagnosis_status === "completed"
                  ? "查看诊断过程"
                  : "开始深度诊断"}
              <ArrowRightIcon className="h-3.5 w-3.5" />
            </Button>
          )}

          {!incident.ticket_id && (
            <Button
              variant="outline"
              size="sm"
              className="gap-1.5 h-9 border-sky-300 dark:border-sky-800 bg-sky-50/50 hover:bg-sky-100 dark:bg-sky-950/20 dark:hover:bg-sky-950/40 text-sky-700 dark:text-sky-400"
              onClick={onCreateTicket}
              disabled={creatingTicket}
            >
              <TicketIcon className="h-3.5 w-3.5" />
              {creatingTicket ? "创建中..." : "创建工单"}
            </Button>
          )}

          <Button
            variant="outline"
            size="sm"
            className="gap-1.5 h-9"
            onClick={onExportReport}
          >
            <DownloadIcon className="h-3.5 w-3.5" />
            导出诊断报告
          </Button>

          {incident.status === "firing" && (incident.ai_summary ?? incident.ai_suggestion) && (
            <Button
              size="sm"
              className="gap-1.5 h-9 bg-emerald-600 hover:bg-emerald-500 text-white font-medium shadow-sm shadow-emerald-500/20"
              onClick={onGoToTerminal}
            >
              <TerminalIcon className="h-3.5 w-3.5" />
              到终端排查
            </Button>
          )}
        </div>

      </div>
    </div>
  );
}
