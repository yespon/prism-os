import { beforeEach, describe, expect, it, vi } from "vitest";

import { fetchAuthApi } from "@/core/api/auth-client";

import {
  downloadResourceArchive,
  installSourceSkill,
  loadAgentCatalog,
  loadResourcePreflight,
  previewAgentTemplate,
} from "./catalog";

vi.mock("@/core/api/auth-client", () => ({ fetchAuthApi: vi.fn() }));

describe("Agent catalog host API", () => {
  beforeEach(() => vi.resetAllMocks());
  it("loads templates and personas through the existing authenticated client", async () => {
    vi.mocked(fetchAuthApi).mockResolvedValueOnce(
      new Response(
        JSON.stringify({ templates: [{ id: "expert:general-assistant" }] }),
      ),
    );
    vi.mocked(fetchAuthApi).mockResolvedValueOnce(
      new Response(JSON.stringify({ personas: [{ code: "INTJ" }] })),
    );
    const result = await loadAgentCatalog("zh");
    expect(result.templates[0]?.id).toBe("expert:general-assistant");
    expect(result.personas[0]?.code).toBe("INTJ");
    expect(fetchAuthApi).toHaveBeenCalledWith(
      "/api/agent-catalog/templates?locale=zh",
      { signal: undefined },
    );
    expect(fetchAuthApi).toHaveBeenCalledWith("/api/agent-catalog/personas", {
      signal: undefined,
    });
  });
  it("encodes template identifiers and preserves the requested language", async () => {
    vi.mocked(fetchAuthApi).mockResolvedValueOnce(
      new Response(JSON.stringify({ system_prompt: "Pinned instructions" })),
    );
    const preview = await previewAgentTemplate(
      "subagent:engineering.backend",
      "en",
    );
    expect(preview.system_prompt).toBe("Pinned instructions");
    expect(fetchAuthApi).toHaveBeenCalledWith(
      "/api/agent-catalog/templates/subagent%3Aengineering.backend?locale=en",
      { signal: undefined },
    );
  });
  it("fails a partially unavailable catalog instead of presenting it as complete", async () => {
    vi.mocked(fetchAuthApi).mockResolvedValueOnce(
      new Response("", { status: 403 }),
    );
    vi.mocked(fetchAuthApi).mockResolvedValueOnce(
      new Response(JSON.stringify({ personas: [] })),
    );
    await expect(loadAgentCatalog("en")).rejects.toThrow();
  });
});

describe("Resource preflight and source archive host API", () => {
  beforeEach(() => vi.resetAllMocks());
  it("requests scoped installation facts with encoded identifiers and abort signal", async () => {
    const signal = new AbortController().signal;
    vi.mocked(fetchAuthApi).mockResolvedValueOnce(
      new Response(JSON.stringify({ installation_checked: true })),
    );
    expect(
      (await loadResourcePreflight("expert:cloud/path", "en", signal))
        .installation_checked,
    ).toBe(true);
    expect(fetchAuthApi).toHaveBeenCalledWith(
      "/api/agent-catalog/templates/expert%3Acloud%2Fpath/resources?locale=en&check_installation=true",
      { signal },
    );
  });
  it("downloads bytes using authenticated fetch and encodes both identifiers", async () => {
    const signal = new AbortController().signal;
    vi.mocked(fetchAuthApi).mockResolvedValueOnce(
      new Response("source-zip", {
        headers: { "Content-Type": "application/zip" },
      }),
    );
    const blob = await downloadResourceArchive(
      "expert:cloud",
      "skill:refs/path",
      "zh",
      signal,
    );
    expect(await blob.text()).toBe("source-zip");
    expect(fetchAuthApi).toHaveBeenCalledWith(
      "/api/agent-catalog/templates/expert%3Acloud/resources/skill%3Arefs%2Fpath/archive?locale=zh",
      { signal },
    );
  });
  it("rejects denied archives rather than saving an error response as a zip", async () => {
    vi.mocked(fetchAuthApi).mockResolvedValueOnce(
      new Response("Denied", { status: 403 }),
    );
    await expect(
      downloadResourceArchive(
        "expert:cloud",
        "skill:one",
        "en",
        new AbortController().signal,
      ),
    ).rejects.toThrow("Source archive unavailable");
  });
});

it("installs only the confirmed fixed source into the server-selected actor scope", async () => {
  vi.mocked(fetchAuthApi).mockResolvedValueOnce(
    new Response(
      JSON.stringify({ operation_id: "receipt-a", registered: true }),
    ),
  );
  const controller = new AbortController();
  await installSourceSkill(
    "expert:a/b",
    "resource:a/b",
    "zh",
    "personal",
    "a".repeat(64),
    controller.signal,
  );
  expect(fetchAuthApi).toHaveBeenCalledWith(
    "/api/agent-catalog/templates/expert%3Aa%2Fb/resources/resource%3Aa%2Fb/install?locale=zh",
    {
      method: "POST",
      signal: controller.signal,
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        scope: "personal",
        bundle_sha256: "a".repeat(64),
      }),
    },
  );
});
