import { renderHook } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";

import { useSkillImportContext } from "./import-context";
const mock = vi.hoisted(() => ({
  tenant: "tenant-a",
  liveTenant: "tenant-a",
  token: "token-a",
  role: "tenant_admin",
  roleTenant: "tenant-a",
}));
vi.mock("@/core/auth/hooks", () => ({
  useSession: () => ({
    data: {
      user: { id: "user-a", role: "platform_admin" },
      session: { id: "session-a", token: "token-a" },
    },
  }),
}));
vi.mock("@/core/auth/auth-api", () => ({ getAuthToken: () => mock.token }));
vi.mock("@/core/agents/hooks", () => ({ useTenantKey: () => mock.tenant }));
vi.mock("@/core/tenants/hooks", () => ({
  useCurrentTenant: () => ({
    data: { tenant_id: mock.roleTenant, role: mock.role },
  }),
}));
vi.mock("@/core/tenants/store", () => ({
  getCurrentTenantId: () => mock.liveTenant,
}));
beforeEach(() => {
  mock.tenant = mock.liveTenant = mock.roleTenant = "tenant-a";
  mock.token = "token-a";
  mock.role = "tenant_admin";
});
it("requires the cached session to match the live token", () => {
  mock.token = "token-b";
  const { result } = renderHook(useSkillImportContext);
  expect(result.current.identityReady).toBe(false);
  expect(result.current.canShare).toBe(false);
});
it("does not grant shared writes from another tenant's cached admin role", () => {
  mock.roleTenant = "tenant-b";
  expect(renderHook(useSkillImportContext).result.current.canShare).toBe(false);
});
it("does not grant shared writes from platform role alone", () => {
  mock.role = "member";
  expect(renderHook(useSkillImportContext).result.current.canShare).toBe(false);
});
it("invalidates a captured identity immediately on live tenant or token change", () => {
  const { result } = renderHook(useSkillImportContext);
  const current = result.current.isCurrent;
  expect(current()).toBe(true);
  mock.liveTenant = "tenant-b";
  expect(current()).toBe(false);
  mock.liveTenant = "tenant-a";
  mock.token = "token-b";
  expect(current()).toBe(false);
});
it("keeps tokens out of the render key", () => {
  expect(renderHook(useSkillImportContext).result.current.key).not.toContain(
    "token-a",
  );
});
