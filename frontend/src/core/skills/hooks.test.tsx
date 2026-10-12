import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import { useAvailableSkills, useTenantSkills } from "./hooks";

const mock = vi.hoisted(() => ({
  key: "tenant-a/user-a/session-a",
  ready: true,
  current: true,
  load: vi.fn(),
  tenant: vi.fn(),
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
