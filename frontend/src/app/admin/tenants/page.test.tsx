import { describe, expect, it, vi } from "vitest";

import { render, screen, waitFor } from "@/test/utils";

import AdminTenantsPage from "./page";

const mocks = vi.hoisted(() => ({
  fetchAuthApi: vi.fn(),
}));

vi.mock("@/core/api/auth-client", () => ({
  fetchAuthApi: mocks.fetchAuthApi,
}));

vi.mock("./create-tenant-dialog", () => ({
  CreateTenantDialog: () => null,
}));

vi.mock("./delete-tenant-dialog", () => ({
  DeleteTenantDialog: () => null,
}));

vi.mock("./deactivate-tenant-dialog", () => ({
  DeactivateTenantDialog: () => null,
}));

vi.mock("./restore-tenant-dialog", () => ({
  RestoreTenantDialog: () => null,
}));

vi.mock("./edit-tenant-dialog", () => ({
  EditTenantDialog: () => null,
}));

describe("AdminTenantsPage", () => {
  it("does not show tenant member management action", async () => {
    mocks.fetchAuthApi.mockResolvedValue({
      ok: true,
      json: async () => ({
        tenants: [
          {
            id: "tenant-a",
            name: "Tenant A",
            slug: "tenant-a",
            status: "active",
            created_at: "2026-04-02T00:00:00Z",
            member_count: 3,
          },
        ],
      }),
    });

    render(<AdminTenantsPage />);

    await waitFor(() => {
      expect(screen.getByText("Tenant A")).toBeInTheDocument();
    });

    expect(screen.queryByRole("button", { name: "成员管理" })).not.toBeInTheDocument();
  });

  it("shows permanent delete action for inactive tenants", async () => {
    mocks.fetchAuthApi.mockResolvedValue({
      ok: true,
      json: async () => ({
        tenants: [
          {
            id: "tenant-b",
            name: "Tenant B",
            slug: "tenant-b",
            status: "inactive",
            created_at: "2026-04-02T00:00:00Z",
            member_count: 1,
          },
        ],
      }),
    });

    render(<AdminTenantsPage />);

    await waitFor(() => {
      expect(screen.getByText("Tenant B")).toBeInTheDocument();
    });

    expect(screen.getByRole("button", { name: "永久删除" })).toBeInTheDocument();
  });
});
