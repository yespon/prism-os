import { describe, expect, it, vi } from "vitest";

import { render, screen } from "@/test/utils";

import { TenantAdminShell } from "./tenant-admin-shell";

const mocks = vi.hoisted(() => ({
  usePathname: vi.fn(),
  useRouter: vi.fn(),
  useCurrentTenant: vi.fn(),
  useTenantList: vi.fn(),
  useSwitchTenant: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  usePathname: mocks.usePathname,
  useRouter: mocks.useRouter,
}));

vi.mock("@/core/tenants", () => ({
  useCurrentTenant: mocks.useCurrentTenant,
  useTenantList: mocks.useTenantList,
  useSwitchTenant: mocks.useSwitchTenant,
}));

describe("TenantAdminShell", () => {
  it("renders tenant admin navigation and content", () => {
    mocks.usePathname.mockReturnValue("/tenant-admin/members");
    mocks.useRouter.mockReturnValue({ replace: vi.fn(), refresh: vi.fn() });
    mocks.useCurrentTenant.mockReturnValue({ data: { tenant_id: "tenant-a" } });
    mocks.useTenantList.mockReturnValue({
      data: [
        { id: "tenant-a", name: "Tenant A" },
        { id: "tenant-b", name: "Tenant B" },
      ],
    });
    mocks.useSwitchTenant.mockReturnValue({ mutate: vi.fn(), isPending: false });

    render(
      <TenantAdminShell>
        <div>members content</div>
      </TenantAdminShell>,
    );

    expect(screen.getByText("管理控制台")).toBeInTheDocument();
    expect(screen.getByRole("combobox", { name: "切换工作空间" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "用户管理" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "智能体管理" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "告警规则" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "渠道管理" })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "个人设置" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "外观" })).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "进入业务工作台" })).toHaveAttribute(
      "href",
      "/workspace/overview",
    );
    expect(screen.getByText("members content")).toBeInTheDocument();
  });
});
