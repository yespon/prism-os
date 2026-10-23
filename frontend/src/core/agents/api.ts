import { fetchAuthApi, getAuthHeaders } from "@/core/api/auth-client";
import { getBackendBaseURL } from "@/core/config";

import type { Agent, CreateAgentRequest, UpdateAgentRequest, CopyAgentRequest, Skill } from "./types";

export async function listAgents(): Promise<Agent[]> {
  const res = await fetchAuthApi("/api/agents");
  if (!res.ok) throw new Error(`Failed to load agents: ${res.statusText}`);
  const data = (await res.json()) as { agents: Agent[] };
  return data.agents;
}

export class AgentReadError extends Error {
  constructor(public status: number) { super(`Agent read failed (${status})`); }
}

export async function getAgent(name: string): Promise<Agent> {
  const res = await fetchAuthApi(`/api/agents/${name}`);
  if (!res.ok) throw new AgentReadError(res.status);
  return res.json() as Promise<Agent>;
}

export class AgentMutationError extends Error {
  constructor(public status: number, public inspectionRequired = false, message?: string) { super(message ?? `Agent save failed (${status})`); }
}
async function saveAgent(path: string, method: string, request: CreateAgentRequest | UpdateAgentRequest | CopyAgentRequest, options: {isCurrent?: () => boolean} = {}): Promise<Agent> {
  const current = () => !options.isCurrent || options.isCurrent();
  const headers = await getAuthHeaders({"Content-Type":"application/json"});
  if (!current()) throw new AgentMutationError(401, false, "Agent draft identity changed");
  const response = await fetch(`${getBackendBaseURL()}${path}`, {method, headers, credentials:"include",body:JSON.stringify(request)});
  if (!current()) throw new AgentMutationError(401, false, "Agent draft identity changed");
  const body = await response.json().catch(() => null) as (Agent & {detail?: unknown}) | null;
  if (!current()) throw new AgentMutationError(401, false, "Agent draft identity changed");
  if (!response.ok) throw new AgentMutationError(response.status, response.status >= 500, typeof body?.detail === "string" ? body.detail : undefined);
  if (!body || typeof body.id !== "string") throw new AgentMutationError(503,true);
  return body;
}
export async function createAgent(request: CreateAgentRequest, options: {isCurrent?: () => boolean} = {}): Promise<Agent> {
  return saveAgent("/api/agents","POST",request,options);
}
export async function updateAgent(name: string, request: UpdateAgentRequest, options: {isCurrent?: () => boolean} = {}): Promise<Agent> {
  return saveAgent(`/api/agents/${encodeURIComponent(name)}`,"PUT",request,options);
}

export async function deleteAgent(name: string): Promise<void> {
  const res = await fetchAuthApi(`/api/agents/${name}`, {
    method: "DELETE",
  });
  if (!res.ok) throw new Error(`Failed to delete agent: ${res.statusText}`);
}

export async function checkAgentName(
  name: string,
  isShared?: boolean,
): Promise<{ available: boolean; name: string }> {
  const queryParams = new URLSearchParams({ name });
  if (isShared) {
    queryParams.append("is_shared", "true");
  }
  const res = await fetchAuthApi(
    `/api/agents/check?${queryParams.toString()}`,
  );
  if (!res.ok) {
    const err = (await res.json().catch(() => ({}))) as { detail?: string };
    throw new Error(
      err.detail ?? `Failed to check agent name: ${res.statusText}`,
    );
  }
  return res.json() as Promise<{ available: boolean; name: string }>;
}


export async function listSkills(signal?: AbortSignal): Promise<Skill[]> {
  const res = await fetchAuthApi("/api/skills", {signal});
  if (!res.ok) throw new Error(`Failed to load skills: ${res.statusText}`);
  const data = (await res.json()) as { skills: Skill[] };
  return data.skills;
}

export async function copyAgent(name: string, request: CopyAgentRequest, options: {isCurrent?: () => boolean} = {}): Promise<Agent> {
  try {
    return await saveAgent(`/api/agents/${encodeURIComponent(name)}/copy`, "POST", request, options);
  } catch (error) {
    if (error instanceof AgentMutationError) throw error;
    throw new AgentMutationError(503, true, "复制结果未确认，请先检查目标 Agent");
  }
}
