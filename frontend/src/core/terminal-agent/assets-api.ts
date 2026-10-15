export class AssetOperationError extends Error {
  constructor(message: string, readonly inspectionRequired = false) {
    super(message);
    this.name = "AssetOperationError";
  }
}

export async function requestAssetOperation<T>(
  path: string,
  method: "POST" | "PUT" | "DELETE",
  body?: unknown,
  isCurrent?: () => boolean,
): Promise<T> {
  if (isCurrent && !isCurrent()) throw new AssetOperationError("身份已变化，请重新打开当前资产列表。");
  let response: Response;
  try {
    response = await fetch(path, {
      method,
      headers: body === undefined ? undefined : { "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    throw new AssetOperationError("请求结果未知，请先刷新列表核对，勿直接重复提交。", true);
  }
  let data: unknown;
  try {
    data = await response.json();
  } catch {
    throw new AssetOperationError("响应无法确认，请先刷新列表核对，勿直接重复提交。", true);
  }
  if (!response.ok) {
    const detail = data && typeof data === "object" && "detail" in data ? data.detail : null;
    if (detail === "Credential encryption is not configured") {
      throw new AssetOperationError("凭据加密尚未配置，请联系管理员。");
    }
    const inspect = response.status >= 500 || Boolean(
      detail && typeof detail === "object" && "inspection_required" in detail && detail.inspection_required,
    );
    const message = inspect
      ? "操作结果未确认，请先刷新列表核对，勿直接重复提交。"
      : response.status === 401 || response.status === 403
        ? "当前权限已失效，请重新验证身份。"
        : response.status === 404
          ? "所选资源已不可用，请重新选择。"
          : response.status === 409
            ? "配置冲突或仍被引用，请核对后修改。"
            : "配置未保存，请检查输入后重试。";
    throw new AssetOperationError(message, inspect);
  }
  if (isCurrent && !isCurrent()) throw new AssetOperationError("身份已变化，请核对原操作结果。", true);
  const result = data && typeof data === "object" ? data as Record<string, unknown> : null;
  const valid = method === "DELETE"
    ? result?.status === "ok"
    : path.endsWith("/test-connection")
      ? result?.status === "ok" || result?.status === "error"
      : typeof result?.id === "string" && result.id.length > 0;
  if (!valid) throw new AssetOperationError("响应结果未确认，请先刷新列表核对。", true);
  return data as T;
}
