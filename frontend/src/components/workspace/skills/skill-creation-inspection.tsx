"use client";

import type { SkillImportScope } from "@/core/skills/imports";

import { SkillImportOperations } from "./skill-import-operations";

export function SkillCreationInspection({scope, operationId, locale = "zh"}: {scope: SkillImportScope; operationId?: string; locale?: "zh" | "en"}) {
  const zh = locale === "zh";
  return <section role="alert" className="space-y-2 rounded border p-3 text-sm">
    <p>{zh ? "创建结果需要核对，请勿重复提交。恢复登记后的新资源保持禁用；请检查配置后再启用。" : "Inspect the creation outcome before submitting again. Newly recovered resources remain disabled; inspect configuration before enabling."}</p>
    {operationId && <p className="break-all text-xs">{operationId}</p>}
    <SkillImportOperations scope={scope} locale={locale} creation />
    <a className="underline" href={`/workspace/skills?filter=${scope}`}>{zh ? "查看当前资源列表" : "Inspect current resources"}</a>
  </section>;
}
