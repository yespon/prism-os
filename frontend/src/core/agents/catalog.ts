import type { AgentQuickPrompt } from "./types";
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
  quick_prompts: AgentQuickPrompt[];
  welcome_message: string;
  avatar_id: string;
  excluded_resources: string[];
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

export async function loadAgentCatalog(
  locale: "zh" | "en",
  signal?: AbortSignal,
) {
  const [templates, personas] = await Promise.all([
    fetchAuthApi(`/api/agent-catalog/templates?locale=${locale}`, { signal }),
    fetchAuthApi("/api/agent-catalog/personas", { signal }),
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
  signal?: AbortSignal,
): Promise<AgentTemplatePreview> {
  const res = await fetchAuthApi(
    `/api/agent-catalog/templates/${encodeURIComponent(id)}?locale=${locale}`,
    { signal },
  );
  if (!res.ok) throw new Error("无法加载所选模板");
  return res.json() as Promise<AgentTemplatePreview>;
}

export interface AgentAvatar {
  id: string;
  label: string;
  kind: "experts" | "personas";
  sha256: string;
}
export interface PersonalityQuestion {
  id: number;
  question: string;
  option_a: string;
  option_b: string;
}
export interface PersonalityResult {
  code: string;
  dimensions: Record<string, [string, number]>;
  automatic_apply: false;
}

async function readCatalog<T>(path: string, signal: AbortSignal): Promise<T> {
  const response = await fetchAuthApi(path, { signal });
  if (!response.ok) throw new Error("Catalog unavailable");
  return response.json() as Promise<T>;
}
export function loadAgentAvatars(signal: AbortSignal) {
  return readCatalog<{ avatars: AgentAvatar[] }>(
    "/api/agent-catalog/avatars",
    signal,
  );
}
export function loadPersonalityQuestions(
  locale: "zh" | "en",
  signal: AbortSignal,
) {
  return readCatalog<{ questions: PersonalityQuestion[] }>(
    `/api/agent-catalog/personality-test?locale=${locale}`,
    signal,
  );
}
export async function scorePersonality(
  answers: Record<string, "A" | "B">,
  signal: AbortSignal,
): Promise<PersonalityResult> {
  const response = await fetchAuthApi("/api/agent-catalog/personality-test", {
    method: "POST",
    signal,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ answers }),
  });
  if (!response.ok) throw new Error("Questionnaire could not be scored");
  return response.json() as Promise<PersonalityResult>;
}
