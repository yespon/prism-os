import { readSkillImportResponse, SkillImportError } from "./imports";
import { getAuthHeaders } from "@/core/api/auth-client";
import { getBackendBaseURL } from "@/core/config";

import type { Skill, AvailableSkillResponse, SummarizeDiagnosisRequest, SummarizeDiagnosisResponse } from "./type";

export async function loadSkills() {
  const skills = await fetch(`${getBackendBaseURL()}/api/skills`, {
    headers: await getAuthHeaders(),
  });
  const json = await skills.json();
  return json.skills as Skill[];
}

export interface InstallSkillRequest {
  thread_id: string;
  path: string;
}

export interface InstallSkillResponse {
  success: boolean;
  skill_name: string;
  message: string;
  operation_id?: string;
}

export async function installSkill(
  request: InstallSkillRequest,
): Promise<InstallSkillResponse> {
  const response = await fetch(`${getBackendBaseURL()}/api/skills/install`, {
    method: "POST",
    headers: await getAuthHeaders({
      "Content-Type": "application/json",
    }),
    body: JSON.stringify(request),
  });

  try {
    return await readSkillImportResponse<InstallSkillResponse>(response);
  } catch (error) {
    if (!(error instanceof SkillImportError)) throw error;
    return { success: false, skill_name: "", message: error.message, operation_id: error.operationId };
  }
}

export async function loadAvailableSkills() {
  const response = await fetch(`${getBackendBaseURL()}/api/skills/available`, {
    headers: await getAuthHeaders(),
  });

  if (!response.ok) {
    throw new Error(`Failed to load available skills: ${response.status}`);
  }

  const json = await response.json();
  return json.skills as AvailableSkillResponse[];
}

export async function loadTenantSkills() {
  const response = await fetch(`${getBackendBaseURL()}/api/tenants/skills`, {
    headers: await getAuthHeaders(),
  });

  if (!response.ok) {
    throw new Error(`Failed to load tenant skills: ${response.status}`);
  }

  const json = await response.json();
  return json.skills as Skill[];
}

export async function updateTenantSkill(skillName: string, enabled: boolean) {
  const response = await fetch(
    `${getBackendBaseURL()}/api/tenants/skills/${skillName}`,
    {
      method: "PUT",
      headers: await getAuthHeaders({
        "Content-Type": "application/json",
      }),
      body: JSON.stringify({
        enabled,
      }),
    }
  );
  if (!response.ok) {
    throw new Error(`Failed to update tenant skill: ${response.status}`);
  }
  return response.json();
}

export async function createTenantSkill(input: {
  name: string;
  description: string;
  instructions?: string | null;
  enabled?: boolean;
  category?: string;
  bound_tools?: string[];
  prompt_template?: string | null;
  strategy?: string | null;
}) {
  const response = await fetch(
    `${getBackendBaseURL()}/api/tenants/skills`,
    {
      method: "POST",
      headers: await getAuthHeaders({
        "Content-Type": "application/json",
      }),
      body: JSON.stringify(input),
    }
  );
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    throw new Error(payload.detail ?? `Failed to create tenant skill: ${response.status}`);
  }
  return response.json();
}

export async function patchTenantSkill(
  skillName: string,
  input: {
    description?: string | null;
    instructions?: string | null;
    enabled?: boolean;
    category?: string;
    bound_tools?: string[];
    prompt_template?: string | null;
    strategy?: string | null;
  },
) {
  const response = await fetch(
    `${getBackendBaseURL()}/api/tenants/skills/${skillName}`,
    {
      method: "PATCH",
      headers: await getAuthHeaders({
        "Content-Type": "application/json",
      }),
      body: JSON.stringify(input),
    }
  );
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    throw new Error(payload.detail ?? `Failed to patch tenant skill: ${response.status}`);
  }
  return response.json();
}

