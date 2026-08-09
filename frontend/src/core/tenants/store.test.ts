import { beforeEach, describe, expect, it, vi } from "vitest";

describe("tenant storage migration", () => {
  beforeEach(() => {
    localStorage.clear();
    vi.resetModules();
  });

  it("migrates the tenant key and emits only the PrismOS event", async () => {
    localStorage.setItem("opsintech.current_tenant_id", "tenant-1");
    const legacy = vi.fn();
    const canonical = vi.fn();
    window.addEventListener("opsintech:tenant-changed", legacy);
    window.addEventListener("prismos:tenant-changed", canonical);

    const store = await import("./store");
    expect(store.getCurrentTenantId()).toBe("tenant-1");
    expect(localStorage.getItem("prismos_current_tenant_id")).toBe("tenant-1");
    expect(localStorage.getItem("opsintech.current_tenant_id")).toBeNull();

    store.setCurrentTenantId("tenant-2");
    expect(localStorage.getItem("prismos_current_tenant_id")).toBe("tenant-2");
    expect(legacy).not.toHaveBeenCalled();
    expect(canonical).toHaveBeenCalledOnce();

    window.removeEventListener("opsintech:tenant-changed", legacy);
    window.removeEventListener("prismos:tenant-changed", canonical);
  });
});
