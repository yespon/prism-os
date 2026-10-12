"use client";

import { useEffect, useRef, useState } from "react";
import { SourceSkillInstall } from "../skills/source-skill-install";
import { useSkillImportContext } from "@/core/skills/import-context";
import { Button } from "@/components/ui/button";
import { useTenantKey } from "@/core/agents/hooks";
import { getCurrentTenantId } from "@/core/tenants/store";
import {
  downloadResourceArchive,
  loadResourcePreflight,
  type ResourcePreflight,
  type ResourcePreflightItem,
} from "@/core/agents/catalog";

const labels: Record<string, [string, string]> = {
  source_match: ["内容与来源一致", "Contents match source"],
  modified: ["同名内容有差异", "Same name, different contents"],
  files_missing: ["记录存在，文件缺失", "Recorded, files missing"],
  location_unverified: ["位置无法核对", "Location unverified"],
  multiple_visible_records: [
    "存在多个可见同名记录",
    "Multiple visible records",
  ],
  not_installed: ["未发现可见安装", "No visible installation"],
  disabled: ["已禁用", "Disabled"],
  binding_required: ["待绑定", "Binding required"],
  format_blocked: ["格式待处理", "Format blocked"],
};

export function AgentResourcePreflight({
  open,
  templateId,
  locale,
}: {
  open: boolean;
  templateId: string;
  locale: "zh" | "en";
}) {
  const tenant = useTenantKey();
  const identity = useSkillImportContext();
  const zh = locale === "zh";
  const [data, setData] = useState<{
    scope: string;
    value: ResourcePreflight;
  } | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [downloading, setDownloading] = useState("");
  const scope = JSON.stringify([
    open,
    tenant,
    identity.key,
    templateId,
    locale,
  ]);
  const live = useRef(scope);
  live.current = scope;
  const generation = useRef(0);
  const request = useRef<AbortController | null>(null);
  const download = useRef<AbortController | null>(null);
  useEffect(() => {
    request.current?.abort();
    download.current?.abort();
    ++generation.current;
    setData(null);
    setError("");
    setLoading(false);
    setDownloading("");
    return () => {
      request.current?.abort();
      download.current?.abort();
      ++generation.current;
    };
  }, [scope]);
  const isCurrent = (signal: AbortSignal, current: number) =>
    identity.isCurrent() &&
    !signal.aborted &&
    generation.current === current &&
    live.current === scope &&
    tenant === (getCurrentTenantId() ?? "_");

  async function inspect(preserve = false) {
    if (!identity.identityReady || !identity.isCurrent()) return;
    request.current?.abort();
    download.current?.abort();
    setDownloading("");
    const controller = new AbortController();
    request.current = controller;
    const current = ++generation.current;
    setLoading(true);
    if (!preserve) setData(null);
    setError("");
    try {
      const result = await loadResourcePreflight(
        templateId,
        locale,
        controller.signal,
      );
      if (isCurrent(controller.signal, current))
        setData({ scope, value: result });
    } catch {
      if (isCurrent(controller.signal, current))
        setError(
          zh
            ? "资源预检失败，请重试。"
            : "Resource checks unavailable. Please retry.",
        );
    } finally {
      if (isCurrent(controller.signal, current)) setLoading(false);
    }
  }
  async function saveArchive(resource: ResourcePreflightItem) {
    download.current?.abort();
    const controller = new AbortController();
    download.current = controller;
    const current = generation.current;
    setDownloading(resource.id);
    setError("");
    try {
      const blob = await downloadResourceArchive(
        templateId,
        resource.id,
        locale,
        controller.signal,
      );
      if (!isCurrent(controller.signal, current)) return;
      const url = URL.createObjectURL(blob);
      try {
        const link = document.createElement("a");
        link.href = url;
        link.download = `${resource.host_adaptation?.name ?? "skill"}.zip`;
        document.body.appendChild(link);
        link.click();
        link.remove();
      } finally {
        URL.revokeObjectURL(url);
      }
    } catch {
      if (isCurrent(controller.signal, current))
        setError(
          zh
            ? "源包下载失败，请重试。"
            : "Source package download failed. Please retry.",
        );
    } finally {
      if (isCurrent(controller.signal, current)) setDownloading("");
    }
  }
  const visible = data?.scope === scope ? data.value : null;
  if (!open || !templateId) return null;
  return (
    <section
      className="space-y-2 rounded border p-2 text-xs"
      aria-label={zh ? "配套资源预检" : "Companion resource checks"}
    >
      <Button
        type="button"
        variant="outline"
        size="sm"
        disabled={loading || !identity.identityReady}
        onClick={() => void inspect()}
      >
        {loading
          ? zh
            ? "正在核对资源…"
            : "Checking resources…"
          : zh
            ? "检查配套资源"
            : "Check companion resources"}
      </Button>
      {error && (
        <p role="alert" className="text-destructive">
          {error}
        </p>
      )}
      {visible && (
        <>
          <p>
            {zh
              ? `完整配套文件 ${visible.member_count} 项，其中补充文件 ${visible.additional_member_count} 项。`
              : `${visible.member_count} companion files, including ${visible.additional_member_count} additional files.`}
          </p>
          <p className="text-muted-foreground">
            {zh
              ? "安装核对仅表示可见记录和内容；依赖、绑定和执行权限仍需确认。下载源包可在 Skill 管理中手动导入，不会自动安装。"
              : "Installation checks describe visible records and contents. Dependencies, bindings and execution rights still need verification. Source packages can be manually imported in Skill management."}
          </p>
          <details>
            <summary>{zh ? "来源摘要" : "Source identity"}</summary>
            <p className="break-all">{visible.revision}</p>
            <p className="break-all">{visible.declaration_sha256}</p>
          </details>
          {!!visible.excluded_resources.length && (
            <p>
              {zh ? "待独立实现：" : "Independent implementation pending: "}
              {visible.excluded_resources.join(", ")}
            </p>
          )}
          <ul className="max-h-64 space-y-2 overflow-auto">
            {visible.resources.map((resource) => (
              <li key={resource.id} className="rounded border p-2">
                <p className="font-medium break-all">
                  {resource.root} · {resource.members.length}{" "}
                  {zh ? "文件" : "files"}
                </p>
                <p>
                  {
                    (labels[
                      resource.installation?.status ?? "binding_required"
                    ] ?? ["尚未核对", "Not checked"])[zh ? 0 : 1]
                  }
                </p>
                {resource.host_adaptation?.adapted && (
                  <p>
                    {zh
                      ? "提供保留来源记录的宿主格式包"
                      : "Host format package retains source provenance"}
                  </p>
                )}
                {resource.host_format.status === "needs_adapter" && (
                  <p className="break-all">{resource.host_format.detail}</p>
                )}
                {resource.host_adaptation?.status === "ready" && (
                  <SourceSkillInstall
                    templateId={templateId}
                    resource={resource}
                    locale={locale}
                    open={open}
                    onInstalled={() => void inspect(true)}
                  />
                )}
                {resource.host_adaptation?.status === "ready" && (
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    disabled={!!downloading}
                    onClick={() => void saveArchive(resource)}
                  >
                    {downloading === resource.id
                      ? zh
                        ? "准备源包…"
                        : "Preparing package…"
                      : zh
                        ? "下载源包"
                        : "Download source package"}
                  </Button>
                )}
              </li>
            ))}
          </ul>
        </>
      )}
    </section>
  );
}
