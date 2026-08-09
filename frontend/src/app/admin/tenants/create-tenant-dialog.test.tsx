import { describe, expect, it, vi } from "vitest";

import { render, screen } from "@/test/utils";

import { CreateTenantDialog } from "./create-tenant-dialog";

const mocks = vi.hoisted(() => ({
  fetchAuthApi: vi.fn(),
  toastSuccess: vi.fn(),
  toastError: vi.fn(),
}));

vi.mock("@/core/api/auth-client", () => ({
  fetchAuthApi: mocks.fetchAuthApi,
}));

vi.mock("sonner", () => ({
  toast: {
    success: mocks.toastSuccess,
    error: mocks.toastError,
  },
}));

describe("CreateTenantDialog", () => {
  it("does not expose tenant_member option and keeps initial role fixed", () => {
    render(<CreateTenantDialog open onOpenChange={vi.fn()} onSuccess={vi.fn()} />);

    expect(screen.queryByText("该用户在工作空间中的角色")).not.toBeInTheDocument();
    expect(screen.queryByText("tenant_member")).not.toBeInTheDocument();
    expect(screen.getByText("初始角色")).toBeInTheDocument();
    expect(screen.getByText("tenant_admin")).toBeInTheDocument();
  });
});
