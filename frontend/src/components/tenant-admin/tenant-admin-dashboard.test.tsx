import { describe, expect, it, vi } from "vitest";

import { render, screen } from "@/test/utils";

import { TenantAdminDashboard } from "./tenant-admin-dashboard";

const mocks = vi.hoisted(() => ({
  useAvailableMcpConfig: vi.fn(),
  useAvailableModels: vi.fn(),
  useAvailableSkills: vi.fn(),
  useCurrentTenant: vi.fn(),
  useTenantMembers: vi.fn(),
}));

vi.mock("@/core/mcp/hooks", () => ({
  useAvailableMcpConfig: mocks.useAvailableMcpConfig,
}));

vi.mock("@/core/models/hooks", () => ({
  useAvailableModels: mocks.useAvailableModels,
}));

vi.mock("@/core/skills/hooks", () => ({
  useAvailableSkills: mocks.useAvailableSkills,
}));

vi.mock("@/core/tenants/hooks", () => ({
  useCurrentTenant: mocks.useCurrentTenant,
  useTenantMembers: mocks.useTenantMembers,
}));

describe("TenantAdminDashboard", () => {
  it("renders unified dashboard structure", () => {
    mocks.useCurrentTenant.mockReturnValue({ data: { tenant_id: "tenant-a", role: "tenant_admin" } });
    mocks.useTenantMembers.mockReturnValue({ data: [{ id: "m1" }, { id: "m2" }] });
    mocks.useAvailableModels.mockReturnValue({ models: [{ scope: "tenant", enabled: true }] });
    mocks.useAvailableMcpConfig.mockReturnValue({ rawArray: [{ scope: "tenant", enabled: true }] });
    mocks.useAvailableSkills.mockReturnValue({ skills: [{ scope: "tenant", enabled: true }] });

    render(<TenantAdminDashboard />);

    expect(screen.getByRole("heading", { level: 1, name: "总览" })).toBeInTheDocument();
    expect(screen.getByText("成员数量")).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 2, name: "风险提醒" })).toBeInTheDocument();
  });
});
