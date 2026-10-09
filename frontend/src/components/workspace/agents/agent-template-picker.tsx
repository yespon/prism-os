"use client";

import { useEffect, useRef, useState } from "react";

import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  loadAgentCatalog,
  previewAgentTemplate,
  type AgentPersona,
  type AgentTemplate,
  type AgentTemplatePreview,
} from "@/core/agents/catalog";

interface Props {
  open: boolean;
  locale: "zh" | "en";
  templateId: string;
  personaCode: string;
  onTemplate: (template: AgentTemplatePreview | null) => void;
  onPersona: (code: string) => void;
}

export function AgentTemplatePicker({
  open,
  locale,
  templateId,
  personaCode,
  onTemplate,
  onPersona,
}: Props) {
  const [templates, setTemplates] = useState<AgentTemplate[]>([]);
  const [personas, setPersonas] = useState<AgentPersona[]>([]);
  const [query, setQuery] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [selecting, setSelecting] = useState(false);
  const generation = useRef(0);
  const zh = locale === "zh";

  useEffect(() => {
    const current = ++generation.current;
    if (!open) return;
    setLoading(true);
    setSelecting(false);
    setError("");
    setQuery("");
    void loadAgentCatalog(locale)
      .then((data) => {
        if (generation.current !== current) return;
        setTemplates(data.templates);
        setPersonas(data.personas);
      })
      .catch(() => {
        if (generation.current === current)
          setError(
            zh
              ? "模板暂时不可用，可继续手动创建。"
              : "Templates unavailable. You can still create an agent manually.",
          );
      })
      .finally(() => {
        if (generation.current === current) setLoading(false);
      });
    return () => {
      generation.current = current + 1;
    };
  }, [open, locale, zh]);

  const filtered = templates.filter((item) =>
    `${item.name} ${item.description} ${item.division}`
      .toLowerCase()
      .includes(query.toLowerCase()),
  );
  const visible = filtered.slice(0, 100);
  const selected = templates.find((item) => item.id === templateId);
  if (selected && !visible.some((item) => item.id === selected.id))
    visible.unshift(selected);

  async function selectTemplate(id: string) {
    if (id === "manual") {
      onTemplate(null);
      return;
    }
    const current = generation.current;
    setSelecting(true);
    setError("");
    try {
      const preview = await previewAgentTemplate(id, locale);
      if (generation.current === current) onTemplate(preview);
    } catch {
      if (generation.current === current)
        setError(
          zh
            ? "模板加载失败，请重试。"
            : "Could not load this template. Try again.",
        );
    } finally {
      if (generation.current === current) setSelecting(false);
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
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        className="h-8 text-xs"
      />
      <Select
        value={templateId || "manual"}
        disabled={loading || selecting}
        onValueChange={(id) => {
          void selectTemplate(id);
        }}
      >
        <SelectTrigger
          className="h-9 w-full"
          aria-label={zh ? "专家模板" : "Expert template"}
        >
          <SelectValue placeholder={zh ? "选择模板" : "Choose a template"} />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="manual">
            {zh ? "手动设定" : "Configure manually"}
          </SelectItem>
          {visible.map((item) => (
            <SelectItem key={item.id} value={item.id}>
              {item.name}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
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
            ? "此模板有配套技能或工具，请按需另行安装与授权。"
            : "This template has companion skills or tools. Install and authorize them as needed."}
        </p>
      )}
      <Select
        value={personaCode || "none"}
        disabled={loading}
        onValueChange={(code) => onPersona(code === "none" ? "" : code)}
      >
        <SelectTrigger
          className="h-9 w-full"
          aria-label={zh ? "人格风格" : "Personality style"}
        >
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="none">
            {zh ? "保持原有人格" : "Keep the original personality"}
          </SelectItem>
          {personas.map((item) => (
            <SelectItem key={item.code} value={item.code}>
              {item.code} · {zh ? item.name_zh : item.name_en}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
      {error && (
        <p className="text-destructive text-xs" role="alert">
          {error}
        </p>
      )}
    </section>
  );
}
