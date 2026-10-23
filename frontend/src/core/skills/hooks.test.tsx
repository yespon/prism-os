import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import {
  useAvailableSkills,
  useTenantSkills,
  useUpdateTenantSkill,
} from "./hooks";
import { SkillMutationError } from "./mutations";


const mock = vi.hoisted(() => ({
  key: "tenant-a/user-a/session-a",
  ready: true,
  current: true,
  load: vi.fn(),
  tenant: vi.fn(),
  toggle: vi.fn(),
}));
vi.mock("@/core/skills/import-context", () => ({
  useSkillImportContext: () => ({
    key: mock.key,
    identityReady: mock.ready,
    isCurrent: () => mock.current,
  }),
}));
vi.mock("@/core/auth/hooks", () => ({
  useSession: () => ({ data: { user: { role: "user" } } }),
}));
vi.mock("./api", () => ({
  loadAvailableSkills: mock.load,
  loadTenantSkills: mock.tenant,
  updateTenantSkill: mock.toggle,
}));
beforeEach(() => {
  vi.clearAllMocks();
  mock.key = "tenant-a/user-a/session-a";
  mock.ready = mock.current = true;
});
afterEach(cleanup);
function wrapper(client: QueryClient) {
  return function Provider({ children }: { children: React.ReactNode }) {
    return (
      <QueryClientProvider client={client}>{children}</QueryClientProvider>
    );
  };
}
it.each(["available", "tenant"])(
  "never displays cached %s resources after tenant/user identity change",
  async (kind) => {
    const load = kind === "available" ? mock.load : mock.tenant;
    load.mockResolvedValueOnce([{ name: "private-old" }]);
    let resolve!: (value: { name: string }[]) => void;
    load.mockReturnValueOnce(
      new Promise((done) => {
        resolve = done;
      }),
    );
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    const view = renderHook(
      () => (kind === "available" ? useAvailableSkills() : useTenantSkills()),
      { wrapper: wrapper(client) },
    );
    await waitFor(() =>
      expect(view.result.current.skills[0]?.name).toBe("private-old"),
    );
    mock.key = "tenant-b/user-b/session-b";
    view.rerender();
    expect(view.result.current.skills).toEqual([]);
    await act(async () => resolve([{ name: "new-only" }]));
    await waitFor(() =>
      expect(view.result.current.skills[0]?.name).toBe("new-only"),
    );
  },
);

it("discards a late old-session response instead of populating the new cache", async () => {
  let resolveOld!: (value: { name: string }[]) => void;
  mock.load.mockReturnValueOnce(
    new Promise((done) => {
      resolveOld = done;
    }),
  );
  mock.load.mockResolvedValueOnce([{ name: "new-session" }]);
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  const view = renderHook(useAvailableSkills, { wrapper: wrapper(client) });
  await waitFor(() => expect(mock.load).toHaveBeenCalledOnce());
  const signal = mock.load.mock.calls[0]?.[0] as AbortSignal;
  mock.key = "tenant-a/user-b/session-b";
  view.rerender();
  await waitFor(() =>
    expect(view.result.current.skills[0]?.name).toBe("new-session"),
  );
  await act(async () => resolveOld([{ name: "private-late" }]));
  expect(signal.aborted).toBe(true);
  expect(view.result.current.skills[0]?.name).toBe("new-session");
});
it("hides cached data and does not read when the cached session mismatches the live token", async () => {
  mock.load.mockResolvedValueOnce([{ name: "cached" }]);
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  const view = renderHook(useAvailableSkills, { wrapper: wrapper(client) });
  await waitFor(() => expect(view.result.current.skills).toHaveLength(1));
  mock.ready = mock.current = false;
  view.rerender();
  expect(view.result.current.skills).toEqual([]);
  expect(mock.load).toHaveBeenCalledOnce();
});

