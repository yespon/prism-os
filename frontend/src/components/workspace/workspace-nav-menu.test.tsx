import { beforeEach, describe, expect, it, vi } from "vitest";

import { fireEvent, render, screen } from "@/test/utils";

import { WorkspaceNavMenu } from "./workspace-nav-menu";

const mocks = vi.hoisted(() => ({
  useSession: vi.fn(),
  useCurrentTenant: vi.fn(),
  useTenantList: vi.fn(),
  useRouter: vi.fn(),
  useQueryClient: vi.fn(),
  useSidebar: vi.fn(),
}));

const queryClientMock = {
  cancelQueries: vi.fn().mockResolvedValue(undefined),
  clear: vi.fn(),
};

vi.mock("@/core/auth/hooks", () => ({
  useSession: mocks.useSession,
}));

vi.mock("next/navigation", () => ({
  useRouter: mocks.useRouter,
}));

vi.mock("@tanstack/react-query", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@tanstack/react-query")>()),
  useQueryClient: mocks.useQueryClient,
}));

vi.mock("@/components/ui/sidebar", () => ({
  useSidebar: mocks.useSidebar,
}));

vi.mock("@/core/tenants", () => ({
  useCurrentTenant: mocks.useCurrentTenant,
  useTenantList: mocks.useTenantList,
}));

vi.mock("@/components/workspace/settings", () => ({
  SettingsDialog: ({ open }: { open: boolean }) => (open ? <div>settings-dialog-open</div> : null),
}));

describe("WorkspaceNavMenu", () => {
  const renderMenu = (role: string, tenantRole: string) => {
    mocks.useSession.mockReturnValue({
      data: { user: { role, name: "Tester", email: "tester@example.com" } },
    });
    mocks.useCurrentTenant.mockReturnValue({ data: { tenant_id: "tenant-a", role: tenantRole } });
    mocks.useTenantList.mockReturnValue({ data: [] });

    render(<WorkspaceNavMenu />);

    fireEvent.pointerDown(screen.getByRole("button", { name: /Tester tenant-a/ }));
  };

  beforeEach(() => {
    mocks.useRouter.mockReturnValue({ replace: vi.fn(), refresh: vi.fn() });
    mocks.useQueryClient.mockReturnValue(queryClientMock);
    mocks.useSidebar.mockReturnValue({ state: "expanded", toggleSidebar: vi.fn() });
  });

  it("shows personal settings entry for normal users", () => {
    renderMenu("user", "tenant_member");

    expect(screen.getByRole("menuitem", { name: "个人设置" })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "平台治理" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "管理工作台" })).not.toBeInTheDocument();
  });

  it("opens settings dialog from personal settings entry", () => {
    renderMenu("user", "tenant_member");

    fireEvent.click(screen.getByRole("menuitem", { name: "个人设置" }));
    expect(screen.getByText("settings-dialog-open")).toBeInTheDocument();
  });

  it("shows platform admin entry for platform admins", () => {
    mocks.useSession.mockReturnValue({ data: { user: { role: "admin", name: "Tester", email: "tester@example.com" } } });
    mocks.useCurrentTenant.mockReturnValue({ data: { tenant_id: "tenant-a", role: "tenant_member" } });
    mocks.useTenantList.mockReturnValue({ data: [] });

    render(<WorkspaceNavMenu />);

    expect(screen.getByRole("link", { name: "平台治理" })).toHaveAttribute("href", "/admin");
  });

  it("shows tenant admin workspace entry for tenant admins", () => {
    renderMenu("user", "tenant_admin");

    expect(screen.getByRole("menuitem", { name: "管理工作台" }).closest("a")).toHaveAttribute(
      "href",
      "/tenant-admin",
    );
  });
});
