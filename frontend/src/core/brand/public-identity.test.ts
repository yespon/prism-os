import fs from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";

const root = path.resolve(__dirname, "../../..");
const publicFiles = [
  "src/app/sign-in/page.tsx",
  "src/components/landing/hero.tsx",
  "src/components/workspace/workspace-header.tsx",
  "src/components/tenant-admin/alert-sources-tab.tsx",
  "src/components/workspace/incidents/alert-sources-panel.tsx",
  "src/core/terminal-agent/security/security-settings-ui.tsx",
];

describe("PrismOS public identity", () => {
  it("uses PrismOS assets and copy", () => {
    for (const relative of publicFiles) {
      const content = fs.readFileSync(path.join(root, relative), "utf8");
      expect(content).not.toMatch(/opsintech/i);
    }
    expect(fs.existsSync(path.join(root, "public/images/prismos.svg"))).toBe(true);
    expect(fs.existsSync(path.join(root, "public/images/prismos-full.svg"))).toBe(true);
    expect(fs.existsSync(path.join(root, "public/images/opsintech.svg"))).toBe(false);
    expect(fs.readFileSync(path.join(root, "public/images/prismos-full.svg"), "utf8"))
      .toContain("PrismOS");
  });
});