it("blocks another same-resource toggle after unknown until a successful current list inspection", async () => {
  mock.load.mockResolvedValue([{ name: "demo", resource_id: "skill:current" }]);
  mock.toggle.mockRejectedValueOnce(
    new SkillMutationError(503, "skill:current", true),
  );
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  const view = renderHook(
    () => ({ list: useAvailableSkills(), toggle: useUpdateTenantSkill() }),
    { wrapper: wrapper(client) },
  );
  await waitFor(() => expect(view.result.current.list.skills).toHaveLength(1));
  await act(async () => {
    await expect(
      view.result.current.toggle.mutateAsync({
        skillName: "demo",
        enabled: false,
        expectedResourceId: "skill:current",
      }),
    ).rejects.toMatchObject({ status: 503 });
  });
  expect(view.result.current.toggle.enablementNeedsInspection).toBe(true);
  expect(view.result.current.toggle.canToggleResource("skill:current")).toBe(
    false,
  );
  await act(async () => {
    await expect(
      view.result.current.toggle.mutateAsync({
        skillName: "demo",
        enabled: false,
        expectedResourceId: "skill:current",
      }),
    ).rejects.toMatchObject({ status: 409 });
  });
  expect(mock.toggle).toHaveBeenCalledOnce();
  mock.load.mockRejectedValueOnce(new Error("current read unavailable"));
  await act(async () => {
    await expect(
      view.result.current.toggle.inspectEnablement(),
    ).rejects.toThrow("current read unavailable");
  });
  expect(view.result.current.toggle.enablementNeedsInspection).toBe(true);
  mock.load.mockResolvedValue([
    { name: "demo", resource_id: "skill:current", enabled: false },
  ]);
  await act(async () => view.result.current.toggle.inspectEnablement());
  expect(view.result.current.toggle.enablementNeedsInspection).toBe(false);
  expect(view.result.current.toggle.canToggleResource("skill:current")).toBe(
    true,
  );
});

it("rejects old-identity dispatch and discards old toggle completion without invalidating the new cache", async () => {
  let resolve!: (value: unknown) => void;
  mock.toggle.mockReturnValue(
    new Promise((done) => {
      resolve = done;
    }),
  );
  const client = new QueryClient();
  const invalidate = vi.spyOn(client, "invalidateQueries");
  const view = renderHook(useUpdateTenantSkill, { wrapper: wrapper(client) });
  let result!: Promise<unknown>;
  act(() => {
    result = view.result.current.mutateAsync({
      skillName: "demo",
      enabled: false,
      expectedResourceId: "public:current",
    });
  });
  await waitFor(() => expect(mock.toggle).toHaveBeenCalledOnce());
  const options = mock.toggle.mock.calls[0]?.[2] as {
    isCurrent: () => boolean;
  };
  expect(options.isCurrent()).toBe(true);
  mock.key = "tenant-b/user-b/session-b";
  view.rerender();
  expect(options.isCurrent()).toBe(false);
  await act(async () => {
    resolve({ enabled: false });
    await expect(result).rejects.toMatchObject({ status: 401 });
  });
  expect(invalidate).not.toHaveBeenCalled();
  expect(view.result.current.enablementNeedsInspection).toBe(false);
  mock.current = false;
  await act(async () => {
    await expect(
      view.result.current.mutateAsync({
        skillName: "demo",
        enabled: true,
        expectedResourceId: "public:current",
      }),
    ).rejects.toMatchObject({ status: 401 });
  });
  expect(mock.toggle).toHaveBeenCalledOnce();
});

it("allows independent resources while serializing a selected instance", async () => {
  let resolve!: (value: unknown) => void;
  mock.toggle
    .mockReturnValueOnce(
      new Promise((done) => {
        resolve = done;
      }),
    )
    .mockResolvedValueOnce({ enabled: false });
  const client = new QueryClient();
  const view = renderHook(useUpdateTenantSkill, { wrapper: wrapper(client) });
  let pending!: Promise<unknown>;
  act(() => {
    pending = view.result.current.mutateAsync({
      skillName: "first",
      enabled: false,
      expectedResourceId: "skill:first",
    });
  });
  await waitFor(() =>
    expect(view.result.current.canToggleResource("skill:first")).toBe(false),
  );
  expect(view.result.current.canToggleResource("skill:other")).toBe(true);
  await act(async () => {
    await expect(
      view.result.current.mutateAsync({
        skillName: "first",
        enabled: false,
        expectedResourceId: "skill:first",
      }),
    ).rejects.toMatchObject({ status: 409 });
  });
  await act(async () => {
    await view.result.current.mutateAsync({
      skillName: "second",
      enabled: false,
      expectedResourceId: "skill:other",
    });
  });
  await act(async () => {
    resolve({ enabled: false });
    await pending;
  });
  expect(mock.toggle).toHaveBeenCalledTimes(2);
});
