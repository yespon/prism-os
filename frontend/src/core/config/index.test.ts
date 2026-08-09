import { describe, expect, it, vi } from "vitest";

vi.mock("@/env", () => ({
  env: {},
}));

import { getBackendBaseURL } from "./index";

describe("getBackendBaseURL", () => {
  it("uses the current page origin when no browser API URL is configured", () => {
    expect(getBackendBaseURL()).toBe(window.location.origin);
  });
});
