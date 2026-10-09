import { beforeEach, describe, expect, it, vi } from "vitest";

import { fetchAuthApi } from "@/core/api/auth-client";

import { loadAgentCatalog, previewAgentTemplate } from "./catalog";

vi.mock("@/core/api/auth-client", () => ({ fetchAuthApi: vi.fn() }));

describe("Agent catalog host API", () => {
  beforeEach(() => vi.resetAllMocks());
  it("loads templates and personas through the existing authenticated client", async () => {
    vi.mocked(fetchAuthApi).mockResolvedValueOnce(new Response(JSON.stringify({ templates: [{ id: "expert:general-assistant" }] })));
    vi.mocked(fetchAuthApi).mockResolvedValueOnce(new Response(JSON.stringify({ personas: [{ code: "INTJ" }] })));
    const result = await loadAgentCatalog("zh");
    expect(result.templates[0]?.id).toBe("expert:general-assistant");
    expect(result.personas[0]?.code).toBe("INTJ");
    expect(fetchAuthApi).toHaveBeenCalledWith("/api/agent-catalog/templates?locale=zh");
    expect(fetchAuthApi).toHaveBeenCalledWith("/api/agent-catalog/personas");
  });
  it("encodes template identifiers and preserves the requested language", async () => {
    vi.mocked(fetchAuthApi).mockResolvedValueOnce(new Response(JSON.stringify({ system_prompt: "Pinned instructions" })));
    const preview = await previewAgentTemplate("subagent:engineering.backend", "en");
    expect(preview.system_prompt).toBe("Pinned instructions");
    expect(fetchAuthApi).toHaveBeenCalledWith("/api/agent-catalog/templates/subagent%3Aengineering.backend?locale=en");
  });
  it("fails a partially unavailable catalog instead of presenting it as complete", async () => {
    vi.mocked(fetchAuthApi).mockResolvedValueOnce(new Response("", { status: 403 }));
    vi.mocked(fetchAuthApi).mockResolvedValueOnce(new Response(JSON.stringify({ personas: [] })));
    await expect(loadAgentCatalog("en")).rejects.toThrow();
  });
});
