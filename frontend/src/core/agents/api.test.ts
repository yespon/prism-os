import { afterEach, beforeEach, expect, it, vi } from "vitest";

import { AgentMutationError, createAgent, updateAgent } from "./api";
const auth = vi.hoisted(() => ({ headers: vi.fn() }));
vi.mock("@/core/api/auth-client", () => ({
  getAuthHeaders: auth.headers,
  fetchAuthApi: vi.fn(),
}));
vi.mock("@/core/config", () => ({ getBackendBaseURL: () => "http://gateway" }));
const fetchMock = vi.fn();
beforeEach(() => {
  vi.clearAllMocks();
  auth.headers.mockResolvedValue(new Headers());
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => vi.unstubAllGlobals());
it("stops before dispatch if auth loading changed the current draft identity", async () => {
  let current = true;
  auth.headers.mockImplementation(async () => {
    current = false;
    return new Headers();
  });
  await expect(
    createAgent({ name: "demo" }, { isCurrent: () => current }),
  ).rejects.toBeInstanceOf(AgentMutationError);
  expect(fetchMock).not.toHaveBeenCalled();
});
it("sends explicit source selection and native revision conditions", async () => {
  fetchMock.mockResolvedValue(Response.json({ id: "agent-id" }));
  const request = {
    expected_agent_id: "agent-id",
    expected_revision: "revision",
    skill_binding_mode: "selected" as const,
    skill_resources: [
      {
        name: "demo",
        scope: "personal" as const,
        resource_id: "skill:current",
      },
    ],
  };
  await updateAgent("demo", request);
  expect(JSON.parse(fetchMock.mock.calls[0]![1].body)).toEqual(request);
});
it("keeps commit/response uncertainty separate from definitive rejection", async () => {
  fetchMock.mockResolvedValueOnce(
    Response.json({ detail: "stale" }, { status: 409 }),
  );
  await expect(updateAgent("demo", {})).rejects.toMatchObject({
    inspectionRequired: false,
    status: 409,
  });
  fetchMock.mockResolvedValueOnce(
    Response.json({ detail: "unknown" }, { status: 503 }),
  );
  await expect(updateAgent("demo", {})).rejects.toMatchObject({
    inspectionRequired: true,
    status: 503,
  });
});
