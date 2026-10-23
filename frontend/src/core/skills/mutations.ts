export class SkillMutationError extends Error {
  constructor(
    public status: number,
    public resourceId?: string,
    public inspectionRequired = false,
    message?: string,
    public operationId?: string,
  ) {
    super(message ?? `Skill edit failed (${status})`);
  }
}

export async function readSkillMutationResponse<T>(
  response: Response,
): Promise<T> {
  const body = (await response.json().catch(() => null)) as {
    detail?: unknown;
  } | null;
  if (!response.ok) {
    const detail = body?.detail;
    const object =
      typeof detail === "object" && detail !== null
        ? (detail as Record<string, unknown>)
        : null;
    throw new SkillMutationError(
      response.status,
      typeof object?.resource_id === "string" ? object.resource_id : undefined,
      response.status >= 500 || object?.inspection_required === true,
      typeof detail === "string"
        ? detail
        : typeof object?.message === "string"
          ? object.message
          : undefined,
      typeof object?.operation_id === "string" ? object.operation_id : undefined,
    );
  }
  if (!body) throw new SkillMutationError(503, undefined, true);
  return body as T;
}
export function skillMutationMessage(error: unknown, zh = true) {
  if (error instanceof SkillMutationError) {
    if (error.inspectionRequired)
      return zh
        ? "修改结果暂无法确认，请重新检查当前资源，避免重复保存。"
        : "Edit outcome uncertain. Inspect the current resource before saving again.";
    if (error.status === 409)
      return zh
        ? "资源实例或文件已改变，请重新检查后再保存。"
        : "Resource instance or files changed. Inspect again before saving.";
    if ([401, 403].includes(error.status))
      return zh
        ? "当前身份不允许修改此资源。"
        : "The current identity cannot edit this resource.";
  }
  if (error instanceof TypeError)
    return zh
      ? "连接中断，修改结果暂无法确认，请重新检查当前资源。"
      : "Connection interrupted; inspect the current edit outcome.";
  return error instanceof Error
    ? error.message
    : zh
      ? "修改失败"
      : "Edit failed";
}
