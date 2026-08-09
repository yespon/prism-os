import { describe, expect, it, vi } from "vitest";

import { sanitizeRunStreamOptions, warnUnsupportedStreamModes } from "./stream-mode";

describe("sanitizeRunStreamOptions", () => {
  it("drops unsupported stream modes from array payloads", () => {
  const sanitized = sanitizeRunStreamOptions({
    streamMode: [
      "values",
      "messages-tuple",
      "custom",
      "updates",
      "events",
      "tools",
    ],
  });

    expect(sanitized.streamMode).toEqual([
    "values",
    "messages-tuple",
    "custom",
    "updates",
    "events",
  ]);
  });

  it("drops unsupported stream modes from scalar payloads", () => {
  const sanitized = sanitizeRunStreamOptions({
    streamMode: "tools",
  });

    expect(sanitized.streamMode).toBeUndefined();
  });

  it("keeps payloads without streamMode untouched", () => {
  const options = {
    streamSubgraphs: true,
  };

    expect(sanitizeRunStreamOptions(options)).toBe(options);
  });

  it("uses the PrismOS identity in unsupported-mode warnings", () => {
    const warn = vi.fn();
    warnUnsupportedStreamModes(["legacy-tools"], warn);

    expect(warn).toHaveBeenCalledWith(expect.stringContaining("[PrismOS]"));
    expect(warn).toHaveBeenCalledWith(expect.not.stringMatching(/opsintech/i));
  });
});
