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

import type { ResourcePreflightItem } from "@/core/agents/catalog";
import type * as SkillImports from "@/core/skills/imports";
import {
  SkillImportError,
  type SkillImportOperation,
} from "@/core/skills/imports";

import { SkillImportOperations } from "./skill-import-operations";
import { SourceSkillInstall } from "./source-skill-install";

const mock = vi.hoisted(() => ({
  key: "tenant-a/user-a/session-a",
  ready: true,
  share: false,
  current: true,
  install: vi.fn(),
  load: vi.fn(),
  change: vi.fn(),
}));
vi.mock("@/core/skills/import-context", () => ({
  useSkillImportContext: () => ({
    key: mock.key,
    identityReady: mock.ready,
    canShare: mock.share,
    isCurrent: () => mock.current,
  }),
}));
vi.mock("@/core/agents/catalog", () => ({ installSourceSkill: mock.install }));
vi.mock("@/core/skills/imports", async (importActual) => ({
  ...(await importActual<typeof SkillImports>()),
  loadSkillImportOperations: mock.load,
  changeSkillImportOperation: mock.change,
}));
const resource: ResourcePreflightItem = {
  id: "resource:source",
  kind: "skill_bundle",
  root: "skills/demo",
  bundle_sha256: "confirmed-source-digest",
  members: [],
  host_format: { status: "compatible" },
  host_adaptation: { status: "ready", name: "demo" },
  execution_ready: false,
};
const pendingOperation: SkillImportOperation = {
  operation_id: "operation-a",
  name: "demo",
  scope: "personal",
  state: "registration_pending",
  phase: "published",
  files_verified: true,
  registered: false,
  enabled: null,
  execution_ready: false,
};
function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((done) => {
    resolve = done;
  });
  return { promise, resolve };
}
function wrapped(
  node: React.ReactNode,
  client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  }),
) {
  return <QueryClientProvider client={client}>{node}</QueryClientProvider>;
}
const props = {
  templateId: "expert:source",
  resource,
  locale: "zh" as const,
  open: true,
  onInstalled: vi.fn(),
};
beforeEach(() => {
  vi.clearAllMocks();
  mock.key = "tenant-a/user-a/session-a";
  mock.ready = true;
  mock.share = false;
  mock.current = true;
  mock.install.mockResolvedValue({
    operation_id: "operation-a",
    registered: true,
  });
  mock.load.mockResolvedValue({ operations: [pendingOperation] });
  mock.change.mockResolvedValue({
    ...pendingOperation,
    registered: true,
    state: "registered",
  });
});
afterEach(cleanup);

