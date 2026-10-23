import { afterEach, describe, expect, it, vi } from "vitest";

import { POST as approve } from "./chat/approve/route";
import { POST as invoke } from "./chat/route";
import { terminalGatewayHeaders } from "./gateway-headers";

afterEach(() => vi.unstubAllGlobals());

function request(body: unknown): Request {
  return {
    headers: new Headers({
      Cookie: "session=caller",
      Authorization: "Bearer caller-token",
      "X-Tenant-Id": "selected-tenant",
      "X-User-Id": "forged-user",
    }),
    json: async () => body,
  } as Request;
}

describe("terminal caller scope", () => {
  it("forwards only canonical authentication and tenant headers", () => {
    const headers = terminalGatewayHeaders(request({}));
    expect(headers.get("Cookie")).toBe("session=caller");
    expect(headers.get("Authorization")).toBe("Bearer caller-token");
    expect(headers.get("X-Tenant-Id")).toBe("selected-tenant");
    expect(headers.has("X-User-Id")).toBe(false);
  });

  it.each([
    ["invoke", invoke, "/api/v1/terminal/invoke"],
    ["approve", approve, "/api/v1/terminal/approve"],
  ] as const)("keeps caller scope and uncached SSE for %s", async (_, handler, suffix) => {
    const gateway = vi.fn().mockResolvedValue(new Response("data: actual-stream\n\n"));
    vi.stubGlobal("fetch", gateway);
    const response = await handler(request({ session_id: "thread", terminal_session_id: null, asset_id: null }));
    const [url, options] = gateway.mock.calls[0] as [string, RequestInit];
    expect(url.endsWith(suffix)).toBe(true);
    const headers = new Headers(options.headers);
    expect(headers.get("Authorization")).toBe("Bearer caller-token");
    expect(headers.get("X-Tenant-Id")).toBe("selected-tenant");
    expect(headers.get("Cookie")).toBe("session=caller");
    expect(response.headers.get("Cache-Control")).toBe("no-store");
    expect(await response.text()).toContain("actual-stream");
  });
});
