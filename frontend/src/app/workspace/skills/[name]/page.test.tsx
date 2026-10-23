import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  act,
  cleanup,
  fireEvent,
  render as testingRender,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import { SkillMutationError } from "@/core/skills/mutations";

import SkillDetailPage from "./page";

const mock = vi.hoisted(() => ({
  key: "tenant-a/user-a",
  name: "collision",
  create: vi.fn(),
  scope: "personal",
  id: "skill:1",
  ready: true,
  current: true,
  detail: vi.fn(),
  patch: vi.fn(),
  push: vi.fn(),
  success: vi.fn(),
  terminal: vi.fn(),
}));
vi.mock("next/navigation", () => ({
  useParams: () => ({ name: mock.name }),
  useRouter: () => ({ push: mock.push, back: vi.fn() }),
  useSearchParams: () =>
    new URLSearchParams({ scope: mock.scope, resource_id: mock.id }),
}));
vi.mock("@/core/skills/import-context", () => ({useSkillImportContext: () => ({key: mock.key, identityReady: mock.ready, canShare: false, isCurrent: () => mock.current})}));
function render(element: React.ReactElement) {
  const client = new QueryClient({defaultOptions: {queries: {retry: false}}});
  return testingRender(element, {wrapper: ({children}) => <QueryClientProvider client={client}>{children}</QueryClientProvider>});
}
vi.mock("@/core/skills/query-identity", () => ({
  useSkillQueryIdentity: () => ({
    key: mock.key,
    identityReady: mock.ready,
    isCurrent: () => mock.current,
  }),
}));
vi.mock("@/core/skills/api", () => ({
  getSkillDetail: mock.detail,
  patchPersonalSkill: mock.patch,
  patchTenantSkill: mock.patch,
  createPersonalSkill: mock.create,
  generateInstructions: vi.fn(),
}));
vi.mock("@/core/models/hooks", () => ({
  useAvailableModels: () => ({ models: [] }),
}));
vi.mock("@/core/terminal-agent/useTerminalAgent", () => ({
  useTerminalAgent: mock.terminal,
}));
vi.mock("sonner", () => ({ toast: { success: mock.success, error: vi.fn() } }));
vi.mock("@/components/workspace/messages/markdown-content", () => ({
  MarkdownContent: ({ content }: { content: string }) => <div>{content}</div>,
}));
const data = {
  name: "collision",
  resource_id: "skill:current",
  file_sha256: "a".repeat(64),
  description: "PERSONAL DESCRIPTION",
  instructions: "PERSONAL BODY",
  scope: "personal",
  managed_by_current_user: true,
  enabled: true,
  bound_tools: [],
};
beforeEach(() => {
  vi.clearAllMocks();
  mock.key = "tenant-a/user-a";
  mock.name = "collision";
  mock.scope = "personal";
  mock.id = "skill:1";
  mock.ready = mock.current = true;
  mock.detail.mockResolvedValue(data);
  mock.terminal.mockReturnValue({
    messages: [],
    input: "",
    handleInputChange: vi.fn(),
    handleSubmit: vi.fn(),
    sendMessage: vi.fn(),
    isLoading: false,
  });
});
afterEach(cleanup);
it("requests the concrete selected resource and scope", async () => {
  render(<SkillDetailPage />);
  await screen.findByDisplayValue("PERSONAL BODY");
  expect(mock.detail).toHaveBeenCalledWith("collision", {
    scope: "personal",
    resourceId: "skill:1",
    signal: expect.any(AbortSignal),
  });
});
it("discards a late same-name response after source identity changes", async () => {
  let resolve!: (value: typeof data) => void;
  mock.detail.mockReturnValueOnce(
    new Promise((done) => {
      resolve = done;
    }),
  );
  mock.detail.mockResolvedValueOnce({
    ...data,
    scope: "tenant",
    instructions: "SHARED BODY",
  });
  const view = render(<SkillDetailPage />);
  const signal = mock.detail.mock.calls[0]?.[1].signal as AbortSignal;
  mock.scope = "tenant";
  mock.id = "skill:2";
  view.rerender(<SkillDetailPage />);
  await screen.findByDisplayValue("SHARED BODY");
  await act(async () => resolve(data));
  expect(signal.aborted).toBe(true);
  expect(screen.queryByDisplayValue("PERSONAL BODY")).not.toBeInTheDocument();
});
it("clears private fields and creates a different test-chat session after identity change", async () => {
  const view = render(<SkillDetailPage />);
  await screen.findByDisplayValue("PERSONAL BODY");
  const session = mock.terminal.mock.calls.at(-1)?.[0].taskId;
  mock.detail.mockResolvedValueOnce({
    ...data,
    instructions: "NEW OWNER BODY",
  });
  mock.key = "tenant-b/user-b";
  view.rerender(<SkillDetailPage />);
  expect(screen.queryByDisplayValue("PERSONAL BODY")).not.toBeInTheDocument();
  await screen.findByDisplayValue("NEW OWNER BODY");
  expect(mock.terminal.mock.calls.at(-1)?.[0].taskId).not.toBe(session);
});
it("a late save cannot navigate or toast into a different selected source", async () => {
  let resolve!: (value: unknown) => void;
  mock.patch.mockReturnValueOnce(
    new Promise((done) => {
      resolve = done;
    }),
  );
  const view = render(<SkillDetailPage />);
  await screen.findByDisplayValue("PERSONAL BODY");
  fireEvent.click(screen.getByRole("button", { name: "保存" }));
  await waitFor(() => expect(mock.patch).toHaveBeenCalledOnce());
  mock.id = "skill:2";
  view.rerender(<SkillDetailPage />);
  await act(async () => resolve({}));
  expect(mock.push).not.toHaveBeenCalled();
  expect(mock.success).not.toHaveBeenCalled();
});

