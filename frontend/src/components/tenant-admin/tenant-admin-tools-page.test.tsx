import { beforeEach, describe, expect, it, vi } from "vitest";

import type { AvailableMcpServerResponse } from "@/core/mcp/types";
import { fireEvent, render, screen, waitFor } from "@/test/utils";

import { TenantAdminToolsPage } from "./tenant-admin-tools-page";

const mocks = vi.hoisted(() => ({
  useAvailableMcpConfig: vi.fn(),
  useCreateTenantMCPServer: vi.fn(),
  useDeleteTenantMCPServer: vi.fn(),
  useEnableTenantMCPServer: vi.fn(),
  usePingMCPServer: vi.fn(),
  useCheckMCPHealth: vi.fn(),
  useUpdateSingleTenantMCPServer: vi.fn(),
  toastError: vi.fn(),
  toastSuccess: vi.fn(),
}));

vi.mock("@/core/mcp/hooks", () => ({
  useAvailableMcpConfig: mocks.useAvailableMcpConfig,
  useCreateTenantMCPServer: mocks.useCreateTenantMCPServer,
  useDeleteTenantMCPServer: mocks.useDeleteTenantMCPServer,
  useEnableTenantMCPServer: mocks.useEnableTenantMCPServer,
  usePingMCPServer: mocks.usePingMCPServer,
  useCheckMCPHealth: mocks.useCheckMCPHealth,
  useUpdateSingleTenantMCPServer: mocks.useUpdateSingleTenantMCPServer,
}));

vi.mock("sonner", () => ({
  toast: {
    error: mocks.toastError,
    success: mocks.toastSuccess,
  },
}));

function makeTool(
  overrides: Partial<AvailableMcpServerResponse> & Pick<AvailableMcpServerResponse, "name">,
): AvailableMcpServerResponse {
  return {
    enabled: true,
    type: "stdio",
    command: "npx",
    args: [],
    env: {},
    url: undefined,
    headers: {},
    oauth: undefined,
    description: "",
    is_builtin: false,
    scope: "tenant",
    source: "tenant_shared",
    managed_by_current_user: true,
    effective_permissions: ["read", "use", "manage"],
    health_status: "unknown",
    last_checked_at: null,
    ...overrides,
  };
}

function mockPageHooks(tools: AvailableMcpServerResponse[]) {
  const createTenantTool = vi.fn();
  const updateTenantTool = vi.fn();
  const deleteTenantTool = vi.fn();
  const enableTenantTool = vi.fn();
  const pingTool = vi.fn();

  mocks.useAvailableMcpConfig.mockReturnValue({ rawArray: tools, isLoading: false, error: null });
  mocks.useCreateTenantMCPServer.mockReturnValue({ mutateAsync: createTenantTool, isPending: false });
  mocks.useUpdateSingleTenantMCPServer.mockReturnValue({ mutateAsync: updateTenantTool, isPending: false });
  mocks.useDeleteTenantMCPServer.mockReturnValue({ mutateAsync: deleteTenantTool });
  mocks.useEnableTenantMCPServer.mockReturnValue({ mutateAsync: enableTenantTool });
  mocks.usePingMCPServer.mockReturnValue({ mutateAsync: pingTool, isPending: false });
  mocks.useCheckMCPHealth.mockReturnValue({ mutateAsync: pingTool, isPending: false });

  return {
    createTenantTool,
    updateTenantTool,
    deleteTenantTool,
    enableTenantTool,
    pingTool,
  };
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe("TenantAdminToolsPage", () => {
  it("shows built-in tools alongside tenant-owned tools", () => {
    mockPageHooks([
      makeTool({
        name: "filesystem",
        scope: "global",
        source: "platform_builtin",
        managed_by_current_user: true,
        effective_permissions: ["read", "use", "toggle"],
        description: "内置工具",
      }),
      makeTool({
        name: "tenant-tool",
        source: "tenant_shared",
        enabled: false,
        description: "工作空间自建工具",
        url: "https://example.com/mcp",
        type: "http",
        command: undefined,
      }),
      makeTool({
        name: "private-tool",
        scope: "user",
        source: "user_private",
        description: "个人工具",
      }),
    ]);

    render(<TenantAdminToolsPage />);

    expect(screen.getByRole("heading", { name: "工具管理" })).toBeInTheDocument();
    expect(screen.getByText("filesystem")).toBeInTheDocument();
    expect(screen.getByText("tenant-tool")).toBeInTheDocument();
    expect(screen.getByText("内置工具", { selector: "span" })).toBeInTheDocument();
    expect(screen.getByText("工作空间自建", { selector: "span" })).toBeInTheDocument();
    expect(screen.queryByText("private-tool")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "删除" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "编辑" })).toBeEnabled();
  });

  it("supports toggling, deleting and creating tenant MCP tools", async () => {
    const hooks = mockPageHooks([
      makeTool({
        name: "filesystem",
        scope: "global",
        source: "platform_builtin",
        managed_by_current_user: true,
        effective_permissions: ["read", "use", "toggle"],
      }),
      makeTool({
        name: "tenant-tool",
        source: "tenant_shared",
        enabled: false,
        description: "工作空间自建工具",
        url: "https://example.com/mcp",
        type: "http",
        command: undefined,
      }),
    ]);

    const confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(true);

    render(<TenantAdminToolsPage />);

    fireEvent.click(screen.getByRole("switch", { name: "filesystem 状态" }));

    await waitFor(() => {
      expect(hooks.enableTenantTool).toHaveBeenCalledWith({ serverName: "filesystem", enabled: false });
    });

    fireEvent.click(screen.getByRole("button", { name: "删除 tenant-tool" }));

    await waitFor(() => {
      expect(confirmSpy).toHaveBeenCalled();
      expect(hooks.deleteTenantTool).toHaveBeenCalledWith({ name: "tenant-tool" });
    });

    fireEvent.click(screen.getByRole("button", { name: "注册工具" }));
    fireEvent.change(screen.getByLabelText("工具名称"), { target: { value: "new-tenant-tool" } });
    fireEvent.change(screen.getByLabelText("启动命令"), { target: { value: "npx" } });
    fireEvent.click(screen.getByRole("button", { name: "保存" }));

    await waitFor(() => {
      expect(hooks.createTenantTool).toHaveBeenCalledWith({
        name: "new-tenant-tool",
        config: expect.objectContaining({
          enabled: true,
          type: "stdio",
          command: "npx",
          args: [],
          env: {},
          headers: {},
          description: "",
        }),
      });
    });

    confirmSpy.mockRestore();
  });
});