it("requires explicit confirmation and sends only confirmed digest and personal scope", async () => {
  render(wrapped(<SourceSkillInstall {...props} />));
  expect(mock.install).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "安装 Skill…" }));
  expect(mock.install).not.toHaveBeenCalled();
  expect(
    screen.queryByRole("option", { name: "租户共享 Skill" }),
  ).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "确认安装" }));
  await screen.findByText(/已登记 Skill/);
  expect(mock.install).toHaveBeenCalledWith(
    "expert:source",
    "resource:source",
    "zh",
    "personal",
    "confirmed-source-digest",
    expect.any(AbortSignal),
  );
  expect(props.onInstalled).toHaveBeenCalledOnce();
});
it("allows current tenant admin to confirm shared installation", async () => {
  mock.share = true;
  render(wrapped(<SourceSkillInstall {...props} />));
  fireEvent.click(screen.getByRole("button", { name: "安装 Skill…" }));
  fireEvent.change(screen.getByLabelText("安装范围"), {
    target: { value: "tenant" },
  });
  fireEvent.click(screen.getByRole("button", { name: "确认安装" }));
  await screen.findByText(/已登记 Skill/);
  expect(mock.install.mock.calls[0]?.[3]).toBe("tenant");
});
it.each([401, 403, 409, 503])(
  "does not retry a rejected or uncertain installation (%s)",
  async (status) => {
    mock.install.mockRejectedValueOnce(
      new SkillImportError(status, status === 503 ? "operation-a" : undefined),
    );
    render(wrapped(<SourceSkillInstall {...props} />));
    fireEvent.click(screen.getByRole("button", { name: "安装 Skill…" }));
    fireEvent.click(screen.getByRole("button", { name: "确认安装" }));
    await screen.findByRole("link", { name: "检查导入记录" });
    expect(mock.install).toHaveBeenCalledOnce();
    expect(props.onInstalled).not.toHaveBeenCalled();
    if (status === 503) {
      expect(
        screen.getByRole("button", { name: "安装 Skill…" }),
      ).toBeDisabled();
      expect(screen.getByText(/operation-a/)).toBeInTheDocument();
    }
  },
);
it.each(["identity", "resource", "close", "locale"])(
  "drops confirmation and late mutation effects after %s change",
  async (kind) => {
    const request = deferred<{ operation_id: string; registered: boolean }>();
    mock.install.mockReturnValueOnce(request.promise);
    const client = new QueryClient();
    const invalidate = vi.spyOn(client, "invalidateQueries");
    const view = render(wrapped(<SourceSkillInstall {...props} />, client));
    fireEvent.click(screen.getByRole("button", { name: "安装 Skill…" }));
    fireEvent.click(screen.getByRole("button", { name: "确认安装" }));
    const signal = mock.install.mock.calls[0]?.[5] as AbortSignal;
    if (kind === "identity") mock.key = "tenant-a/user-b/session-b";
    view.rerender(
      wrapped(
        <SourceSkillInstall
          {...props}
          open={kind !== "close"}
          resource={
            kind === "resource"
              ? { ...resource, bundle_sha256: "new-source" }
              : resource
          }
          locale={kind === "locale" ? "en" : "zh"}
        />,
        client,
      ),
    );
    await act(async () =>
      request.resolve({ operation_id: "late", registered: true }),
    );
    expect(signal.aborted).toBe(true);
    expect(props.onInstalled).not.toHaveBeenCalled();
    expect(invalidate).not.toHaveBeenCalled();
    expect(screen.queryByText(/已登记 Skill/)).not.toBeInTheDocument();
  },
);
it("prevents installation when the live identity no longer matches", async () => {
  render(wrapped(<SourceSkillInstall {...props} />));
  fireEvent.click(screen.getByRole("button", { name: "安装 Skill…" }));
  mock.current = false;
  fireEvent.click(screen.getByRole("button", { name: "确认安装" }));
  expect(mock.install).not.toHaveBeenCalled();
});
it("loads records on demand and requires separate confirmation before recovery", async () => {
  render(wrapped(<SkillImportOperations scope="personal" locale="zh" />));
  expect(mock.load).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "检查导入记录" }));
  await screen.findByText(/文件已发布/);
  fireEvent.click(screen.getByRole("button", { name: "继续核对并登记" }));
  expect(mock.change).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "确认操作" }));
  await waitFor(() =>
    expect(mock.change).toHaveBeenCalledWith(
      "personal",
      "operation-a",
      "recover",
      expect.any(AbortSignal),
    ),
  );
  expect(mock.load).toHaveBeenCalledTimes(2);
});
it("offers abort for staged content and never for published or registered content", async () => {
  mock.load.mockResolvedValue({
    operations: [
      {
        ...pendingOperation,
        operation_id: "stage-a",
        state: "publication_pending",
        phase: "prepared",
        files_verified: false,
        staged_files_verified: true,
      },
      {
        ...pendingOperation,
        operation_id: "disabled",
        registered: true,
        state: "registered",
        enabled: false,
      },
    ],
  });
  render(wrapped(<SkillImportOperations scope="personal" locale="zh" />));
  fireEvent.click(screen.getByRole("button", { name: "检查导入记录" }));
  await screen.findByText(/已禁用/);
  expect(screen.getAllByRole("button", { name: "放弃自有暂存" })).toHaveLength(
    1,
  );
  fireEvent.click(screen.getByRole("button", { name: "放弃自有暂存" }));
  expect(mock.change).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "确认操作" }));
  await waitFor(() => expect(mock.change.mock.calls[0]?.[2]).toBe("abort"));
});
it("blocks shared records without current tenant admin and clears old records immediately", async () => {
  mock.share = true;
  const view = render(
    wrapped(<SkillImportOperations scope="tenant" locale="zh" />),
  );
  fireEvent.click(screen.getByRole("button", { name: "检查导入记录" }));
  await screen.findByText(/文件已发布/);
  mock.share = false;
  mock.key = "tenant-b/user-a/no-admin";
  view.rerender(wrapped(<SkillImportOperations scope="tenant" locale="zh" />));
  expect(screen.queryByText(/文件已发布/)).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: "检查导入记录" })).toBeDisabled();
});
it("unknown recovery keeps records and requires explicit inspection before another action", async () => {
  mock.change.mockRejectedValueOnce(new SkillImportError(503));
  render(wrapped(<SkillImportOperations scope="personal" locale="zh" />));
  fireEvent.click(screen.getByRole("button", { name: "检查导入记录" }));
  await screen.findByText(/文件已发布/);
  fireEvent.click(screen.getByRole("button", { name: "继续核对并登记" }));
  fireEvent.click(screen.getByRole("button", { name: "确认操作" }));
  await screen.findByText(/结果暂无法确认或存在冲突/);
  expect(mock.change).toHaveBeenCalledOnce();
  expect(
    screen.queryByRole("button", { name: "继续核对并登记" }),
  ).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "检查导入记录" }));
  await screen.findByRole("button", { name: "继续核对并登记" });
});

