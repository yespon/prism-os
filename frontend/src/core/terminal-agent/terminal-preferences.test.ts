import { beforeEach, describe, expect, it } from "vitest";

import {
  loadHostSidebarCollapsed,
  loadTerminalTheme,
  saveHostSidebarCollapsed,
  saveTerminalTheme,
} from "./terminal-preferences";

describe("terminal preference migration", () => {
  beforeEach(() => localStorage.clear());

  it("migrates valid legacy preferences", () => {
    localStorage.setItem("opsintech_terminal_theme", "hacker");
    localStorage.setItem("opsintech_host_sidebar_collapsed", "true");

    expect(loadTerminalTheme(localStorage)).toBe("hacker");
    expect(loadHostSidebarCollapsed(localStorage)).toBe(true);
    expect(localStorage.getItem("opsintech_terminal_theme")).toBeNull();
    expect(localStorage.getItem("opsintech_host_sidebar_collapsed")).toBeNull();
  });

  it("writes only canonical preferences", () => {
    saveTerminalTheme(localStorage, "dark");
    saveHostSidebarCollapsed(localStorage, false);

    expect(localStorage.getItem("prismos_terminal_theme")).toBe("dark");
    expect(localStorage.getItem("prismos_host_sidebar_collapsed")).toBe("false");
  });
});
