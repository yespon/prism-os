import { beforeEach, describe, expect, it, vi } from "vitest";

import { getDisabledModelsStore, setDisabledModelsStore } from "@/core/models/hooks";
import { DEFAULT_LOCAL_SETTINGS, getLocalSettings, saveLocalSettings } from "@/core/settings/local";
import { ChatHistoryManager } from "@/core/terminal-agent/chat-history";
import { AutoApprovalManager } from "@/core/terminal-agent/security/auto-approval-settings";
import { SecurityConfigManager } from "@/core/terminal-agent/security/security-config";

describe("PrismOS branded storage consumers", () => {
  beforeEach(() => localStorage.clear());

  it("migrates local settings and writes only the canonical key", () => {
    localStorage.setItem("opsintech.local-settings", JSON.stringify(DEFAULT_LOCAL_SETTINGS));

    expect(getLocalSettings()).toMatchObject(DEFAULT_LOCAL_SETTINGS);
    saveLocalSettings(DEFAULT_LOCAL_SETTINGS);
    expect(localStorage.getItem("prismos_local_settings")).not.toBeNull();
    expect(localStorage.getItem("opsintech.local-settings")).toBeNull();
  });

  it("migrates disabled models and writes only the canonical key", () => {
    localStorage.setItem("opsintech:models:disabled", '["legacy-model"]');

    expect(getDisabledModelsStore()).toEqual(["legacy-model"]);
    setDisabledModelsStore(["new-model"]);
    expect(localStorage.getItem("prismos_models_disabled")).toBe('["new-model"]');
    expect(localStorage.getItem("opsintech:models:disabled")).toBeNull();
  });

  it("migrates terminal chat history", () => {
    localStorage.setItem("opsintech_terminal_chats", "[]");

    expect(ChatHistoryManager.loadSessions()).toEqual([]);
    expect(localStorage.getItem("prismos_terminal_chats")).toBe("[]");
    expect(localStorage.getItem("opsintech_terminal_chats")).toBeNull();
  });

  it("migrates auto-approval and security settings", () => {
    localStorage.setItem("opsintech_auto_approval_settings", '{"enabled":true}');
    localStorage.setItem("opsintech_terminal_security_config", '{"enableCommandSecurity":false}');

    expect(new AutoApprovalManager().getSettings().enabled).toBe(true);
    expect(new SecurityConfigManager().getConfig().enableCommandSecurity).toBe(false);
    expect(localStorage.getItem("prismos_auto_approval_settings")).not.toBeNull();
    expect(localStorage.getItem("prismos_terminal_security_config")).not.toBeNull();
  });

  it("keeps malformed legacy objects and falls back safely", () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => undefined);
    localStorage.setItem("opsintech.local-settings", "[]");

    expect(getLocalSettings()).toEqual(DEFAULT_LOCAL_SETTINGS);
    expect(localStorage.getItem("opsintech.local-settings")).toBe("[]");
    expect(warn).toHaveBeenCalled();
    warn.mockRestore();
  });
});
