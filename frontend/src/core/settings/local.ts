import { readMigratedStorage, writePrismOSStorage } from "@/core/storage/brand-migration";

import type { AgentThreadContext } from "../threads";

export const DEFAULT_LOCAL_SETTINGS: LocalSettings = {
  notification: {
    enabled: true,
  },
  context: {
    model_name: undefined,
    mode: undefined,
    reasoning_effort: undefined,
    skill_name: undefined,
  },
  layout: {
    sidebar_collapsed: false,
  },
};

const LOCAL_SETTINGS_KEY = "prismos_local_settings";
const LEGACY_LOCAL_SETTINGS_KEY = "opsintech.local-settings";

export interface LocalSettings {
  notification: {
    enabled: boolean;
  };
  context: Omit<
    AgentThreadContext,
    "thread_id" | "is_plan_mode" | "thinking_enabled" | "subagent_enabled"
  > & {
    mode: "flash" | "thinking" | "pro" | "ultra" | undefined;
    reasoning_effort?: "minimal" | "low" | "medium" | "high";
  };
  layout: {
    sidebar_collapsed: boolean;
  };
}

export function getLocalSettings(): LocalSettings {
  if (typeof window === "undefined") {
    return DEFAULT_LOCAL_SETTINGS;
  }
  try {
    const settings = readMigratedStorage({
      storage: localStorage,
      key: LOCAL_SETTINGS_KEY,
      legacyKey: LEGACY_LOCAL_SETTINGS_KEY,
      parse: parseLocalSettings,
    });
    return settings ?? DEFAULT_LOCAL_SETTINGS;
  } catch {
    return DEFAULT_LOCAL_SETTINGS;
  }
}

export function saveLocalSettings(settings: LocalSettings) {
  writePrismOSStorage(localStorage, LOCAL_SETTINGS_KEY, JSON.stringify(settings));
}

function parseLocalSettings(raw: string): LocalSettings {
  const settings: unknown = JSON.parse(raw);
  if (typeof settings !== "object" || settings === null || Array.isArray(settings)) {
    throw new Error("Invalid local settings shape");
  }
  const record = settings as Partial<LocalSettings>;
  return {
    ...DEFAULT_LOCAL_SETTINGS,
    context: {
      ...DEFAULT_LOCAL_SETTINGS.context,
      ...(record.context ?? {}),
    },
    layout: {
      ...DEFAULT_LOCAL_SETTINGS.layout,
      ...(record.layout ?? {}),
    },
    notification: {
      ...DEFAULT_LOCAL_SETTINGS.notification,
      ...(record.notification ?? {}),
    },
  };
}
