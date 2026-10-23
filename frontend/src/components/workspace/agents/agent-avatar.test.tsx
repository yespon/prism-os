import { act, cleanup, render, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import { AgentAvatar } from "./agent-avatar";

const mock = vi.hoisted(() => ({
  tenant: "tenant-a",
  fetch: vi.fn(),
  createURL: vi.fn(),
  revokeURL: vi.fn(),
}));
vi.mock("@/core/api/auth-client", () => ({ fetchAuthApi: mock.fetch }));
vi.mock("@/core/agents/hooks", () => ({ useTenantKey: () => mock.tenant }));
const NativeURL = URL;
function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((done) => {
    resolve = done;
  });
  return { promise, resolve };
}
beforeEach(() => {
  vi.resetAllMocks();
  mock.tenant = "tenant-a";
  mock.createURL.mockReturnValue("blob:avatar");
  vi.stubGlobal(
    "URL",
    class extends NativeURL {
      static createObjectURL = mock.createURL;
      static revokeObjectURL = mock.revokeURL;
    },
  );
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

it("ignores a late avatar from a previous tenant", async () => {
  const previous = deferred<Response>();
  mock.fetch
    .mockReturnValueOnce(previous.promise)
    .mockResolvedValueOnce(new Response("current image"));
  const view = render(<AgentAvatar avatarId="personas:INTJ" />);
  const signal = mock.fetch.mock.calls[0]?.[1].signal as AbortSignal;
  mock.tenant = "tenant-b";
  view.rerender(<AgentAvatar avatarId="personas:INTJ" />);
  await waitFor(() =>
    expect(view.container.querySelector("img")).toHaveAttribute(
      "src",
      "blob:avatar",
    ),
  );
  await act(async () => previous.resolve(new Response("old image")));
  expect(signal.aborted).toBe(true);
  expect(mock.createURL).toHaveBeenCalledTimes(1);
});
it("hides and releases the old image immediately when the avatar changes", async () => {
  const next = deferred<Response>();
  mock.fetch
    .mockResolvedValueOnce(new Response("first"))
    .mockReturnValueOnce(next.promise);
  const view = render(<AgentAvatar avatarId="personas:INTJ" />);
  await waitFor(() =>
    expect(view.container.querySelector("img")).not.toBeNull(),
  );
  view.rerender(<AgentAvatar avatarId="personas:ENFP" />);
  expect(view.container.querySelector("img")).toBeNull();
  expect(mock.revokeURL).toHaveBeenCalledWith("blob:avatar");
  await act(async () => next.resolve(new Response("", { status: 403 })));
  expect(view.container.querySelector("img")).toBeNull();
});
it("does not create an object URL after unmount while reading the blob", async () => {
  const blob = deferred<Blob>();
  mock.fetch.mockResolvedValue({ ok: true, blob: () => blob.promise });
  const view = render(<AgentAvatar avatarId="personas:INTJ" />);
  await act(async () => {
    // flush microtasks
  });
  view.unmount();
  await act(async () => blob.resolve(new Blob(["svg"])));
  expect(mock.createURL).not.toHaveBeenCalled();
  expect((mock.fetch.mock.calls[0]?.[1].signal as AbortSignal).aborted).toBe(
    true,
  );
});
it("uses the default icon without a request and releases accepted images on close", async () => {
  const view = render(<AgentAvatar />);
  expect(mock.fetch).not.toHaveBeenCalled();
  mock.fetch.mockResolvedValueOnce(new Response("svg"));
  view.rerender(<AgentAvatar avatarId="personas:INTJ" />);
  await waitFor(() =>
    expect(view.container.querySelector("img")).not.toBeNull(),
  );
  view.unmount();
  expect(mock.revokeURL).toHaveBeenCalledWith("blob:avatar");
});
