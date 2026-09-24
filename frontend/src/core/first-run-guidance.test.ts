import { afterEach, describe, expect, it, vi } from "vitest";

const rollout = vi.hoisted(() => ({ tenantIds: "" }));
vi.mock("@/env", () => ({
  env: {
    get NEXT_PUBLIC_FIRST_RUN_TENANT_IDS() {
      return rollout.tenantIds;
    },
  },
}));

import { isFirstRunGuidanceEnabled } from "./first-run-guidance";

afterEach(() => {
  rollout.tenantIds = "";
});

describe("first-run guidance rollout", () => {
  it("stays off without an explicit tenant allowlist", () => {
    expect(isFirstRunGuidanceEnabled("tenant-a")).toBe(false);
  });

  it("only enables exact tenant IDs", () => {
    rollout.tenantIds = " tenant-a,tenant-b ";
    expect(isFirstRunGuidanceEnabled("tenant-a")).toBe(true);
    expect(isFirstRunGuidanceEnabled("tenant-b")).toBe(true);
    expect(isFirstRunGuidanceEnabled("tenant-ab")).toBe(false);
    expect(isFirstRunGuidanceEnabled(undefined)).toBe(false);
  });
});
