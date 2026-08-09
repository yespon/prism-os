import { beforeEach, describe, expect, it, vi } from "vitest";

import { readMigratedStorage, writePrismOSStorage } from "./brand-migration";

const parseString = (raw: string) => raw;

describe("brand storage migration", () => {
  beforeEach(() => localStorage.clear());

  it("prefers the new key and leaves legacy untouched", () => {
    localStorage.setItem("prismos_test", "new");
    localStorage.setItem("opsintech_test", "old");

    expect(
      readMigratedStorage({
        storage: localStorage,
        key: "prismos_test",
        legacyKey: "opsintech_test",
        parse: parseString,
      }),
    ).toBe("new");
    expect(localStorage.getItem("opsintech_test")).toBe("old");
  });

  it("copies valid legacy data, verifies it, then removes the old key", () => {
    localStorage.setItem("opsintech_test", "old");

    expect(
      readMigratedStorage({
        storage: localStorage,
        key: "prismos_test",
        legacyKey: "opsintech_test",
        parse: parseString,
      }),
    ).toBe("old");
    expect(localStorage.getItem("prismos_test")).toBe("old");
    expect(localStorage.getItem("opsintech_test")).toBeNull();
  });

  it("preserves malformed legacy data", () => {
    localStorage.setItem("opsintech_json", "not-json");

    expect(
      readMigratedStorage({
        storage: localStorage,
        key: "prismos_json",
        legacyKey: "opsintech_json",
        parse: JSON.parse,
      }),
    ).toBeNull();
    expect(localStorage.getItem("opsintech_json")).toBe("not-json");
    expect(localStorage.getItem("prismos_json")).toBeNull();
  });

  it("writes only the new key", () => {
    writePrismOSStorage(localStorage, "prismos_test", "value");

    expect(localStorage.getItem("prismos_test")).toBe("value");
  });

  it("does not delete legacy data when the new write cannot be verified", () => {
    const removeItem = vi.fn();
    const storage = {
      getItem: (key: string) => (key === "opsintech_test" ? "old" : null),
      setItem: () => undefined,
      removeItem,
    } as unknown as Storage;

    expect(
      readMigratedStorage({
        storage,
        key: "prismos_test",
        legacyKey: "opsintech_test",
        parse: parseString,
      }),
    ).toBeNull();
    expect(removeItem).not.toHaveBeenCalled();
  });
});
