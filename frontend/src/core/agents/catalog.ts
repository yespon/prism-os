import { fetchAuthApi } from "@/core/api/auth-client";

export interface AgentTemplate {
  id: string;
  kind: "expert" | "subagent";
  name: string;
  suggested_name: string;
  description: string;
  locale: "zh" | "en";
  division: string;
  bundled_resources: string[];
  revision: string;
}

export interface AgentTemplatePreview extends AgentTemplate {
  system_prompt: string;
}

export interface AgentPersona {
  code: string;
  name_zh: string;
  name_en: string;
  summary_zh: string;
  summary_en: string;
}

export async function loadAgentCatalog(locale: "zh" | "en") {
  const [templates, personas] = await Promise.all([
    fetchAuthApi(`/api/agent-catalog/templates?locale=${locale}`),
    fetchAuthApi("/api/agent-catalog/personas"),
  ]);
  if (!templates.ok || !personas.ok) throw new Error("无法加载专家与人格模板");
  const templateData = (await templates.json()) as {
    templates: AgentTemplate[];
  };
  const personaData = (await personas.json()) as { personas: AgentPersona[] };
  return { ...templateData, ...personaData };
}

export async function previewAgentTemplate(
  id: string,
  locale: "zh" | "en",
): Promise<AgentTemplatePreview> {
  const res = await fetchAuthApi(
    `/api/agent-catalog/templates/${encodeURIComponent(id)}?locale=${locale}`,
  );
  if (!res.ok) throw new Error("无法加载所选模板");
  return res.json() as Promise<AgentTemplatePreview>;
}
