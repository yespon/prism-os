import { afterEach, describe, expect, it, vi } from "vitest";

import { AssetOperationError, requestAssetOperation } from "./assets-api";

afterEach(() => vi.unstubAllGlobals());

describe("native asset operations", () => {
  it("sends one request and returns a confirmed result", async () => {
    const fetch = vi.fn().mockResolvedValue(new Response(JSON.stringify({ id: "owned" })));
    vi.stubGlobal("fetch", fetch);
    await expect(requestAssetOperation("/api/v1/assets/keychains", "POST", { name: "owned" })).resolves.toEqual({ id: "owned" });
    expect(fetch).toHaveBeenCalledTimes(1);
  });

  it.each([401, 403, 404, 409, 422])("refuses a known %s response without presenting success", async status => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({ detail: "private server detail" }), { status })));
    await expect(requestAssetOperation("/api/v1/assets/local", "POST", {})).rejects.toMatchObject({ inspectionRequired: false });
  });

  it("keeps encryption setup failure distinct from unknown publication", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({ detail: "Credential encryption is not configured" }), { status: 503 })));
    await expect(requestAssetOperation("/api/v1/assets/keychains", "POST", {})).rejects.toMatchObject({ inspectionRequired: false, message: "凭据加密尚未配置，请联系管理员。" });
  });

  it.each(["network", "invalid-json", "server-unknown"])("does not replay %s outcomes or echo private input", async scenario => {
    expect.assertions(4);
    const fetch = vi.fn();
    if (scenario === "network") fetch.mockRejectedValue(new Error("private-token"));
    else fetch.mockResolvedValue(new Response(scenario === "invalid-json" ? "private-token" : JSON.stringify({ detail: { inspection_required: true, message: "private-token" } }), { status: scenario === "invalid-json" ? 200 : 503 }));
    vi.stubGlobal("fetch", fetch);
    try { await requestAssetOperation("/api/v1/assets/local", "POST", { password: "private-token" }); }
    catch (error) {
      expect(error).toBeInstanceOf(AssetOperationError);
      expect((error as AssetOperationError).inspectionRequired).toBe(true);
      expect((error as Error).message).not.toContain("private-token");
    }
    expect(fetch).toHaveBeenCalledTimes(1);
  });

  it("refuses changed identity before dispatch", async () => {
    const fetch = vi.fn(); vi.stubGlobal("fetch", fetch);
    await expect(requestAssetOperation("/api/v1/assets/local", "POST", {}, () => false)).rejects.toMatchObject({ inspectionRequired: false });
    expect(fetch).not.toHaveBeenCalled();
  });

  it("discards a result after identity changes", async () => {
    let current = true;
    vi.stubGlobal("fetch", vi.fn().mockImplementation(async () => {
      current = false;
      return new Response(JSON.stringify({ id: "private-old-result" }));
    }));
    await expect(requestAssetOperation("/api/v1/assets/local", "POST", {}, () => current)).rejects.toMatchObject({ inspectionRequired: true });
  });
});

it("does not accept a successful HTTP status without the expected resource fact", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("null")));
  await expect(requestAssetOperation("/api/v1/assets/local", "POST", {})).rejects.toMatchObject({ inspectionRequired: true });
});
