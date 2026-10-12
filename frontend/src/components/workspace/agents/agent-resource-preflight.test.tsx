import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import type { ResourcePreflight } from "@/core/agents/catalog";
import { AgentResourcePreflight } from "./agent-resource-preflight";

const mock = vi.hoisted(() => ({
  tenant: "tenant-a",
  load: vi.fn(),
  download: vi.fn(),
}));
vi.mock("../skills/source-skill-install", () => ({
  SourceSkillInstall: ({ onInstalled }: {onInstalled: () => void}) => <button onClick={onInstalled}>Test completed installation</button>,
}));
vi.mock("@/core/skills/import-context", () => ({
  useSkillImportContext: () => ({
    key: mock.tenant,
    identityReady: true,
    canShare: false,
    isCurrent: () => true,
  }),
}));
vi.mock("@/core/agents/hooks", () => ({ useTenantKey: () => mock.tenant }));
vi.mock("@/core/tenants/store", () => ({
  getCurrentTenantId: () => mock.tenant,
}));
vi.mock("@/core/agents/catalog", () => ({
  loadResourcePreflight: mock.load,
  downloadResourceArchive: mock.download,
}));
const result: ResourcePreflight = {
  template_id: "expert:test",
  revision: "fixed-source-revision",
  declaration_sha256: "source-digest",
  member_count: 9,
  additional_member_count: 2,
  installation_checked: true,
  runtime_dependencies_checked: false,
  execution_ready: false,
  permission_grants: false,
  excluded_resources: ["skills/pptx"],
  resources: [
    {
      id: "resource:one",
      kind: "skill_bundle",
      root: "skills/test",
      bundle_sha256: "bundle",
      members: [
        { path: "SKILL.md", sha256: "source", source_path: "upstream/skill" },
      ],
      host_format: {
        status: "needs_adapter",
        detail: "Original format needs adaptation",
      },
      host_adaptation: { status: "ready", name: "test-skill", adapted: true },
      installation: { status: "modified", candidates: [] },
      execution_ready: false,
    },
  ],
};
function pending<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((done) => {
    resolve = done;
  });
  return { promise, resolve };
}
const props = { open: true, templateId: "expert:test", locale: "zh" as const };
beforeEach(() => {
  vi.clearAllMocks();
  mock.tenant = "tenant-a";
  mock.load.mockResolvedValue(result);
  mock.download.mockResolvedValue(new Blob(["public source"]));
});
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

it("checks full resources on demand and keeps installation different from execution rights", async () => {
  render(<AgentResourcePreflight {...props} />);
  expect(mock.load).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "检查配套资源" }));
  await screen.findByText(/完整配套文件 9 项/);
  expect(screen.getByText("同名内容有差异")).toBeInTheDocument();
  expect(screen.getByText(/依赖、绑定和执行权限仍需确认/)).toBeInTheDocument();
  expect(screen.getByText(/待独立实现：skills\/pptx/)).toBeInTheDocument();
  expect(mock.load).toHaveBeenCalledWith(
    "expert:test",
    "zh",
    expect.any(AbortSignal),
  );
});
it("retries failed checks without changing the agent draft", async () => {
  mock.load.mockRejectedValueOnce(new Error("unavailable"));
  render(<AgentResourcePreflight {...props} />);
  fireEvent.click(screen.getByRole("button", { name: "检查配套资源" }));
  await screen.findByRole("alert");
  fireEvent.click(screen.getByRole("button", { name: "检查配套资源" }));
  await screen.findByText(/完整配套文件 9 项/);
  expect(mock.load).toHaveBeenCalledTimes(2);
});
it.each(["template", "locale", "tenant", "close"])(
  "aborts and discards pending results after %s",
  async (kind) => {
    const request = pending<ResourcePreflight>();
    mock.load.mockReturnValueOnce(request.promise);
    const view = render(<AgentResourcePreflight {...props} />);
    fireEvent.click(screen.getByRole("button", { name: "检查配套资源" }));
    const signal = mock.load.mock.calls[0]?.[2] as AbortSignal;
    if (kind === "tenant") mock.tenant = "tenant-b";
    view.rerender(
      <AgentResourcePreflight
        {...props}
        templateId={kind === "template" ? "expert:other" : props.templateId}
        locale={kind === "locale" ? "en" : "zh"}
        open={kind !== "close"}
      />,
    );
    await act(async () => request.resolve(result));
    expect(signal.aborted).toBe(true);
    expect(screen.queryByText(/完整配套文件/)).not.toBeInTheDocument();
    expect(screen.queryByText("skills/test")).not.toBeInTheDocument();
  },
);
it("clears already loaded installation facts on a tenant change", async () => {
  const view = render(<AgentResourcePreflight {...props} />);
  fireEvent.click(screen.getByRole("button", { name: "检查配套资源" }));
  await screen.findByText("同名内容有差异");
  mock.tenant = "tenant-b";
  view.rerender(<AgentResourcePreflight {...props} />);
  expect(screen.queryByText("同名内容有差异")).not.toBeInTheDocument();
});
it("downloads only after a click and releases its temporary object URL", async () => {
  const create = vi.fn(() => "blob:source");
  const revoke = vi.fn();
  vi.stubGlobal(
    "URL",
    class extends URL {
      static createObjectURL = create;
      static revokeObjectURL = revoke;
    },
  );
  const click = vi
    .spyOn(HTMLAnchorElement.prototype, "click")
    .mockImplementation(() => {});
  render(<AgentResourcePreflight {...props} />);
  fireEvent.click(screen.getByRole("button", { name: "检查配套资源" }));
  fireEvent.click(await screen.findByRole("button", { name: "下载源包" }));
  await waitFor(() => expect(click).toHaveBeenCalled());
  expect(mock.download).toHaveBeenCalledWith(
    "expert:test",
    "resource:one",
    "zh",
    expect.any(AbortSignal),
  );
  expect(revoke).toHaveBeenCalledWith("blob:source");
  vi.unstubAllGlobals();
});
it("never downloads a late response after leaving the template", async () => {
  const download = pending<Blob>();
  mock.download.mockReturnValueOnce(download.promise);
  const create = vi.fn();
  vi.stubGlobal(
    "URL",
    class extends URL {
      static createObjectURL = create;
      static revokeObjectURL = vi.fn();
    },
  );
  const view = render(<AgentResourcePreflight {...props} />);
  fireEvent.click(screen.getByRole("button", { name: "检查配套资源" }));
  fireEvent.click(await screen.findByRole("button", { name: "下载源包" }));
  view.rerender(
    <AgentResourcePreflight {...props} templateId="expert:other" />,
  );
  await act(async () => download.resolve(new Blob(["source"])));
  expect(create).not.toHaveBeenCalled();
  vi.unstubAllGlobals();
});

it("refreshes installation facts after confirmed registration while preserving the visible resource", async () => {
  render(<AgentResourcePreflight {...props} />);
  fireEvent.click(screen.getByRole("button", {name: "检查配套资源"}));
  await screen.findByText(/完整配套文件 9 项/);
  const update = pending<ResourcePreflight>();
  mock.load.mockReturnValueOnce(update.promise);
  fireEvent.click(screen.getByRole("button", {name: "Test completed installation"}));
  expect(mock.load).toHaveBeenCalledTimes(2);
  expect(screen.getByText(/完整配套文件 9 项/)).toBeInTheDocument();
  await act(async () => update.resolve({...result, resources: [{...result.resources[0]!, installation: {status: "source_match", candidates: []}}]}));
  expect(screen.getByText(/依赖、绑定和执行权限仍需确认/)).toBeInTheDocument();
});
