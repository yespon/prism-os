"use client";

import { ShieldAlertIcon, CableIcon, SlidersIcon, SettingsIcon, ActivityIcon } from "lucide-react";

import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { EscalationRulesPanel } from "@/components/workspace/incidents/escalation-rules-panel";

import { AlertRulesTab } from "./alert-rules-tab";
import { AlertSourcesTab } from "./alert-sources-tab";
import { AlertingSettingsTab } from "./alerting-settings-tab";

export function TenantAdminAlertsPage() {
  return (
    <div className="space-y-6">
      {/* 顶层主 Header */}
      <div>
        <h1 className="flex items-center gap-2.5 text-xl font-bold tracking-tight text-zinc-900 dark:text-zinc-50">
          <ShieldAlertIcon className="h-6 w-6 text-zinc-800 dark:text-zinc-200" />
          智能告警与治理规则
        </h1>
        <p className="mt-1 text-sm text-muted-foreground">
          配置并维护工作空间的第三方告警源 Webhook 接入，并配置实时智能治理规则对异常信号流执行去重、聚合与标记静默。
        </p>
      </div>

      {/* 标签页导航 */}
      <Tabs defaultValue="sources" className="w-full">
        <TabsList className="grid w-fit grid-cols-3 mb-6 h-10 p-1 bg-zinc-100 dark:bg-zinc-900 rounded-lg">
          <TabsTrigger value="sources" className="flex items-center gap-1.5 px-4 text-xs font-semibold">
            <CableIcon className="h-3.5 w-3.5" />
            接入源与映射
          </TabsTrigger>
          <TabsTrigger value="rules" className="flex items-center gap-1.5 px-4 text-xs font-semibold">
            <SlidersIcon className="h-3.5 w-3.5" />
            治理与升级规则
          </TabsTrigger>
          <TabsTrigger value="settings" className="flex items-center gap-1.5 px-4 text-xs font-semibold">
            <SettingsIcon className="h-3.5 w-3.5" />
            全局设置
          </TabsTrigger>
        </TabsList>

        <TabsContent value="sources" className="space-y-4 focus-visible:outline-none">
          <AlertSourcesTab />
        </TabsContent>

        <TabsContent value="rules" className="space-y-8 focus-visible:outline-none">
          <AlertRulesTab />
          <EscalationRulesPanel />
        </TabsContent>

        <TabsContent value="settings" className="space-y-4 focus-visible:outline-none">
          <AlertingSettingsTab />
        </TabsContent>
      </Tabs>
    </div>
  );
}
