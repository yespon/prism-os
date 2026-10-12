import { beforeEach, afterEach, expect, it, vi } from "vitest";

import { installSkill } from "./api";
import {
  SkillImportError,
  readSkillImportResponse,
  skillImportErrorMessage,
  changeSkillImportOperation,
} from "./imports";
const mock = vi.hoisted(() => ({ fetch: vi.fn() }));
vi.mock("@/core/api/auth-client", () => ({
  fetchAuthApi: mock.fetch,
  getAuthHeaders: async () => ({
    Authorization: "Bearer test",
    "X-Tenant-Id": "tenant-a",
  }),
}));
vi.mock("@/core/config", () => ({
  getBackendBaseURL: () => "http://localhost:8001",
}));
beforeEach(() => vi.clearAllMocks());
afterEach(() => vi.unstubAllGlobals());
it("preserves structured operation ID and message after uncertain registration", async () => {
  const response = new Response(
    JSON.stringify({
      detail: { message: "Registration uncertain", operation_id: "receipt-a" },
    }),
    { status: 503 },
  );
  await expect(readSkillImportResponse(response)).rejects.toMatchObject({
    status: 503,
    operationId: "receipt-a",
    message: "Registration uncertain",
  });
});
it.each([401, 403, 409])(
  "distinguishes a definitive rejection (%s) from unknown",
  (status) => {
    expect(
      skillImportErrorMessage(new SkillImportError(status), false),
    ).not.toContain("uncertain");
    expect(
      skillImportErrorMessage(new SkillImportError(503, "receipt-a"), false),
    ).toContain("uncertain");
  },
);
it("marks broken success JSON and network interruption as uncertain", async () => {
  await expect(
    readSkillImportResponse(new Response("broken", { status: 200 })),
  ).rejects.toMatchObject({ status: 503 });
  expect(
    skillImportErrorMessage(new TypeError("Failed to fetch"), false),
  ).toContain("inspect import records");
});
it("encodes operation identifiers without sending target overrides", async () => {
  mock.fetch.mockResolvedValue(
    new Response(JSON.stringify({ registered: true })),
  );
  const controller = new AbortController();
  await changeSkillImportOperation(
    "tenant",
    "id/other",
    "recover",
    controller.signal,
  );
  expect(mock.fetch).toHaveBeenCalledWith(
    "/api/tenants/skills/imports/id%2Fother/recover",
    { method: "POST", signal: controller.signal },
  );
});
it("keeps thread install failure compatible with its string message contract and exposes the receipt", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          detail: {
            message: "Registration uncertain",
            operation_id: "receipt-a",
          },
        }),
        { status: 503 },
      ),
    ),
  );
  expect(
    await installSkill({ thread_id: "thread-a", path: "demo.zip" }),
  ).toEqual({
    success: false,
    skill_name: "",
    message: "Registration uncertain",
    operation_id: "receipt-a",
  });
});
