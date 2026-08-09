"use client";

import {
  SaveIcon,
  DatabaseIcon,
  AlertCircleIcon,
  Loader2Icon,
  ShieldAlertIcon,
  BellIcon,
  MessageSquareIcon,
  HelpCircleIcon,
  ClockIcon,
  VolumeXIcon,
  ExternalLinkIcon,
} from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import {
  useAlertingSettings,
  useUpdateAlertingSettings,
  type NotificationConfig,
} from "@/core/alerting";

const DEFAULT_NOTIFICATION: NotificationConfig = {
  enabled: false,
  channels: [],
  chat_ids: {},
  selected_chat_ids: {},
  severity_threshold: "major",
  on_resolved: true,
  digest: { enabled: false, schedule: "daily", time: "09:00" },
  quiet_hours: { enabled: false, start: "22:00", end: "07:00" },
};

const AVAILABLE_CHANNELS = [
  { key: "feishu", label: "飞书", desc: "字节跳动旗下协同办公平台" },
  { key: "slack", label: "Slack", desc: "全球流行的团队沟通工具" },
  { key: "telegram", label: "Telegram", desc: "高安全性的即时通讯软件" },
];

export function AlertingSettingsTab() {
  const { data: settings, isLoading, error } = useAlertingSettings();
  const { mutate: updateSettings, isPending: isSaving } = useUpdateAlertingSettings();

  const [days, setDays] = useState<string>("");
  const [validationError, setValidationError] = useState<string | null>(null);

  // Notification state
  const [notif, setNotif] = useState<NotificationConfig>(DEFAULT_NOTIFICATION);

  useEffect(() => {
    if (settings) {
      setDays(settings.raw_alert_retention_days.toString());
      
      const config = settings.notification_config && Object.keys(settings.notification_config).length > 0
        ? { ...DEFAULT_NOTIFICATION, ...settings.notification_config }
        : DEFAULT_NOTIFICATION;

      // Populate selected_chat_ids with all configured chat_ids by default if missing
      config.selected_chat_ids ??= {};
      
      const chatIds = config.chat_ids || {};
      AVAILABLE_CHANNELS.forEach((ch) => {
        if (!config.selected_chat_ids![ch.key]) {
          const rawIds = chatIds[ch.key] ?? "";
          config.selected_chat_ids![ch.key] = rawIds
            .split(",")
            .map((id) => id.trim())
            .filter((id) => id !== "");
        }
      });

      setNotif(config);
    }
  }, [settings]);

  const handleInputChange = (val: string) => {
    setDays(val);
    if (!val.trim()) {
      setValidationError("请输入保留天数");
      return;
    }
    const num = parseInt(val, 10);
    if (isNaN(num) || !/^\d+$/.test(val)) {
      setValidationError("请输入有效的整数天数");
      return;
    }
    if (num < 1) {
      setValidationError("最小保留 1 天");
    } else if (num > 365) {
      setValidationError("最大保留 365 天");
    } else {
      setValidationError(null);
    }
  };

  const handleSaveRetention = (e: React.FormEvent) => {
    e.preventDefault();
    if (!days.trim()) {
      setValidationError("请输入保留天数");
      return;
    }
    const num = parseInt(days, 10);
    if (isNaN(num) || num < 1 || num > 365 || !/^\d+$/.test(days)) {
      handleInputChange(days);
      return;
    }
    updateSettings({ raw_alert_retention_days: num, notification_config: notif });
  };

  const handleSaveNotification = (e: React.FormEvent) => {
    e.preventDefault();
    if (!settings) return;
    updateSettings({ raw_alert_retention_days: settings.raw_alert_retention_days, notification_config: notif });
  };

  const toggleChannelSelection = (key: string) => {
    setNotif((prev) => {
      const isSelected = prev.channels.includes(key);
      const channels = isSelected
        ? prev.channels.filter((c) => c !== key)
        : [...prev.channels, key];

      // If enabling channel, select all registered IDs by default
      const selectedChatIds = { ...prev.selected_chat_ids };
      if (!isSelected && selectedChatIds[key]?.length === 0) {
        const rawIds = prev.chat_ids[key] ?? "";
        selectedChatIds[key] = rawIds
          .split(",")
          .map((id) => id.trim())
          .filter((id) => id !== "");
      }

      return { ...prev, channels, selected_chat_ids: selectedChatIds };
    });
  };

  const toggleChatIdSelection = (channelKey: string, chatId: string) => {
    setNotif((prev) => {
      const currentSelected = prev.selected_chat_ids?.[channelKey] ?? [];
      const nextSelected = currentSelected.includes(chatId)
        ? currentSelected.filter((id) => id !== chatId)
        : [...currentSelected, chatId];

      const selectedChatIds = {
        ...prev.selected_chat_ids,
        [channelKey]: nextSelected,
      };

      // Auto-toggle channel status based on whether any chat ID is selected
      let channels = [...prev.channels];
      if (nextSelected.length > 0 && !channels.includes(channelKey)) {
        channels.push(channelKey);
      } else if (nextSelected.length === 0 && channels.includes(channelKey)) {
        channels = channels.filter((c) => c !== channelKey);
      }

      return { ...prev, channels, selected_chat_ids: selectedChatIds };
    });
  };

  if (isLoading) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[400px] rounded-xl border border-zinc-200 dark:border-zinc-800 bg-background/30 p-8">
        <Loader2Icon className="h-10 w-10 animate-spin text-zinc-500" />
        <p className="mt-3 text-sm text-muted-foreground animate-pulse">正在载入系统告警配置...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[400px] rounded-xl border border-dashed border-red-200 dark:border-red-800/50 bg-red-50/5 dark:bg-red-950/5 p-8 text-center">
        <ShieldAlertIcon className="h-12 w-12 text-red-500 animate-bounce" />
        <h3 className="mt-4 text-base font-semibold text-zinc-800 dark:text-zinc-200">配置加载失败</h3>
        <p className="mt-2 text-xs text-muted-foreground max-w-sm">
          {error instanceof Error ? error.message : "未检测到可用的工作空间告警设置，请联系管理员核对。"}
        </p>
      </div>
    );
  }

  const isRetentionValid = days.trim() !== "" && !validationError && !isSaving;
  const isNotificationValid = !isSaving;

  // Extract configured Chat IDs from the global settings (populated via IM Channel Management)
  const configuredChatIds = notif.chat_ids || {};
  const hasConfiguredChannels = AVAILABLE_CHANNELS.some((ch) => configuredChatIds[ch.key]?.trim());

  return (
    <div className="space-y-8">
      {/* CARD 1: DATA RETENTION POLICY */}
      <form onSubmit={handleSaveRetention}>
        <div className="rounded-xl border border-zinc-200 dark:border-zinc-800 bg-background overflow-hidden divide-y divide-zinc-100 dark:divide-zinc-900">
          <div className="p-4 bg-zinc-50/50 dark:bg-zinc-900/20">
            <div className="flex items-center gap-2.5">
              <DatabaseIcon className="h-4 w-4 text-zinc-500" />
              <div>
                <h3 className="text-sm font-semibold text-zinc-900 dark:text-zinc-50">告警历史数据保留策略</h3>
                <p className="text-[11px] mt-0.5 text-muted-foreground">配置系统自动清理冗余原始告警数据与归档周期</p>
              </div>
            </div>
          </div>
          
          <div className="flex flex-col sm:flex-row sm:items-center justify-between p-4 gap-4">
            <div className="flex-1 space-y-1">
              <span className="text-xs font-semibold text-zinc-800 dark:text-zinc-200">原始告警记录保留时间</span>
              <p className="text-[10px] text-zinc-500 leading-normal max-w-xl">
                可配置天数范围为 <strong className="font-medium text-zinc-700 dark:text-zinc-300">1 至 365 天</strong>（默认 30 天）。系统将在每日凌晨根据保留期限自动缩减并重组数据库，避免存储空间溢出。
              </p>
              {validationError && (
                <div className="flex items-center gap-1.5 text-[10px] text-red-500 pt-1">
                  <AlertCircleIcon className="h-3 w-3 shrink-0" />
                  <span>{validationError}</span>
                </div>
              )}
            </div>
            
            <div className="flex items-center gap-3">
              <div className="relative w-28">
                <Input
                  type="text"
                  value={days}
                  onChange={(e) => handleInputChange(e.target.value)}
                  disabled={isSaving}
                  className={`h-8 text-center font-mono text-xs pr-8 focus:ring-2 bg-background ${
                    validationError
                      ? "border-red-500 focus:ring-red-500/20"
                      : "border-zinc-200 dark:border-zinc-800 focus:ring-indigo-500/20"
                  }`}
                  maxLength={3}
                />
                <span className="absolute right-3 top-1/2 -translate-y-1/2 text-[10px] font-semibold text-muted-foreground pointer-events-none">天</span>
              </div>
              <Button type="submit" disabled={!isRetentionValid} className="gap-1.5 h-8 px-3 text-xs">
                {isSaving ? (
                  <Loader2Icon className="h-3.5 w-3.5 animate-spin" />
                ) : (
                  <SaveIcon className="h-3.5 w-3.5" />
                )}
                保存
              </Button>
            </div>
          </div>
        </div>
      </form>

      {/* CARD 2: IM NOTIFICATION INTEGRATION */}
      <div className="rounded-xl border border-zinc-200 dark:border-zinc-800 bg-background overflow-hidden">
        <div className="p-5 border-b border-zinc-100 dark:border-zinc-900 bg-zinc-50/50 dark:bg-zinc-900/20">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2.5">
              <BellIcon className="h-4 w-4 text-zinc-500" />
              <div>
                <h3 className="text-sm font-semibold text-zinc-900 dark:text-zinc-50">全局通知与免打扰设置</h3>
                <p className="text-[11px] mt-0.5 text-muted-foreground">选择接收告警的即时通讯渠道，并配置全局静默期与摘要</p>
              </div>
            </div>
            <div className="flex items-center gap-3">
              <span className="text-[11px] text-muted-foreground">
                {notif.enabled ? "已启用全局推送" : "已暂停全局推送"}
              </span>
              <Switch
                checked={notif.enabled}
                onCheckedChange={(v) => setNotif({ ...notif, enabled: v })}
                disabled={isSaving}
              />
              <Button
                type="submit"
                disabled={!isNotificationValid}
                className="gap-1.5 h-8 px-3 text-xs ml-2"
                onClick={handleSaveNotification}
              >
                {isSaving ? (
                  <Loader2Icon className="h-3.5 w-3.5 animate-spin" />
                ) : (
                  <SaveIcon className="h-3.5 w-3.5" />
                )}
                保存
              </Button>
            </div>
          </div>
        </div>

        <form onSubmit={handleSaveNotification}>
          <div className="p-4 space-y-6">
            {!notif.enabled ? (
              <div className="flex flex-col items-center justify-center py-8 px-4 rounded-xl border border-dashed border-zinc-200 dark:border-zinc-800 bg-zinc-50/10 dark:bg-zinc-900/5 text-center">
                <BellIcon className="h-8 w-8 text-zinc-400 dark:text-zinc-600 animate-pulse mb-3" />
                <h4 className="text-xs font-semibold text-zinc-700 dark:text-zinc-300">IM 告警推送功能已关闭</h4>
                <p className="text-[11px] text-zinc-400 mt-1 max-w-sm">
                  启用上方主开关后，即可配置通知渠道过滤器、降噪日报及免打扰静默期。
                </p>
              </div>
            ) : (
              <div className="space-y-6">
                {/* 1. CHANNEL SELECTION WITH GRANULAR CHAT IDS */}
                <div className="space-y-3">
                  <div className="flex items-center justify-between">
                    <label className="text-xs font-semibold text-zinc-700 dark:text-zinc-300 uppercase tracking-wider">
                      通知推送渠道与群组选择
                    </label>
                    <Link
                      href="/tenant-admin/im"
                      className="text-[11px] text-indigo-600 dark:text-indigo-400 hover:underline flex items-center gap-1 font-semibold transition"
                    >
                      渠道与密钥管理 <ExternalLinkIcon className="h-3 w-3" />
                    </Link>
                  </div>

                  {!hasConfiguredChannels ? (
                    <div className="flex flex-col items-center justify-center p-6 rounded-xl border border-amber-100 dark:border-amber-900/30 bg-amber-50/5 dark:bg-amber-950/5 text-center">
                      <AlertCircleIcon className="h-6 w-6 text-amber-500 mb-2" />
                      <h4 className="text-xs font-semibold text-amber-800 dark:text-amber-300">未检测到已配置的通知渠道</h4>
                      <p className="text-[10px] text-zinc-400 mt-1 max-w-md">
                        目前您尚未在系统“渠道管理”页面配置任何接收端 Chat ID 密钥。告警推送将处于挂起状态。
                      </p>
                      <Link href="/tenant-admin/im" className="mt-3">
                        <Button type="button" variant="outline" size="sm" className="h-8 text-xs font-semibold border-amber-200 text-amber-850 hover:bg-amber-50 dark:border-amber-900/50 dark:text-amber-400">
                          立即前往配置渠道群聊 ↗
                        </Button>
                      </Link>
                    </div>
                  ) : (
                    <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                      {AVAILABLE_CHANNELS.map((ch) => {
                        const chatIdVal = configuredChatIds[ch.key]?.trim() ?? "";
                        const isConfigured = chatIdVal !== "";
                        const isChannelSelected = notif.channels.includes(ch.key) && isConfigured;

                        // Parse individual Chat IDs configured for this channel
                        const chatIdsList = chatIdVal
                          .split(",")
                          .map((id) => id.trim())
                          .filter((id) => id !== "");

                        return (
                          <div
                            key={ch.key}
                            className={`relative rounded-xl border transition-all duration-300 flex flex-col justify-between overflow-hidden ${
                              !isConfigured
                                ? "bg-zinc-50/50 border-zinc-150 dark:bg-zinc-900/10 dark:border-zinc-850 opacity-60 min-h-[120px]"
                                : isChannelSelected
                                ? "bg-indigo-50/10 border-indigo-200/60 dark:bg-indigo-950/5 dark:border-indigo-900/40 shadow-sm"
                                : "bg-background/40 border-zinc-200 dark:border-zinc-800 hover:border-zinc-300 min-h-[120px]"
                            }`}
                          >
                            {/* Card Header */}
                            <div className="p-4 pb-3 flex items-start justify-between gap-2 border-b border-zinc-100 dark:border-zinc-900 bg-zinc-50/30 dark:bg-zinc-900/10">
                              <div className="flex items-center gap-2.5 min-w-0">
                                <MessageSquareIcon className={`h-4.5 w-4.5 shrink-0 ${
                                  isChannelSelected ? "text-indigo-500" : "text-zinc-400"
                                }`} />
                                <div className="min-w-0">
                                  <h4 className="text-xs font-bold text-zinc-850 dark:text-zinc-250 truncate">
                                    {ch.label}
                                  </h4>
                                  <p className="text-[9px] text-zinc-400 mt-0.5">
                                    {isConfigured ? `已配置 ${chatIdsList.length} 个群组` : "未配置 Chat ID"}
                                  </p>
                                </div>
                              </div>

                              <Switch
                                checked={isChannelSelected}
                                onCheckedChange={() => toggleChannelSelection(ch.key)}
                                disabled={!isConfigured || isSaving}
                                className="scale-85 shrink-0"
                              />
                            </div>

                            {/* Card Content: Granular Chat ID Selection List */}
                            <div className="p-3.5 flex-1 flex flex-col justify-center space-y-2 bg-background/25">
                              {!isConfigured ? (
                                <div className="flex items-center justify-between text-[10px] py-1.5">
                                  <span className="text-zinc-400">渠道不可用</span>
                                  <Link
                                    href="/tenant-admin/im"
                                    className="text-indigo-600 dark:text-indigo-400 hover:underline font-semibold"
                                  >
                                    前往配置 ↗
                                  </Link>
                                </div>
                              ) : isChannelSelected ? (
                                <div className="space-y-2">
                                  <span className="text-[9px] font-bold text-zinc-450 uppercase tracking-wider block">
                                    分发接收目标选择
                                  </span>
                                  <div className="max-h-24 overflow-y-auto space-y-1.5 pr-1">
                                    {chatIdsList.map((cid) => {
                                      const isCidChecked = notif.selected_chat_ids?.[ch.key]?.includes(cid) ?? false;

                                      return (
                                        <label
                                          key={cid}
                                          className={`flex items-center justify-between gap-2 p-1.5 rounded-lg border text-[10px] cursor-pointer transition-colors ${
                                            isCidChecked
                                              ? "bg-indigo-50/40 border-indigo-200/50 text-indigo-950 dark:bg-indigo-950/20 dark:border-indigo-900/50 dark:text-indigo-350"
                                              : "bg-background/80 border-zinc-200 dark:border-zinc-800 text-zinc-550 dark:text-zinc-400 hover:border-zinc-250"
                                          }`}
                                        >
                                          <span className="font-mono truncate flex-1 pr-1">{cid}</span>
                                          <Switch
                                            checked={isCidChecked}
                                            onCheckedChange={() => toggleChatIdSelection(ch.key, cid)}
                                            disabled={isSaving}
                                            className="scale-75 shrink-0"
                                          />
                                        </label>
                                      );
                                    })}
                                  </div>
                                </div>
                              ) : (
                                <div className="text-[10px] text-zinc-400 text-center py-2">
                                  请开启上方开关，激活群聊选择
                                </div>
                              )}
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  )}
                </div>

                {/* 2. POLICY FILTER AND NOISE CONTROL (UNIFIED LIST VIEW) */}
                <div className="rounded-xl border border-zinc-200 dark:border-zinc-800 bg-background overflow-hidden divide-y divide-zinc-100 dark:divide-zinc-900">
                  
                  {/* Severity Threshold */}
                  <div className="flex flex-col sm:flex-row sm:items-center justify-between p-4 gap-4">
                    <div className="space-y-0.5">
                      <span className="text-xs font-semibold text-zinc-800 dark:text-zinc-200">推送级别过滤门槛</span>
                      <p className="text-[10px] text-zinc-400">选择触发推送的最低告警级别</p>
                    </div>
                    <div className="sm:w-64">
                      <select
                        value={notif.severity_threshold}
                        onChange={(e) =>
                          setNotif({
                            ...notif,
                            severity_threshold: e.target.value as NotificationConfig["severity_threshold"],
                          })
                        }
                        disabled={isSaving}
                        className="w-full h-8 px-2 text-xs rounded-md border border-zinc-200 dark:border-zinc-800 bg-background outline-none font-medium text-zinc-800 dark:text-zinc-200 focus:ring-2 focus:ring-indigo-500/20"
                      >
                        <option value="critical">🔴 仅 Critical（仅阻断性核心告警）</option>
                        <option value="major">🟠 Critical + Major（推荐）</option>
                        <option value="warning">🟡 全部级别推送（Warning及以上）</option>
                      </select>
                    </div>
                  </div>

                  {/* Resolution Push Toggle */}
                  <div className="flex flex-col sm:flex-row sm:items-center justify-between p-4 gap-4">
                    <div className="space-y-0.5">
                      <span className="text-xs font-semibold text-zinc-800 dark:text-zinc-200">故障恢复时推送通知</span>
                      <p className="text-[10px] text-zinc-400">当告警状态变为 resolved 时，秒级推送绿色标记卡片</p>
                    </div>
                    <Switch
                      checked={notif.on_resolved}
                      onCheckedChange={(v) => setNotif({ ...notif, on_resolved: v })}
                      disabled={isSaving}
                    />
                  </div>

                  {/* Quiet Hours */}
                  <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between p-4 gap-4">
                    <div className="flex-1 space-y-1">
                      <div className="flex items-center gap-1.5">
                        <VolumeXIcon className="h-3.5 w-3.5 text-zinc-500" />
                        <span className="text-xs font-semibold text-zinc-800 dark:text-zinc-200">夜间静默（Quiet Hours）</span>
                      </div>
                      <p className="text-[10px] text-zinc-500 leading-normal max-w-lg">
                        在设定的时间范围内静默推送通知。<span className="text-rose-500 font-semibold">Critical 级别的灾难告警将不受限制，依然强行推送。</span>
                      </p>
                      {notif.quiet_hours?.enabled && (
                        <div className="flex items-center gap-2.5 pt-2 animate-fadeIn">
                          <Input
                            type="time"
                            value={notif.quiet_hours?.start || "22:00"}
                            onChange={(e) =>
                              setNotif({
                                ...notif,
                                quiet_hours: { ...notif.quiet_hours!, start: e.target.value },
                              })
                            }
                            disabled={isSaving}
                            className="h-8 text-xs text-center font-mono w-28 bg-background"
                          />
                          <span className="text-[11px] text-zinc-400">至</span>
                          <Input
                            type="time"
                            value={notif.quiet_hours?.end || "07:00"}
                            onChange={(e) =>
                              setNotif({
                                ...notif,
                                quiet_hours: { ...notif.quiet_hours!, end: e.target.value },
                              })
                            }
                            disabled={isSaving}
                            className="h-8 text-xs text-center font-mono w-28 bg-background"
                          />
                        </div>
                      )}
                    </div>
                    <div className="pt-1">
                      <Switch
                        checked={notif.quiet_hours?.enabled ?? false}
                        onCheckedChange={(v) =>
                          setNotif({
                            ...notif,
                            quiet_hours: { ...notif.quiet_hours!, enabled: v },
                          })
                        }
                        disabled={isSaving}
                      />
                    </div>
                  </div>

                  {/* Daily Digests */}
                  <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between p-4 gap-4">
                    <div className="flex-1 space-y-1">
                      <div className="flex items-center gap-1.5">
                        <ClockIcon className="h-3.5 w-3.5 text-zinc-500" />
                        <span className="text-xs font-semibold text-zinc-800 dark:text-zinc-200">降噪日报（Daily Digests）</span>
                      </div>
                      <p className="text-[10px] text-zinc-500 leading-normal max-w-lg">
                        每天定时向指定的通道群组推送降噪健康汇总卡片，包含今日新建告警总数、恢复比例及当前活跃事件。
                      </p>
                      {notif.digest?.enabled && (
                        <div className="flex items-center gap-2.5 pt-2 animate-fadeIn">
                          <select
                            value={notif.digest?.schedule || "daily"}
                            onChange={(e) =>
                              setNotif({
                                ...notif,
                                digest: {
                                  ...notif.digest!,
                                  schedule: e.target.value as "daily" | "weekly",
                                },
                              })
                            }
                            disabled={isSaving}
                            className="h-8 px-2 text-xs rounded-md border border-zinc-200 dark:border-zinc-800 bg-background outline-none"
                          >
                            <option value="daily">每日汇总</option>
                            <option value="weekly">每周汇总</option>
                          </select>
                          <Input
                            type="time"
                            value={notif.digest?.time || "09:00"}
                            onChange={(e) =>
                              setNotif({
                                ...notif,
                                digest: { ...notif.digest!, time: e.target.value },
                              })
                            }
                            disabled={isSaving}
                            className="h-8 text-xs text-center font-mono w-28 bg-background"
                          />
                        </div>
                      )}
                    </div>
                    <div className="pt-1">
                      <Switch
                        checked={notif.digest?.enabled ?? false}
                        onCheckedChange={(v) =>
                          setNotif({
                            ...notif,
                            digest: { ...notif.digest!, enabled: v },
                          })
                        }
                        disabled={isSaving}
                      />
                    </div>
                  </div>
                </div>
              </div>
            )}
          </div>
        </form>
      </div>
    </div>
  );
}
