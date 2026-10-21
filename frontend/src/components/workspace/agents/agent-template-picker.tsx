"use client";

import { useEffect, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  loadAgentCatalog,
  previewAgentTemplate,
  type AgentPersona,
  type AgentTemplate,
  type AgentTemplatePreview,
} from "@/core/agents/catalog";
import { useTenantKey } from "@/core/agents/hooks";
import { getCurrentTenantId } from "@/core/tenants/store";

import { AgentResourcePreflight } from "./agent-resource-preflight";

interface Props {
  templateReadOnly?: boolean;
  open: boolean;
  locale: "zh" | "en";
  templateId: string;
  personaCode: string;
  onTemplate: (template: AgentTemplatePreview | null) => void;
  onPersona: (code: string) => void;
}

export function AgentTemplatePicker({
  templateReadOnly = false,
  open,
  locale,
  templateId,
  personaCode,
  onTemplate,
  onPersona,
}: Props) {
  const tenant = useTenantKey();
  const [templates, setTemplates] = useState<AgentTemplate[]>([]);
  const [personas, setPersonas] = useState<AgentPersona[]>([]);
  const [query, setQuery] = useState("");
  const [kind, setKind] = useState("all");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [selecting, setSelecting] = useState(false);
  const [retry, setRetry] = useState(0);
  const generation = useRef(0);
  const selection = useRef<AbortController | null>(null);
  const zh = locale === "zh";

  useEffect(() => {
    const current = ++generation.current;
    const request = new AbortController();
    selection.current?.abort();
    setTemplates([]);
    setPersonas([]);
    setSelecting(false);
    setError("");
    setQuery("");
    setKind("all");
    if (open) {
      setLoading(true);
      void loadAgentCatalog(locale, request.signal)
        .then((data) => {
          if (
            !request.signal.aborted &&
            generation.current === current &&
            tenant === (getCurrentTenantId() ?? "_")
          ) {
            setTemplates(data.templates);
            setPersonas(data.personas);
          }
        })
        .catch(() => {
          if (!request.signal.aborted && generation.current === current)
            setError(
              zh
                ? "模板暂时不可用，可继续手动创建。"
                : "Templates unavailable. You can still create an agent manually.",
            );
        })
        .finally(() => {
          if (!request.signal.aborted && generation.current === current)
            setLoading(false);
        });
    }
    return () => {
      request.abort();
      selection.current?.abort();
      ++generation.current;
    };
  }, [open, locale, tenant, retry, zh]);

  const filtered = templates.filter(
    (item) =>
      (kind === "all" || item.kind === kind) &&
      `${item.name} ${item.description} ${item.division}`
        .toLowerCase()
        .includes(query.toLowerCase()),
  );
  const visible = filtered.slice(0, 100);
  const selected = templates.find((item) => item.id === templateId);
  if (selected && !visible.some((item) => item.id === selected.id))
    visible.unshift(selected);

  async function selectTemplate(id: string) {
    selection.current?.abort();
    const request = new AbortController();
    selection.current = request;
    const current = generation.current;
    if (id === "manual") {
      setSelecting(false);
      onTemplate(null);
      return;
    }
    setSelecting(true);
    setError("");
    const active = () =>
      !request.signal.aborted &&
      generation.current === current &&
      tenant === (getCurrentTenantId() ?? "_");
    try {
      const preview = await previewAgentTemplate(id, locale, request.signal);
      if (active()) onTemplate(preview);
    } catch {
      if (active())
        setError(
          zh
            ? "模板加载失败，请重试选择。"
            : "Could not load this template. Select it again to retry.",
        );
    } finally {
      if (active()) setSelecting(false);
    }
  }

  return (
    <section className="bg-muted/30 space-y-2 rounded-lg border p-3">
      <h3 className="text-xs font-medium">
        {zh ? "从专家或子智能体模板开始" : "Start from an expert or specialist"}
      </h3>
      <Input
        aria-label={zh ? "搜索模板" : "Search templates"}
        placeholder={
          zh ? "搜索名称、描述或领域" : "Search name, description or field"
        }
        disabled={templateReadOnly}
        value={query}
        onChange={(event) => setQuery(event.target.value)}
        className="h-8 text-xs"
      />
      <select
        aria-label={zh ? "模板类型" : "Template type"}
        className="bg-background w-full rounded border p-2 text-xs"
        disabled={templateReadOnly}
        value={kind}
        onChange={(event) => setKind(event.target.value)}
      >
        <option value="all">{zh ? "全部类型" : "All types"}</option>
        <option value="expert">{zh ? "专家" : "Experts"}</option>
        <option value="subagent">{zh ? "子智能体" : "Specialists"}</option>
      </select>
      <select
        aria-label={zh ? "专家模板" : "Expert template"}
        className="bg-background w-full rounded border p-2 text-xs"
        value={templateId || "manual"}
        disabled={loading || templateReadOnly}
        onChange={(event) => void selectTemplate(event.target.value)}
      >
        <option value="manual">{zh ? "手动设定" : "Configure manually"}</option>
        {templateId && !selected && (
          <option value={templateId}>{templateId}</option>
        )}
        {visible.map((item) => (
          <option key={item.id} value={item.id}>
            {item.name}
          </option>
        ))}
      </select>
      {selecting && (
        <p role="status" className="text-xs">
          {zh ? "正在读取模板…" : "Loading template…"}
        </p>
      )}
      {filtered.length > 100 && (
        <p className="text-muted-foreground text-xs">
          {zh
            ? `共 ${filtered.length} 个结果，请搜索缩小范围。`
            : `${filtered.length} results. Search to narrow the list.`}
        </p>
      )}
      {selected?.description && (
        <p className="text-muted-foreground text-xs">{selected.description}</p>
      )}
      {!!selected?.bundled_resources.length && (
        <p className="text-muted-foreground text-xs">
          {zh
            ? `原目录配套文件 ${selected.bundled_resources.length} 项；请核对完整资源与安装状态。`
            : `${selected.bundled_resources.length} files in the original resource list. Check complete resources and installation status.`}
        </p>
      )}
      {!!selected?.excluded_resources?.length && (
        <p className="text-muted-foreground text-xs">
          {zh
            ? "以下配套能力待独立实现："
            : "Independent implementations pending: "}
          {selected.excluded_resources.join(", ")}
        </p>
      )}
      <AgentResourcePreflight
        open={open}
        templateId={templateId}
        locale={locale}
      />
      <select
        aria-label={zh ? "人格风格" : "Personality style"}
        className="bg-background w-full rounded border p-2 text-xs"
        value={personaCode || "none"}
        disabled={loading}
        onChange={(event) =>
          onPersona(event.target.value === "none" ? "" : event.target.value)
        }
      >
        <option value="none">
          {zh ? "使用基础提示" : "Use base instructions"}
        </option>
        {personaCode && !personas.some((item) => item.code === personaCode) && (
          <option value={personaCode}>{personaCode}</option>
        )}
        {personas.map((item) => (
          <option key={item.code} value={item.code}>
            {item.code} · {zh ? item.name_zh : item.name_en}
          </option>
        ))}
      </select>
      {error && (
        <div role="alert" className="text-destructive text-xs">
          {error}{" "}
          <Button
            type="button"
            variant="ghost"
            onClick={() => setRetry((value) => value + 1)}
          >
            {zh ? "重试" : "Retry"}
          </Button>
        </div>
      )}
    </section>
  );
}
