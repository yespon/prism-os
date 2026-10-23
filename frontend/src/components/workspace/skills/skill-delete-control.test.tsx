import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import type { SkillDeletionPreflight } from "@/core/skills/deletions";
import { SkillMutationError } from "@/core/skills/mutations";

import { SkillDeleteControl } from "./skill-delete-control";

const mock = vi.hoisted(() => ({
  key: "tenant-a/user-a",
  current: true,
  share: false,
  load: vi.fn(),
  remove: vi.fn(),
}));
vi.mock("@/core/skills/import-context", () => ({
  useSkillImportContext: () => ({
    key: mock.key,
    identityReady: true,
    canShare: mock.share,
    isCurrent: () => mock.current,
  }),
}));
vi.mock("@/core/skills/deletions", () => ({
  loadSkillDeletionPreflight: mock.load,
  deleteOwnedSkill: mock.remove,
}));
vi.mock("./skill-import-operations", () => ({
  SkillImportOperations: () => <p>删除记录检查入口</p>,
}));
const plan: SkillDeletionPreflight = {
  name: "demo",
  resource_id: "skill:current",
  selected_resource_id: "skill:current",
  scope: "personal",
  target_kind: "owned",
  tree_sha256: "a".repeat(64),
  file_sha256: "b".repeat(64),
  members: 2,
  references: 0,
  eligible: true,
  physical_reclamation: true,
};
function deferred<T>() {
  let resolve!: (value: T) => void;
  return {
    promise: new Promise<T>((done) => {
      resolve = done;
    }),
    resolve: (value: T) => resolve(value),
  };
}
function view(client = new QueryClient()) {
  return render(
    <QueryClientProvider client={client}>
      <SkillDeleteControl
        name="demo"
        resourceId="skill:current"
        scope="personal"
      />
    </QueryClientProvider>,
  );
}
async function inspect() {
  fireEvent.click(screen.getByRole("button", { name: "删除 demo" }));
  fireEvent.click(screen.getByRole("button", { name: "核对当前删除范围" }));
  await screen.findByRole("button", { name: "确认删除当前实例" });
}
beforeEach(() => {
  vi.clearAllMocks();
  mock.key = "tenant-a/user-a";
  mock.current = true;
  mock.share = false;
  mock.load.mockResolvedValue(plan);
  mock.remove.mockResolvedValue(undefined);
});
afterEach(cleanup);
it("does not dispatch until the actual current instance and full tree are confirmed", async () => {
  view();
  await inspect();
  expect(mock.remove).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "确认删除当前实例" }));
  await screen.findByText("删除与回收已完成。");
  expect(mock.remove).toHaveBeenCalledWith(
    "personal",
    "demo",
    expect.objectContaining({
      expectedResourceId: plan.resource_id,
      expectedTreeSha256: plan.tree_sha256,
      expectedFileSha256: plan.file_sha256,
    }),
  );
});
it("blocks physical reclamation for unresolved Agent references and gives a review path", async () => {
  mock.load.mockResolvedValue({ ...plan, references: 1, eligible: false });
  view();
  await inspect();
  expect(
    screen.getByRole("button", { name: "确认删除当前实例" }),
  ).toBeDisabled();
  expect(screen.getByRole("link", { name: "查看 Agent" })).toHaveAttribute(
    "href",
    "/workspace/agents",
  );
  expect(mock.remove).not.toHaveBeenCalled();
});
it("preserves an unknown result across closing and reopening without another dispatch", async () => {
  mock.remove.mockRejectedValue(
    new SkillMutationError(
      503,
      plan.resource_id,
      true,
      "unknown",
      "operation-old",
    ),
  );
  view();
  await inspect();
  fireEvent.click(screen.getByRole("button", { name: "确认删除当前实例" }));
  await screen.findByText("operation-old");
  fireEvent.keyDown(screen.getByRole("dialog"), { key: "Escape" });
  await waitFor(() =>
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument(),
  );
  fireEvent.click(screen.getByRole("button", { name: "删除 demo" }));
  expect(screen.getByText("删除记录检查入口")).toBeInTheDocument();
  expect(
    screen.queryByRole("button", { name: "核对当前删除范围" }),
  ).not.toBeInTheDocument();
  expect(mock.remove).toHaveBeenCalledTimes(1);
});
it("ignores late preflight after an identity change", async () => {
  const pending = deferred<SkillDeletionPreflight>();
  mock.load.mockReturnValue(pending.promise);
  const result = view();
  fireEvent.click(screen.getByRole("button", { name: "删除 demo" }));
  fireEvent.click(screen.getByRole("button", { name: "核对当前删除范围" }));
  mock.key = "tenant-b/user-b";
  result.rerender(
    <QueryClientProvider client={new QueryClient()}>
      <SkillDeleteControl
        name="demo"
        resourceId="skill:current"
        scope="personal"
      />
    </QueryClientProvider>,
  );
  await act(async () => pending.resolve(plan));
  expect(
    screen.queryByRole("button", { name: "确认删除当前实例" }),
  ).not.toBeInTheDocument();
});
it("suppresses late deletion cache effects after the confirmation is closed", async () => {
  const pending = deferred<void>();
  mock.remove.mockReturnValue(pending.promise);
  const client = new QueryClient();
  const invalidate = vi.spyOn(client, "invalidateQueries");
  view(client);
  await inspect();
  fireEvent.click(screen.getByRole("button", { name: "确认删除当前实例" }));
  fireEvent.keyDown(screen.getByRole("dialog"), { key: "Escape" });
  await act(async () => pending.resolve());
  expect(invalidate).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "删除 demo" }));
  expect(screen.getByText("删除记录检查入口")).toBeInTheDocument();
});
it("requires current tenant administration for shared deletion", () => {
  render(
    <QueryClientProvider client={new QueryClient()}>
      <SkillDeleteControl
        name="demo"
        resourceId="skill:current"
        scope="tenant"
      />
    </QueryClientProvider>,
  );
  expect(screen.getByRole("button", { name: "删除 demo" })).toBeDisabled();
});

it("allows a fresh inspection after a definitive pre-mutation rejection", async () => {
  mock.remove.mockRejectedValue(new SkillMutationError(409, plan.resource_id, false, "Current reference conflict"));
  view(); await inspect(); fireEvent.click(screen.getByRole("button", { name: "确认删除当前实例" }));
  await screen.findByText("删除未执行。请重新核对当前实例与权限后再确认。");
  expect(screen.getByRole("button", { name: "核对当前删除范围" })).not.toBeDisabled();
  expect(screen.queryByText("删除记录检查入口")).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "核对当前删除范围" }));
  await screen.findByRole("button", { name: "确认删除当前实例" });
  expect(mock.load).toHaveBeenCalledTimes(2);
});