it.each(["read", "recover"])(
  "discards late %s effects after identity change",
  async (kind) => {
    const request = deferred<
      SkillImportOperation | { operations: SkillImportOperation[] }
    >();
    const client = new QueryClient();
    const invalidate = vi.spyOn(client, "invalidateQueries");
    if (kind === "read") mock.load.mockReturnValueOnce(request.promise);
    else mock.change.mockReturnValueOnce(request.promise);
    const view = render(
      wrapped(<SkillImportOperations scope="personal" locale="zh" />, client),
    );
    fireEvent.click(screen.getByRole("button", { name: "检查导入记录" }));
    if (kind === "recover") {
      await screen.findByText(/文件已发布/);
      fireEvent.click(screen.getByRole("button", { name: "继续核对并登记" }));
      fireEvent.click(screen.getByRole("button", { name: "确认操作" }));
    }
    mock.key = "tenant-b/user-b/session-b";
    view.rerender(
      wrapped(<SkillImportOperations scope="personal" locale="zh" />, client),
    );
    await act(async () =>
      request.resolve(
        kind === "read" ? { operations: [pendingOperation] } : pendingOperation,
      ),
    );
    expect(screen.queryByText(/文件已发布/)).not.toBeInTheDocument();
    expect(invalidate).not.toHaveBeenCalled();
    expect(mock.load).toHaveBeenCalledTimes(1);
  },
);

it("appends pages once and displays retained receipts without treating them as execution rights", async () => {
  mock.load.mockResolvedValueOnce({
    operations: [pendingOperation],
    next_cursor: "next-a",
    total: 126,
  });
  mock.load.mockResolvedValueOnce({
    operations: [
      pendingOperation,
      {
        ...pendingOperation,
        operation_id: "old-operation",
        name: "old-pending",
      },
    ],
    next_cursor: null,
    total: 126,
  });
  render(wrapped(<SkillImportOperations scope="personal" locale="zh" />));
  fireEvent.click(screen.getByRole("button", { name: "检查导入记录" }));
  await screen.findByRole("button", { name: "加载更多记录" });
  fireEvent.click(screen.getByRole("button", { name: "加载更多记录" }));
  await screen.findByText(/old-pending/);
  expect(mock.load).toHaveBeenLastCalledWith(
    "personal",
    expect.any(AbortSignal),
    "next-a",
  );
  expect(screen.getAllByText("operation-a")).toHaveLength(1);
  expect(screen.getByText(/已检查 2 条 \/ 当前 126 条/)).toBeInTheDocument();
  expect(
    screen.queryByRole("button", { name: "加载更多记录" }),
  ).not.toBeInTheDocument();
});
it("preserves inspected pages after a transient more-page read failure and can retry that cursor", async () => {
  mock.load.mockResolvedValueOnce({
    operations: [pendingOperation],
    next_cursor: "next-a",
    total: 126,
  });
  mock.load.mockRejectedValueOnce(new SkillImportError(503));
  mock.load.mockResolvedValueOnce({
    operations: [
      { ...pendingOperation, operation_id: "old", name: "old-pending" },
    ],
    next_cursor: null,
    total: 126,
  });
  render(wrapped(<SkillImportOperations scope="personal" locale="zh" />));
  fireEvent.click(screen.getByRole("button", { name: "检查导入记录" }));
  fireEvent.click(await screen.findByRole("button", { name: "加载更多记录" }));
  await screen.findByText(/记录核对失败/);
  expect(screen.getByText("operation-a")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "加载更多记录" }));
  await screen.findByText(/old-pending/);
  expect(mock.load).toHaveBeenLastCalledWith(
    "personal",
    expect.any(AbortSignal),
    "next-a",
  );
});
it("an invalid cursor clears actionable records and requires a fresh inspection", async () => {
  mock.load.mockResolvedValueOnce({
    operations: [pendingOperation],
    next_cursor: "next-a",
    total: 126,
  });
  mock.load.mockRejectedValueOnce(new SkillImportError(400));
  render(wrapped(<SkillImportOperations scope="personal" locale="zh" />));
  fireEvent.click(screen.getByRole("button", { name: "检查导入记录" }));
  fireEvent.click(await screen.findByRole("button", { name: "加载更多记录" }));
  await screen.findByText(/记录核对失败/);
  expect(screen.queryByText("operation-a")).not.toBeInTheDocument();
  expect(
    screen.queryByRole("button", { name: "加载更多记录" }),
  ).not.toBeInTheDocument();
});
it.each(["identity", "close"])(
  "ignores a late additional page after %s change",
  async (kind) => {
    mock.load.mockResolvedValueOnce({
      operations: [pendingOperation],
      next_cursor: "next-a",
      total: 126,
    });
    const request = deferred<{
      operations: SkillImportOperation[];
      next_cursor: null;
      total: number;
    }>();
    mock.load.mockReturnValueOnce(request.promise);
    const client = new QueryClient();
    const view = render(
      wrapped(<SkillImportOperations scope="personal" locale="zh" />, client),
    );
    fireEvent.click(screen.getByRole("button", { name: "检查导入记录" }));
    fireEvent.click(
      await screen.findByRole("button", { name: "加载更多记录" }),
    );
    const signal = mock.load.mock.calls[1]?.[1] as AbortSignal;
    if (kind === "identity") mock.key = "tenant-b/user-a";
    view.rerender(
      wrapped(
        <SkillImportOperations
          scope="personal"
          locale="zh"
          open={kind !== "close"}
        />,
        client,
      ),
    );
    await act(async () =>
      request.resolve({
        operations: [{ ...pendingOperation, name: "late private receipt" }],
        next_cursor: null,
        total: 126,
      }),
    );
    expect(signal.aborted).toBe(true);
    expect(screen.queryByText(/late private receipt/)).not.toBeInTheDocument();
  },
);
it("isolates a damaged receipt without offering recovery or abort", async () => {
  mock.load.mockResolvedValueOnce({
    operations: [
      {
        ...pendingOperation,
        name: "",
        state: "receipt_unavailable",
        phase: undefined,
        files_verified: false,
      },
    ],
    next_cursor: null,
    total: 1,
  });
  render(wrapped(<SkillImportOperations scope="personal" locale="zh" />));
  fireEvent.click(screen.getByRole("button", { name: "检查导入记录" }));
  await screen.findByText(/记录无法核对/);
  expect(
    screen.queryByRole("button", { name: "继续核对并登记" }),
  ).not.toBeInTheDocument();
  expect(
    screen.queryByRole("button", { name: "放弃自有暂存" }),
  ).not.toBeInTheDocument();
});
it("keeps the recovered old receipt visible when it is outside the first refreshed page", async () => {
  mock.load.mockResolvedValueOnce({
    operations: [pendingOperation],
    next_cursor: "next-a",
    total: 126,
  });
  mock.load.mockResolvedValueOnce({
    operations: [],
    next_cursor: "first-page",
    total: 126,
  });
  render(wrapped(<SkillImportOperations scope="personal" locale="zh" />));
  fireEvent.click(screen.getByRole("button", { name: "检查导入记录" }));
  fireEvent.click(
    await screen.findByRole("button", { name: "继续核对并登记" }),
  );
  fireEvent.click(screen.getByRole("button", { name: "确认操作" }));
  await screen.findByText(/已登记/);
  expect(screen.getByText("operation-a")).toBeInTheDocument();
  expect(
    screen.queryByRole("button", { name: "继续核对并登记" }),
  ).not.toBeInTheDocument();
});

