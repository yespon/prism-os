import { fetchAuthApi } from "@/core/api/auth-client";

export type SkillImportScope = "personal" | "tenant";
export interface SkillImportOperation {
  operation_id: string;
  name: string;
  scope: SkillImportScope;
  state: string;
  phase?: string;
  files_verified: boolean;
  staged_files_verified?: boolean;
  registered: boolean;
  enabled: boolean | null;
  execution_ready: false;
  kind?: "manual_create";
  requested_enabled?: boolean;
  configuration_phase?: "pending" | "confirmed" | "unknown";
  resource_id?: string;
}
export interface SkillImportPage {
  operations: SkillImportOperation[];
  next_cursor: string | null;
  total: number;
}
export class SkillImportError extends Error {
  constructor(
    public status: number,
    public operationId?: string,
    message?: string,
  ) {
    super(message ?? `Skill import request failed (${status})`);
  }
}
export async function readSkillImportResponse<T>(
  response: Response,
): Promise<T> {
  const body = (await response.json().catch(() => null)) as {
    detail?: unknown;
  } | null;
  if (!response.ok) {
    const detail = body?.detail;
    const operation =
      typeof detail === "object" && detail !== null && "operation_id" in detail
        ? (detail as { operation_id?: unknown }).operation_id
        : undefined;
    throw new SkillImportError(
      response.status,
      typeof operation === "string" ? operation : undefined,
      typeof detail === "string"
        ? detail
        : typeof detail === "object" &&
            detail !== null &&
            "message" in detail &&
            typeof detail.message === "string"
          ? detail.message
          : undefined,
    );
  }
  if (body === null) throw new SkillImportError(503);
  return body as T;
}
function importsUrl(scope: SkillImportScope) {
  return scope === "tenant"
    ? "/api/tenants/skills/imports"
    : "/api/skills/personal/imports";
}
export async function loadSkillImportOperations(
  scope: SkillImportScope,
  signal: AbortSignal,
  cursor?: string,
) {
  const url =
    importsUrl(scope) + (cursor ? `?${new URLSearchParams({ cursor })}` : "");
  const page = await readSkillImportResponse<SkillImportPage>(
    await fetchAuthApi(url, { signal }),
  );
  if (
    !page ||
    !Array.isArray(page.operations) ||
    (page.next_cursor !== null && typeof page.next_cursor !== "string") ||
    !Number.isSafeInteger(page.total) ||
    page.total < 0
  )
    throw new SkillImportError(503);
  return page;
}

export async function changeSkillImportOperation(
  scope: SkillImportScope,
  operation: string,
  action: "recover" | "abort",
  signal: AbortSignal,
) {
  return readSkillImportResponse<SkillImportOperation>(
    await fetchAuthApi(
      `${importsUrl(scope)}/${encodeURIComponent(operation)}/${action}`,
      { method: "POST", signal },
    ),
  );
}

export function skillImportErrorMessage(error: unknown, zh: boolean) {
  if (error instanceof SkillImportError) {
    if (error.operationId || error.status >= 500)
      return zh
        ? "导入结果需要核对，请查看 Skill 导入记录，避免重复导入。"
        : "Import outcome uncertain. Inspect import records before importing again.";
    if (error.status === 401 || error.status === 403)
      return zh
        ? "当前会话或租户权限不允许导入。"
        : "The current session or tenant role does not permit this import.";
    if (error.status === 409)
      return zh
        ? "来源已改变或存在同名资源，请检查现有资源。"
        : "Source changed or a same-name resource exists. Inspect current resources.";
  }
  if (error instanceof TypeError)
    return zh
      ? "网络中断，导入结果暂无法确认；请先检查导入记录。"
      : "Connection interrupted; inspect import records to establish the outcome.";
  return error instanceof Error
    ? error.message
    : zh
      ? "导入失败"
      : "Import failed";
}
