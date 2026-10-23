import { afterEach, beforeEach, expect, it, vi } from "vitest";

import { deleteOwnedSkill, loadSkillDeletionPreflight } from "./deletions";
import { SkillMutationError } from "./mutations";

const auth = vi.hoisted(() => ({ headers: vi.fn() }));
vi.mock("@/core/api/auth-client", () => ({ getAuthHeaders: auth.headers }));
vi.mock("@/core/config", () => ({ getBackendBaseURL: () => "http://gateway" }));
const fetchMock = vi.fn();
beforeEach(() => {
  vi.clearAllMocks();
  auth.headers.mockResolvedValue(new Headers());
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => vi.unstubAllGlobals());
it("encodes the selected generation and full tree while accepting an empty 204", async () => {
  fetchMock.mockResolvedValue(new Response(null, { status: 204 }));
  await deleteOwnedSkill("personal", "demo name", {
    expectedResourceId: "skill:old",
    expectedTreeSha256: "tree",
    expectedFileSha256: "main",
  });
  const [url, init] = fetchMock.mock.calls[0]!;
  expect(url).toContain("demo%20name?");
  expect(new URL(url).searchParams.get("expected_resource_id")).toBe(
    "skill:old",
  );
  expect(new URL(url).searchParams.get("expected_tree_sha256")).toBe("tree");
  expect(init.method).toBe("DELETE");
});
it("keeps structured unknown operation identity for inspection", async () => {
  fetchMock.mockResolvedValue(
    Response.json(
      {
        detail: {
          operation_id: "owned-op",
          inspection_required: true,
          resource_id: "skill:old",
        },
      },
      { status: 503 },
    ),
  );
  await expect(deleteOwnedSkill("tenant", "demo")).rejects.toMatchObject({
    status: 503,
    operationId: "owned-op",
    inspectionRequired: true,
  });
});
it("does not send if identity changed while authentication was being loaded", async () => {
  let current = true;
  auth.headers.mockImplementation(async () => {
    current = false;
    return new Headers();
  });
  await expect(
    deleteOwnedSkill("personal", "demo", { isCurrent: () => current }),
  ).rejects.toBeInstanceOf(SkillMutationError);
  expect(fetchMock).not.toHaveBeenCalled();
});
it("does not treat an unexpected successful payload as deletion completion", async () => {
  fetchMock.mockResolvedValue(Response.json({ ok: true }));
  await expect(deleteOwnedSkill("personal", "demo")).rejects.toMatchObject({
    inspectionRequired: true,
  });
});
it("rejects malformed preflight rather than enabling confirmation", async () => {
  fetchMock.mockResolvedValue(
    Response.json({
      name: "demo",
      scope: "personal",
      members: -1,
      references: 0,
      eligible: true,
    }),
  );
  await expect(
    loadSkillDeletionPreflight("personal", "demo", {}),
  ).rejects.toMatchObject({ inspectionRequired: true });
});
