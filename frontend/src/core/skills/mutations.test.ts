import { afterEach, expect, it, vi } from "vitest";

import { patchPersonalSkill, updateTenantSkill } from "./api";
import {
  SkillMutationError,
  readSkillMutationResponse,
  skillMutationMessage,
} from "./mutations";
vi.mock("@/core/api/auth-client", () => ({
  getAuthHeaders: async () =>
    new Headers({ Authorization: "Bearer fixture", "X-Tenant-Id": "tenant-a" }),
}));
vi.mock("@/core/config", () => ({
  getBackendBaseURL: () => "http://localhost:8001",
}));
afterEach(() => vi.unstubAllGlobals());
it("preserves resource identity and unknown inspection without converting detail into an object string", async () => {
  const response = new Response(
    JSON.stringify({
      detail: {
        message: "Inspect completed native edit",
        resource_id: "skill:current",
        inspection_required: true,
      },
    }),
    { status: 503 },
  );
  await expect(readSkillMutationResponse(response)).rejects.toMatchObject({
    status: 503,
    resourceId: "skill:current",
    inspectionRequired: true,
    message: "Inspect completed native edit",
  });
});
it.each([401, 403, 409])(
  "keeps definitive rejection %s separate from unknown",
  async (status) => {
    await expect(
      readSkillMutationResponse(
        new Response(JSON.stringify({ detail: "Rejected" }), { status }),
      ),
    ).rejects.toMatchObject({
      status,
      inspectionRequired: false,
      message: "Rejected",
    });
    expect(
      skillMutationMessage(new SkillMutationError(status), false),
    ).not.toContain("uncertain");
  },
);
it("incomplete successful response and network interruption require inspection", async () => {
  await expect(
    readSkillMutationResponse(new Response("broken")),
  ).rejects.toMatchObject({ status: 503, inspectionRequired: true });
  expect(
    skillMutationMessage(new TypeError("Failed to fetch"), false),
  ).toContain("inspect");
});
it("sends selected instance and loaded content digest with the owned personal edit", async () => {
  const fetch = vi
    .fn()
    .mockResolvedValue(new Response(JSON.stringify({ name: "demo" })));
  vi.stubGlobal("fetch", fetch);
  const input = {
    expected_resource_id: "skill:current",
    expected_file_sha256: "a".repeat(64),
    instructions: "Reviewed body",
  };
  await patchPersonalSkill("demo", input);
  expect(fetch).toHaveBeenCalledWith(
    "http://localhost:8001/api/skills/personal/demo",
    {
      method: "PATCH",
      headers: expect.any(Headers),
      body: JSON.stringify(input),
    },
  );
});

it("sends concrete enablement and parses structured unknown without retry", async () => {
  const fetch = vi
    .fn()
    .mockResolvedValue(
      new Response(
        JSON.stringify({
          detail: {
            message: "Inspect toggle",
            resource_id: "skill:current",
            inspection_required: true,
          },
        }),
        { status: 503 },
      ),
    );
  vi.stubGlobal("fetch", fetch);
  await expect(
    updateTenantSkill("demo", false, { expectedResourceId: "skill:current" }),
  ).rejects.toMatchObject({
    status: 503,
    resourceId: "skill:current",
    inspectionRequired: true,
  });
  expect(fetch).toHaveBeenCalledOnce();
  expect(fetch.mock.calls[0]?.[1]?.body).toBe(
    JSON.stringify({ enabled: false, expected_resource_id: "skill:current" }),
  );
});

it("checks captured identity after asynchronous auth headers before dispatch", async () => {
  const fetch = vi.fn();
  vi.stubGlobal("fetch", fetch);
  await expect(
    updateTenantSkill("demo", true, {
      expectedResourceId: "public:current",
      isCurrent: () => false,
    }),
  ).rejects.toMatchObject({ status: 401 });
  expect(fetch).not.toHaveBeenCalled();
});