it("offers deletion recovery without registration or abort and requires explicit confirmation", async () => {
  const deletion: SkillImportOperation = {
    ...pendingOperation,
    kind: "resource_delete",
    state: "reclamation_pending",
    phase: "delete_withdrawn",
    withdrawn: true,
    physical_reclamation: true,
  };
  mock.load.mockResolvedValueOnce({
    operations: [deletion],
    next_cursor: null,
    total: 1,
  });
  mock.load.mockResolvedValue({
    operations: [
      { ...deletion, state: "reclaimed", phase: "delete_reclaimed" },
    ],
    next_cursor: null,
    total: 1,
  });
  mock.change.mockResolvedValue({
    ...deletion,
    state: "reclaimed",
    phase: "delete_reclaimed",
  });
  render(
    wrapped(<SkillImportOperations scope="personal" locale="zh" deletion />),
  );
  fireEvent.click(screen.getByRole("button", { name: "检查删除记录" }));
  fireEvent.click(
    await screen.findByRole("button", { name: "继续撤回与回收" }),
  );
  expect(
    screen.getByRole("group", { name: "确认删除恢复操作" }),
  ).toHaveTextContent("确认继续删除");
  expect(
    screen.queryByRole("button", { name: "继续核对并登记" }),
  ).not.toBeInTheDocument();
  expect(
    screen.queryByRole("button", { name: "放弃自有暂存" }),
  ).not.toBeInTheDocument();
  expect(mock.change).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "确认操作" }));
  await screen.findByText(/删除与回收已完成/);
  expect(mock.change).toHaveBeenCalledWith(
    "personal",
    deletion.operation_id,
    "recover",
    expect.any(AbortSignal),
  );
});
