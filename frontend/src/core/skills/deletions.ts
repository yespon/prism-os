import { getAuthHeaders } from "@/core/api/auth-client";
import { getBackendBaseURL } from "@/core/config";

import type { SkillImportScope } from "./imports";
import { SkillMutationError, readSkillMutationResponse } from "./mutations";

export interface SkillDeletionPreflight {
  name: string;
  resource_id: string;
  selected_resource_id: string;
  scope: SkillImportScope;
  target_kind: "owned" | "missing" | "public_override";
  tree_sha256: string;
  file_sha256: string | null;
  members: number;
  references: number;
  eligible: boolean;
  physical_reclamation: boolean;
}
export interface SkillDeletionOptions {
  expectedResourceId?: string;
  expectedTreeSha256?: string;
  expectedFileSha256?: string;
  signal?: AbortSignal;
  isCurrent?: () => boolean;
}
function current(options: SkillDeletionOptions) {
  if (options.signal?.aborted || (options.isCurrent && !options.isCurrent()))
    throw new SkillMutationError(
      401,
      options.expectedResourceId,
      false,
      "Deletion identity changed",
    );
}
function url(
  scope: SkillImportScope,
  name: string,
  options: SkillDeletionOptions,
) {
  const query = new URLSearchParams();
  if (options.expectedResourceId)
    query.set("expected_resource_id", options.expectedResourceId);
  if (options.expectedTreeSha256)
    query.set("expected_tree_sha256", options.expectedTreeSha256);
  if (options.expectedFileSha256)
    query.set("expected_file_sha256", options.expectedFileSha256);
  return (
    `${getBackendBaseURL()}/api/${scope === "tenant" ? "tenants/skills" : "skills/personal"}/${encodeURIComponent(name)}` +
    (query.size ? `?${query}` : "")
  );
}
export async function loadSkillDeletionPreflight(
  scope: SkillImportScope,
  name: string,
  options: SkillDeletionOptions,
) {
  const headers = await getAuthHeaders();
  current(options);
  const target = url(scope, name, options);
  const [path, query] = target.split("?");
  const response = await fetch(
    `${path}/deletion-preflight${query ? `?${query}` : ""}`,
    { headers, signal: options.signal },
  );
  current(options);
  const body =
    await readSkillMutationResponse<SkillDeletionPreflight>(response);
  current(options);
  if (
    body.name !== name ||
    body.scope !== scope ||
    typeof body.resource_id !== "string" ||
    typeof body.selected_resource_id !== "string" ||
    !/^[0-9a-f]{64}$/.test(body.tree_sha256) ||
    !Number.isSafeInteger(body.members) ||
    body.members < 0 ||
    !Number.isSafeInteger(body.references) ||
    body.references < 0 ||
    typeof body.eligible !== "boolean" ||
    body.eligible !== (body.references === 0) ||
    !["owned", "missing", "public_override"].includes(body.target_kind) ||
    typeof body.physical_reclamation !== "boolean"
  )
    throw new SkillMutationError(
      503,
      options.expectedResourceId,
      true,
      "Deletion preflight unavailable",
    );
  return body;
}
export async function deleteOwnedSkill(
  scope: SkillImportScope,
  name: string,
  options: SkillDeletionOptions = {},
) {
  const headers = await getAuthHeaders();
  current(options);
  const response = await fetch(url(scope, name, options), {
    method: "DELETE",
    headers,
    signal: options.signal,
  });
  current(options);
  if (response.status === 204) return;
  if (!response.ok) await readSkillMutationResponse(response);
  throw new SkillMutationError(
    503,
    options.expectedResourceId,
    true,
    "Deletion completion was not confirmed",
  );
}
