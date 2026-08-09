import { readMigratedStorage, writePrismOSStorage } from "@/core/storage/brand-migration";

export type TerminalTheme = "light" | "dark" | "hacker";

const TERMINAL_THEME_KEY = "prismos_terminal_theme";
const LEGACY_TERMINAL_THEME_KEY = "opsintech_terminal_theme";
const HOST_SIDEBAR_COLLAPSED_KEY = "prismos_host_sidebar_collapsed";
const LEGACY_HOST_SIDEBAR_COLLAPSED_KEY = "opsintech_host_sidebar_collapsed";
const TERMINAL_THEMES = ["light", "dark", "hacker"] as const;

const parseTerminalTheme = (raw: string): TerminalTheme => {
  if (!(TERMINAL_THEMES as readonly string[]).includes(raw)) {
    throw new Error("Invalid terminal theme");
  }
  return raw as TerminalTheme;
};

const parseBoolean = (raw: string): boolean => {
  if (raw !== "true" && raw !== "false") {
    throw new Error("Invalid sidebar state");
  }
  return raw === "true";
};

export const loadTerminalTheme = (storage: Storage): TerminalTheme | null =>
  readMigratedStorage({
    storage,
    key: TERMINAL_THEME_KEY,
    legacyKey: LEGACY_TERMINAL_THEME_KEY,
    parse: parseTerminalTheme,
  });

export const saveTerminalTheme = (storage: Storage, value: TerminalTheme): void => {
  writePrismOSStorage(storage, TERMINAL_THEME_KEY, value);
};

export const loadHostSidebarCollapsed = (storage: Storage): boolean | null =>
  readMigratedStorage({
    storage,
    key: HOST_SIDEBAR_COLLAPSED_KEY,
    legacyKey: LEGACY_HOST_SIDEBAR_COLLAPSED_KEY,
    parse: parseBoolean,
  });

export const saveHostSidebarCollapsed = (storage: Storage, value: boolean): void => {
  writePrismOSStorage(storage, HOST_SIDEBAR_COLLAPSED_KEY, String(value));
};
