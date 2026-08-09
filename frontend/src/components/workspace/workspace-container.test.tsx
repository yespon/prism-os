import { fireEvent, render, screen } from "@/test/utils";
import { describe, expect, it, vi } from "vitest";

import { WorkspaceHeader } from "./workspace-container";

const mocks = vi.hoisted(() => ({
  useCurrentTenant: vi.fn(),
  useTenantList: vi.fn(),
  useSwitchTenant: vi.fn(),
  mutate: vi.fn(),
}));

vi.mock("@/core/tenants", () => ({
  useCurrentTenant: mocks.useCurrentTenant,
  useTenantList: mocks.useTenantList,
  useSwitchTenant: mocks.useSwitchTenant,
}));

describe("WorkspaceHeader", () => {
  it("shows tenant dropdown and switches tenant", () => {
    mocks.useCurrentTenant.mockReturnValue({ data: { tenant_id: "tenant-a" } });
    mocks.useTenantList.mockReturnValue({
      data: [
        { id: "tenant-a", name: "Tenant A" },
        { id: "tenant-b", name: "Tenant B" },
      ],
    });
    mocks.useSwitchTenant.mockReturnValue({ mutate: mocks.mutate, isPending: false });

    render(<WorkspaceHeader />);

    const select = screen.getByRole("combobox", { name: "切换工作空间" });
    expect(select).toBeInTheDocument();
    fireEvent.change(select, { target: { value: "tenant-b" } });
    expect(mocks.mutate).toHaveBeenCalledWith("tenant-b");
  });
});
