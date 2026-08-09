import { fireEvent, render, screen } from "@/test/utils";
import { describe, expect, it, vi } from "vitest";

import { TenantAdminMembersPage } from "./tenant-admin-members-page";

const mocks = vi.hoisted(() => ({
  useCurrentTenant: vi.fn(),
  useTenantMembers: vi.fn(),
  useTenantSelectableUsers: vi.fn(),
  useAddTenantMember: vi.fn(),
  useUpdateTenantMemberRole: vi.fn(),
  useUpdateTenantMemberStatus: vi.fn(),
  useRemoveTenantMember: vi.fn(),
  useAddTenantMembersByEmail: vi.fn(),
}));

vi.mock("@/core/tenants/hooks", () => ({
  useCurrentTenant: mocks.useCurrentTenant,
  useTenantMembers: mocks.useTenantMembers,
  useTenantSelectableUsers: mocks.useTenantSelectableUsers,
  useAddTenantMember: mocks.useAddTenantMember,
  useUpdateTenantMemberRole: mocks.useUpdateTenantMemberRole,
  useUpdateTenantMemberStatus: mocks.useUpdateTenantMemberStatus,
  useRemoveTenantMember: mocks.useRemoveTenantMember,
  useAddTenantMembersByEmail: mocks.useAddTenantMembersByEmail,
}));

describe("TenantAdminMembersPage", () => {
  it("renders dedicated tenant admin members page and searchable users", () => {
    mocks.useCurrentTenant.mockReturnValue({
      data: { tenant_id: "tenant-a", role: "tenant_admin" },
    });
    mocks.useTenantMembers.mockReturnValue({
      data: [
        {
          user_id: "u-1",
          email: "u1@example.com",
          name: "User 1",
          role: "tenant_member",
          status: "active",
        },
      ],
      isLoading: false,
      error: null,
    });
    mocks.useAddTenantMember.mockReturnValue({ mutateAsync: vi.fn(), isPending: false });
    mocks.useAddTenantMembersByEmail.mockReturnValue({ mutateAsync: vi.fn(), isPending: false });
    mocks.useUpdateTenantMemberRole.mockReturnValue({ mutateAsync: vi.fn() });
    mocks.useUpdateTenantMemberStatus.mockReturnValue({ mutateAsync: vi.fn() });
    mocks.useRemoveTenantMember.mockReturnValue({ mutateAsync: vi.fn() });
    mocks.useTenantSelectableUsers.mockImplementation(({ keyword }: { keyword?: string }) => ({
      data:
        keyword === "al"
          ? [
              {
                user_id: "u-2",
                email: "alice@example.com",
                name: "Alice",
                role: "user",
                status: "active",
                already_member: false,
              },
            ]
          : [],
      isLoading: false,
      error: null,
    }));

    render(<TenantAdminMembersPage />);

    expect(screen.getByRole("heading", { name: "用户管理" })).toBeInTheDocument();
    
  });
});
