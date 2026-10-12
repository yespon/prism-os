"use client";

import { useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import {
  installSourceSkill,
  type ResourcePreflightItem,
} from "@/core/agents/catalog";
import { useSkillImportContext } from "@/core/skills/import-context";
import { SkillImportError, type SkillImportScope } from "@/core/skills/imports";

export function SourceSkillInstall({
  templateId,
  resource,
  locale,
  open,
  onInstalled,
}: {
  templateId: string;
  resource: ResourcePreflightItem;
  locale: "zh" | "en";
  open: boolean;
  onInstalled: () => void;
}) {
  const context = useSkillImportContext();
  const client = useQueryClient();
  const zh = locale === "zh";
  const key = JSON.stringify([
    context.key,
    templateId,
    resource.id,
    resource.bundle_sha256,
    locale,
    open,
  ]);
  const live = useRef(key);
  live.current = key;
  const request = useRef<AbortController | null>(null);
  const busy = useRef(false);
  const [confirm, setConfirm] = useState<string | null>(null);
  const [scope, setScope] = useState<SkillImportScope>("personal");
  const [working, setWorking] = useState(false);
  const [result, setResult] = useState<{
    key: string;
    kind: "success" | "conflict" | "denied" | "unknown";
    operationId?: string;
  } | null>(null);
  useEffect(() => {
    request.current?.abort();
    busy.current = false;
    setConfirm(null);
    setScope("personal");
    setWorking(false);
    setResult(null);
    return () => request.current?.abort();
  }, [key]);
  async function install() {
    if (
      confirm !== key ||
      busy.current ||
      !context.isCurrent() ||
      !context.identityReady ||
      (scope === "tenant" && !context.canShare)
    )
      return;
    const controller = new AbortController();
    request.current = controller;
    busy.current = true;
    setWorking(true);
    setConfirm(null);
    setResult(null);
    const valid = () =>
      !controller.signal.aborted && live.current === key && context.isCurrent();
    try {
      const response = await installSourceSkill(
        templateId,
        resource.id,
        locale,
        scope,
        resource.bundle_sha256,
        controller.signal,
      );
      if (!valid()) return;
      setResult({ key, kind: "success", operationId: response.operation_id });
      for (const queryKey of [
        ["skills"],
        ["availableSkills"],
        ["tenantSkills"],
      ])
        void client.invalidateQueries({ queryKey });
      onInstalled();
    } catch (error) {
      if (!valid()) return;
      const kind =
        error instanceof SkillImportError && (error.status === 401 || error.status === 403)
          ? "denied"
          : error instanceof SkillImportError &&
              error.status === 409 &&
              !error.operationId
            ? "conflict"
            : "unknown";
      setResult({
        key,
        kind,
        operationId:
          error instanceof SkillImportError ? error.operationId : undefined,
      });
    } finally {
      if (valid()) {
        busy.current = false;
        setWorking(false);
      }
    }
  }
  const visible = result?.key === key ? result : null;
  const messages = {
    success: [
      "已登记 Skill；未自动绑定 Agent，执行权限与依赖仍待确认。",
      "Skill registered. Agent bindings, dependencies and execution rights still need verification.",
    ],
    conflict: [
      "来源已改变或存在同名资源；已有内容保留。请重新检查资源。",
      "Source changed or a same-name resource exists. Existing contents were preserved; check resources again.",
    ],
    denied: [
      "当前权限不允许此安装。请核对当前租户角色。",
      "Current permissions deny this installation. Check the current tenant role.",
    ],
    unknown: [
      "导入结果暂无法确认。先在 Skill 管理检查导入记录，避免重复导入。",
      "Import outcome is uncertain. Inspect import records in Skill management before importing again.",
    ],
  };
  if (!open) return null;
  return (
    <div className="space-y-2">
      <Button
        type="button"
        variant="outline"
        size="sm"
        disabled={
          working || !context.identityReady || visible?.kind === "unknown"
        }
        onClick={() => {
          setConfirm(key);
          setResult(null);
        }}
      >
        {zh ? "安装 Skill…" : "Install Skill…"}
      </Button>
      {working && (
        <p role="status">
          {zh
            ? "正在导入；中止页面请求不代表服务器回滚。"
            : "Importing; aborting a page request does not prove server rollback."}
        </p>
      )}
      {confirm === key && (
        <div
          role="group"
          aria-label={zh ? "确认 Skill 安装" : "Confirm Skill installation"}
          className="rounded border p-2"
        >
          <p>
            {zh
              ? `将 ${resource.host_adaptation?.name ?? resource.root} 导入到当前租户的个人或共享 Skill。不会自动绑定 Agent 或授予执行权限。`
              : `Import ${resource.host_adaptation?.name ?? resource.root} into personal or shared Skills in the current tenant. Agent bindings and execution rights are not granted automatically.`}
          </p>
          <label>
            {zh ? "安装范围" : "Installation scope"}
            <select
              aria-label={zh ? "安装范围" : "Installation scope"}
              value={scope}
              onChange={(event) =>
                setScope(event.target.value as SkillImportScope)
              }
            >
              <option value="personal">
                {zh ? "个人 Skill" : "Personal Skill"}
              </option>
              {context.canShare && (
                <option value="tenant">
                  {zh ? "租户共享 Skill" : "Tenant shared Skill"}
                </option>
              )}
            </select>
          </label>
          <Button type="button" size="sm" onClick={() => void install()}>
            {zh ? "确认安装" : "Confirm installation"}
          </Button>
          <Button
            type="button"
            size="sm"
            variant="ghost"
            onClick={() => setConfirm(null)}
          >
            {zh ? "返回" : "Back"}
          </Button>
        </div>
      )}
      {visible && (
        <p role="status">
          {messages[visible.kind][zh ? 0 : 1]}
          {visible.operationId && (
            <span className="break-all"> {visible.operationId}</span>
          )}
        </p>
      )}
      {visible && (
        <Link
          className="underline"
          href={
            scope === "tenant"
              ? "/tenant-admin/skills?imports=1"
              : "/workspace/skills?imports=1"
          }
        >
          {zh ? "检查导入记录" : "Inspect import records"}
        </Link>
      )}
    </div>
  );
}