export async function createPersonalSkill(input: {
  name: string;
  description: string;
  instructions?: string | null;
  enabled?: boolean;
  changelog?: string | null;
  bound_tools?: string[];
  prompt_template?: string | null;
  strategy?: string | null;
}) {
  const response = await fetch(
    `${getBackendBaseURL()}/api/skills/personal`,
    {
      method: "POST",
      headers: await getAuthHeaders({
        "Content-Type": "application/json",
      }),
      body: JSON.stringify(input),
    }
  );
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    throw new Error(payload.detail ?? `Failed to create personal skill: ${response.status}`);
  }
  return response.json();
}

export async function patchPersonalSkill(
  skillName: string,
  input: {
    description?: string | null;
    instructions?: string | null;
    enabled?: boolean;
    category?: string;
    bound_tools?: string[];
    prompt_template?: string | null;
    strategy?: string | null;
  },
) {
  const response = await fetch(
    `${getBackendBaseURL()}/api/skills/personal/${skillName}`,
    {
      method: "PATCH",
      headers: await getAuthHeaders({
        "Content-Type": "application/json",
      }),
      body: JSON.stringify(input),
    }
  );
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    throw new Error(payload.detail ?? `Failed to patch personal skill: ${response.status}`);
  }
  return response.json();
}

export async function deletePersonalSkill(skillName: string) {
  const response = await fetch(`${getBackendBaseURL()}/api/skills/personal/${skillName}`, {
    method: "DELETE",
    headers: await getAuthHeaders(),
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    throw new Error(payload.detail ?? `Failed to delete personal skill: ${response.status}`);
  }
}

export async function importPersonalSkill(file: File) {
  const formData = new FormData();
  formData.append("archive", file);

  const response = await fetch(`${getBackendBaseURL()}/api/skills/personal/import`, {
    method: "POST",
    headers: await getAuthHeaders(),
    body: formData,
  });

  if (!response.ok) {
    if (response.status === 413) {
      throw new Error("技能包过大（超过网关限制），请压缩后重试或联系管理员提升上传上限");
    }
    return readSkillImportResponse(response);
  }

  return readSkillImportResponse(response);
}

export async function importTenantSkill(file: File) {
  const formData = new FormData();
  formData.append("archive", file);

  const response = await fetch(`${getBackendBaseURL()}/api/tenants/skills/import`, {
    method: "POST",
    headers: await getAuthHeaders(),
    body: formData,
  });

  if (!response.ok) {
    if (response.status === 413) {
      throw new Error("技能包过大（超过网关限制），请压缩后重试或联系管理员提升上传上限");
    }
    return readSkillImportResponse(response);
  }

  return readSkillImportResponse(response);
}

export async function deleteTenantSkill(skillName: string) {
  const response = await fetch(
    `${getBackendBaseURL()}/api/tenants/skills/${skillName}`,
    {
      method: "DELETE",
      headers: await getAuthHeaders(),
    }
  );
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    throw new Error(payload.detail ?? `Failed to delete tenant skill: ${response.status}`);
  }
}

export async function getSkillDetail(skillName: string) {
  const response = await fetch(
    `${getBackendBaseURL()}/api/skills/${skillName}/detail`,
    {
      headers: await getAuthHeaders(),
    }
  );
  if (!response.ok) {
    throw new Error(`Failed to load skill detail: ${response.status}`);
  }
  return response.json();
}

export async function generateInstructions(prompt: string, modelName?: string) {
  const response = await fetch(
    `${getBackendBaseURL()}/api/skills/generate-instructions`,
    {
      method: "POST",
      headers: await getAuthHeaders({
        "Content-Type": "application/json",
      }),
      body: JSON.stringify({ prompt, model_name: modelName }),
    }
  );
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    throw new Error(payload.detail ?? `Failed to generate instructions: ${response.status}`);
  }
  return response.json();
}

export async function summarizeDiagnosis(
  input: SummarizeDiagnosisRequest,
): Promise<SummarizeDiagnosisResponse> {
  const response = await fetch(
    `${getBackendBaseURL()}/api/skills/summarize-diagnosis`,
    {
      method: "POST",
      headers: await getAuthHeaders({
        "Content-Type": "application/json",
      }),
      body: JSON.stringify(input),
    }
  );
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    throw new Error(payload.detail ?? `Failed to summarize diagnosis: ${response.status}`);
  }
  return response.json();
}
