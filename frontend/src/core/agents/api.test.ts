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

it("copies one concrete source version with explicitly reauthorized target resources", async () => {
  const { copyAgent } = await import("./api");
  fetchMock.mockResolvedValue(Response.json({ id: "copy-id" }));
  const request = {
    name: "new-copy", source_agent_id: "source-id", source_revision: "a".repeat(64), is_shared: true,
    skill_binding_mode: "selected" as const,
    skill_resources: [{name:"same-name",scope:"tenant" as const,resource_id:"target-current-instance"}],
  };
  await copyAgent("source/name",request);
  expect(fetchMock.mock.calls[0]![0]).toBe("http://gateway/api/agents/source%2Fname/copy");
  expect(JSON.parse(fetchMock.mock.calls[0]![1].body as string)).toEqual(request);
});

it("does not retry copying after an unknown response or a tenant identity switch", async () => {
  const { copyAgent } = await import("./api");
  const request = {name:"new-copy",source_agent_id:"source-id",source_revision:"a".repeat(64),is_shared:false,skill_binding_mode:"selected" as const,skill_resources:[]};
  fetchMock.mockResolvedValueOnce(new Response("unconfirmed",{status:503}));
  await expect(copyAgent("source",request)).rejects.toMatchObject({inspectionRequired:true});
  expect(fetchMock).toHaveBeenCalledTimes(1);
  let current = true;
  fetchMock.mockImplementationOnce(async () => {current=false;return Response.json({id:"new-copy"});});
  await expect(copyAgent("source",request,{isCurrent:()=>current})).rejects.toMatchObject({status:401});
  expect(fetchMock).toHaveBeenCalledTimes(2);
});


it("requires inspection when a copy request loses its network response", async () => {
  const { copyAgent } = await import("./api");
  fetchMock.mockRejectedValueOnce(new TypeError("connection lost after dispatch"));
  await expect(copyAgent("source", {
    name: "copy", source_agent_id: "source-id", source_revision: "a".repeat(64),
    is_shared: false, skill_binding_mode: "selected", skill_resources: [],
  })).rejects.toMatchObject({ inspectionRequired: true, status: 503 });
  expect(fetchMock).toHaveBeenCalledTimes(1);
});
