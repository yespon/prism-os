/**
 * Auto-Approval Settings.
 * Ported from Chaterm's src/main/agent/shared/AutoApprovalSettings.ts
 *
 * Controls which tool actions can be auto-approved without user confirmation.
 */

import { readMigratedStorage, writePrismOSStorage } from "@/core/storage/brand-migration";

export interface AutoApprovalActions {
  /** Auto-approve reading files on the remote server */
  readFiles: boolean;
  /** Auto-approve writing/editing files */
  editFiles: boolean;
  /** Auto-approve safe commands (ls, cat, echo, etc.) */
  executeSafeCommands: boolean;
  /** Auto-approve ALL commands (including dangerous ones — USE WITH CAUTION) */
  executeAllCommands: boolean;
  /** Once user approves one read-only command, auto-approve all subsequent read-only commands */
  autoExecuteReadOnlyCommands: boolean;
}

export interface AutoApprovalSettings {
  version: number;
  /** Master switch */
  enabled: boolean;
  /** Per-action toggles */
  actions: AutoApprovalActions;
  /** Maximum consecutive auto-approved requests (prevents infinite loops) */
  maxRequests: number;
  /** Show notification when a command is auto-approved */
  enableNotifications: boolean;
}

export const DEFAULT_AUTO_APPROVAL: AutoApprovalSettings = {
  version: 1,
  enabled: false,
  actions: {
    readFiles: true,
    editFiles: false,
    executeSafeCommands: true,
    executeAllCommands: false,
    autoExecuteReadOnlyCommands: false,
  },
  maxRequests: 3,
  enableNotifications: true,
};

const STORAGE_KEY = 'prismos_auto_approval_settings';
const LEGACY_STORAGE_KEY = 'opsintech_auto_approval_settings';

// List of known read-only commands
const READONLY_COMMANDS = [
  'ls', 'pwd', 'whoami', 'date', 'uptime', 'uname',
  'df', 'du', 'free', 'ps', 'top', 'htop',
  'netstat', 'ss', 'ping', 'traceroute',
  'curl', 'wget',
  'cat', 'head', 'tail', 'grep', 'find', 'wc', 'sort',
  'which', 'whereis', 'type', 'file',
  'echo', 'printf', 'printenv', 'env',
  'history', 'alias', 'help', 'man', 'info',
  'id', 'groups', 'hostname', 'hostnamectl',
  'awk', 'sed', 'cut', 'tr',
  'git status', 'git log', 'git diff', 'git branch', 'git show',
  'docker ps', 'docker images', 'docker logs', 'docker inspect',
  'kubectl get', 'kubectl describe', 'kubectl logs',
  'journalctl', 'dmesg',
  'systemctl status', 'systemctl list-units',
];

export function isReadOnlyCommand(command: string): boolean {
  const lower = command.toLowerCase().trim();
  return READONLY_COMMANDS.some((c) => lower.startsWith(c));
}

export class AutoApprovalManager {
  private settings: AutoApprovalSettings;
  private consecutiveApproved = 0;
  /** Once user approves one read-only command, auto-approve rest */
  private readOnlyModeAutoApproved = false;

  constructor() {
    this.settings = this.loadFromStorage() ?? { ...DEFAULT_AUTO_APPROVAL };
  }

  getSettings(): AutoApprovalSettings {
    return { ...this.settings, actions: { ...this.settings.actions } };
  }

  updateSettings(updates: Partial<AutoApprovalSettings>): void {
    this.settings = {
      ...this.settings,
      ...updates,
      actions: updates.actions
        ? { ...this.settings.actions, ...updates.actions }
        : this.settings.actions,
    };
    this.saveToStorage();
  }

  /**
   * Check whether a given action should be auto-approved.
   *
   * @param actionType - The type of action being performed
   * @param command - Optional command string (for execute commands)
   * @returns Whether to auto-approve
   */
  shouldAutoApprove(
    actionType: 'readFile' | 'editFile' | 'executeSafeCommand' | 'executeAllCommands',
    command?: string
  ): boolean {
    if (!this.settings.enabled) return false;

    // Check max consecutive requests limit
    if (this.consecutiveApproved >= this.settings.maxRequests) {
      return false;
    }

    // Read-only command mode: once user approved one, auto-approve rest
    if (actionType === 'executeSafeCommand' && this.readOnlyModeAutoApproved) {
      return true;
    }

    switch (actionType) {
      case 'readFile':
        return this.settings.actions.readFiles;
      case 'editFile':
        return this.settings.actions.editFiles;
      case 'executeSafeCommand':
        if (command && isReadOnlyCommand(command)) {
          return this.settings.actions.executeSafeCommands ||
            this.settings.actions.autoExecuteReadOnlyCommands;
        }
        return this.settings.actions.executeSafeCommands;
      case 'executeAllCommands':
        return this.settings.actions.executeAllCommands;
      default:
        return false;
    }
  }

  /**
   * Record that an auto-approval was used.
   */
  recordAutoApproval(): void {
    this.consecutiveApproved++;
  }

  /**
   * User manually approved a read-only command — enable auto-approval for
   * subsequent read-only commands in this session.
   */
  enableReadOnlyAutoMode(): void {
    this.readOnlyModeAutoApproved = true;
  }

  /**
   * Reset approval counters (called on new task or manual user reset).
   */
  resetCounters(): void {
    this.consecutiveApproved = 0;
    this.readOnlyModeAutoApproved = false;
  }

  private loadFromStorage(): AutoApprovalSettings | null {
    try {
      return readMigratedStorage({
        storage: localStorage,
        key: STORAGE_KEY,
        legacyKey: LEGACY_STORAGE_KEY,
        parse: parseAutoApprovalSettings,
      });
    } catch {
      return null;
    }
  }

  private saveToStorage(): void {
    try {
      writePrismOSStorage(localStorage, STORAGE_KEY, JSON.stringify(this.settings));
    } catch {
      console.warn('[AutoApproval] Failed to save to localStorage');
    }
  }
}

function parseAutoApprovalSettings(raw: string): AutoApprovalSettings {
  const parsed: unknown = JSON.parse(raw);
  if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) {
    throw new Error("Invalid auto-approval settings shape");
  }
  return { ...DEFAULT_AUTO_APPROVAL, ...(parsed as Partial<AutoApprovalSettings>) };
}