it("unknown save blocks repetition until the user reinspects the current specific resource", async () => {
  mock.patch.mockRejectedValueOnce(
    new SkillMutationError(503, "skill:current", true),
  );
  render(<SkillDetailPage />);
  await screen.findByDisplayValue("PERSONAL BODY");
  fireEvent.click(screen.getByRole("button", { name: "保存" }));
  const inspect = await screen.findByRole("button", {
    name: "重新检查当前资源",
  });
  expect(screen.getByRole("button", { name: "保存" })).toBeDisabled();
  fireEvent.click(inspect);
  await screen.findByDisplayValue("PERSONAL BODY");
  expect(mock.patch).toHaveBeenCalledOnce();
  expect(mock.patch.mock.calls[0]?.[1]).toMatchObject({
    expected_resource_id: "skill:current",
    expected_file_sha256: "a".repeat(64),
  });
  expect(mock.detail).toHaveBeenCalledTimes(2);
  expect(screen.getByRole("button", { name: "保存" })).not.toBeDisabled();
});


it("recovered disabled personal resource can be explicitly enabled using its current instance and content", async () => {
  mock.detail.mockResolvedValueOnce({...data, enabled: false}); mock.patch.mockResolvedValueOnce({});
  render(<SkillDetailPage />); await screen.findByDisplayValue("PERSONAL BODY");
  const toggle = screen.getByRole("switch", {name: "启用此 Skill"}); expect(toggle).toHaveAttribute("aria-checked", "false"); fireEvent.click(toggle);
  fireEvent.click(screen.getByRole("button", {name: "保存"})); await waitFor(() => expect(mock.patch).toHaveBeenCalledOnce());
  expect(mock.patch.mock.calls[0]?.[1]).toMatchObject({enabled: true, expected_resource_id: "skill:current", expected_file_sha256: "a".repeat(64)});
});
it("new creation unknown offers original operation inspection and never reloads an empty draft as proof of recovery", async () => {
  mock.name = "new"; mock.create.mockRejectedValueOnce(new SkillMutationError(503, "skill:current", true, "Inspect", "a".repeat(32)));
  render(<SkillDetailPage />);
  fireEvent.change(await screen.findByPlaceholderText("输入小写英文名称"), {target: {value: "owned-new"}});
  fireEvent.change(screen.getByPlaceholderText("简短描述这个 Skill 做什么"), {target: {value: "Owned description"}});
  fireEvent.click(screen.getByRole("button", {name: "保存"}));
  await screen.findByRole("button", {name: "检查创建记录"}); expect(screen.getByRole("button", {name: "保存"})).toBeDisabled();
  expect(screen.queryByRole("button", {name: "重新检查当前资源"})).not.toBeInTheDocument(); expect(mock.create).toHaveBeenCalledOnce(); expect(mock.detail).not.toHaveBeenCalled();
});
