import { describe, expect, it, vi } from "vitest";

import { render, screen, waitFor } from "@/test/utils";

import { TenantAdminGuard } from "./tenant-admin-guard";

const mocks = vi.hoisted(() => ({
  replace: vi.fn(),
  useCurrentTenant: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: mocks.replace }),
}));

vi.mock("@/core/tenants/hooks", () => ({
  useCurrentTenant: mocks.useCurrentTenant,
}));

describe("TenantAdminGuard", () => {
  it("renders loading state while checking tenant role", () => {
    mocks.useCurrentTenant.mockReturnValue({
      data: null,
      isLoading: true,
      isError: false,
    });

    render(
      <TenantAdminGuard>
        <div>content</div>
      </TenantAdminGuard>,
    );

    expect(screen.getByText("正在校验工作空间权限...")).toBeInTheDocument();
  });

  it("redirects non-tenant-admin users", async () => {
    mocks.useCurrentTenant.mockReturnValue({
      data: { role: "tenant_member" },
      isLoading: false,
      isError: false,
    });

    const { container } = render(
      <TenantAdminGuard>
        <div>content</div>
      </TenantAdminGuard>,
    );

    await waitFor(() => {
      expect(mocks.replace).toHaveBeenCalledWith("/workspace/chats");
    });
    expect(container).toBeEmptyDOMElement();
  });

  it("renders children for tenant_admin", () => {
    mocks.useCurrentTenant.mockReturnValue({
      data: { role: "tenant_admin" },
      isLoading: false,
      isError: false,
    });

    render(
      <TenantAdminGuard>
        <div>content</div>
      </TenantAdminGuard>,
    );

    expect(screen.getByText("content")).toBeInTheDocument();
  });
});
