import { fetchAuthApi } from "@/core/api/auth-client";
import { readSkillImportResponse } from "@/core/skills/imports";

import type { AgentQuickPrompt } from "./types";

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

export interface ResourcePreflightItem {
  id: string;
  kind: string;
  root: string;
  bundle_sha256: string;
  members: Array<{ path: string; sha256: string; source_path: string }>;
  host_format: { status: string; detail?: string; skill_name?: string };
  host_adaptation?: {
    status: string;
    name?: string;
    adapted?: boolean;
    detail?: string;
  };
  installation?: {
    status: string;
    candidates: Array<{
      scope: string;
      enabled: boolean;
      content_status: string;
    }>;
  };
  execution_ready: false;
}
export interface ResourcePreflight {
  template_id: string;
  revision: string;
  declaration_sha256: string;
  member_count: number;
  additional_member_count: number;
  resources: ResourcePreflightItem[];
  excluded_resources: string[];
  installation_checked: boolean;
  runtime_dependencies_checked: false;
  execution_ready: false;
  permission_grants: false;
}
export function loadResourcePreflight(
  id: string,
  locale: "zh" | "en",
  signal: AbortSignal,
) {
  return readCatalog<ResourcePreflight>(
    `/api/agent-catalog/templates/${encodeURIComponent(id)}/resources?locale=${locale}&check_installation=true`,
    signal,
  );
}
export async function downloadResourceArchive(
  id: string,
  resourceId: string,
  locale: "zh" | "en",
  signal: AbortSignal,
) {
  const response = await fetchAuthApi(
    `/api/agent-catalog/templates/${encodeURIComponent(id)}/resources/${encodeURIComponent(resourceId)}/archive?locale=${locale}`,
    { signal },
  );
  if (!response.ok) throw new Error("Source archive unavailable");
  return response.blob();
}

export interface SourceSkillInstallResult {
  operation_id: string;
  name: string;
  scope: "personal" | "tenant";
  registered: true;
  execution_ready: false;
  permission_grants: false;
}
export async function installSourceSkill(
  id: string,
  resourceId: string,
  locale: "zh" | "en",
  scope: "personal" | "tenant",
  bundleSha256: string,
  signal: AbortSignal,
) {
  return readSkillImportResponse<SourceSkillInstallResult>(
    await fetchAuthApi(
      `/api/agent-catalog/templates/${encodeURIComponent(id)}/resources/${encodeURIComponent(resourceId)}/install?locale=${locale}`,
      {
        method: "POST",
        signal,
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ scope, bundle_sha256: bundleSha256 }),
      },
    ),
  );
}
