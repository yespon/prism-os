/**
 * Security Configuration Manager.
 * Ported from Chaterm's src/main/agent/core/security/SecurityConfig.ts
 *
 * Manages security config with localStorage persistence in the browser.
 * Supports hot-reloading of config, JSON import/export.
 */

import { readMigratedStorage, writePrismOSStorage } from "@/core/storage/brand-migration";

export interface SecurityPolicy {
  /** Block critical commands (rm, dd, mkfs etc.) directly without asking */
  blockCritical: boolean;
  /** Ask for high-severity commands (systemctl, chmod, etc.) */
  askForHigh: boolean;
  /** Ask for medium-severity commands (iptables, sudo, etc.) */
  askForMedium: boolean;
  /** Ask for blacklist-pattern-matched commands (default: block) */
  askForBlacklist: boolean;
}

export interface SecurityConfig {
  /** Master switch for command security */
  enableCommandSecurity: boolean;
  /** Strict whitelist mode — only allow whitelisted commands */
  enableStrictMode: boolean;
  /** Maximum command length (characters) */
  maxCommandLength: number;
  /** Blacklist patterns (wildcards supported: *) */
  blacklistPatterns: string[];
  /** Whitelist patterns — only used when strictMode is enabled */
  whitelistPatterns: string[];
  /** Dangerous command executables */
  dangerousCommands: string[];
  /** Per-severity policy */
  securityPolicy: SecurityPolicy;
}

export const DEFAULT_SECURITY_CONFIG: SecurityConfig = {
  enableCommandSecurity: true,
  enableStrictMode: false,
  maxCommandLength: 10000,
  blacklistPatterns: [
    'rm -rf /',
    'rm -rf /*',
    'rm -fr /',
    'rm -fr /*',
    'chmod 777 /',
    'chmod -R 777 /',
    'chown -R /',
    'dd if=/dev/zero',
    'mkfs.* /dev/sda',
    'mkfs.* /dev/nvme',
    ':(){ :|:& };:',
    'wget * -O - | sh',
    'curl * | sh',
  ],
  whitelistPatterns: [
    'ls', 'pwd', 'whoami', 'date', 'uptime', 'uname',
    'df', 'du', 'free', 'ps aux', 'top -n 1 -b',
    'netstat', 'ss', 'ping', 'curl -I', 'wget --spider',
    'cat', 'head', 'tail', 'grep', 'find', 'which', 'type', 'file',
    'echo', 'printf', 'printenv', 'env',
    'id', 'groups', 'hostname',
    'awk', 'sed', 'cut', 'tr',
    'git status', 'git log', 'git diff', 'git branch',
    'docker ps', 'docker images', 'kubectl get',
    'journalctl', 'dmesg',
  ],
  dangerousCommands: [
    'rm', 'del', 'format', 'shutdown', 'reboot', 'halt', 'poweroff',
    'dd', 'mkfs', 'fdisk', 'parted',
    'killall', 'pkill',
    'systemctl', 'service',
    'chmod', 'chown',
    'mount', 'umount',
    'iptables', 'ufw', 'firewall-cmd',
    'sudo', 'su',
    'init',
  ],
  securityPolicy: {
    blockCritical: true,
    askForHigh: true,
    askForMedium: true,
    askForBlacklist: false, // Blacklist patterns are blocked by default
  },
};

const STORAGE_KEY = 'prismos_terminal_security_config';
const LEGACY_STORAGE_KEY = 'opsintech_terminal_security_config';

export class SecurityConfigManager {
  private config: SecurityConfig;

  constructor() {
    this.config = this.loadFromStorage() || { ...DEFAULT_SECURITY_CONFIG };
  }

  /**
   * Get the current security configuration.
   */
  getConfig(): SecurityConfig {
    return { ...this.config, securityPolicy: { ...this.config.securityPolicy } };
  }

  /**
   * Update security configuration (partial merge).
   */
  updateConfig(updates: Partial<SecurityConfig>): void {
    this.config = {
      ...this.config,
      ...updates,
      securityPolicy: updates.securityPolicy
        ? { ...this.config.securityPolicy, ...updates.securityPolicy }
        : this.config.securityPolicy,
    };
    this.saveToStorage();
  }

  /**
   * Reset to default configuration.
   */
  resetToDefaults(): void {
    this.config = { ...DEFAULT_SECURITY_CONFIG };
    this.saveToStorage();
  }

  /**
   * Export config as JSON string (for download/sharing).
   */
  exportConfig(): string {
    return JSON.stringify(this.config, null, 2);
  }

  /**
   * Import config from JSON string.
   */
  importConfig(json: string): boolean {
    try {
      const parsed = JSON.parse(json);
      // Basic validation
      if (typeof parsed.enableCommandSecurity !== 'boolean') {
        return false;
      }
      this.config = {
        ...DEFAULT_SECURITY_CONFIG,
        ...parsed,
        securityPolicy: {
          ...DEFAULT_SECURITY_CONFIG.securityPolicy,
          ...(parsed.securityPolicy || {}),
        },
      };
      this.saveToStorage();
      return true;
    } catch {
      return false;
    }
  }

  private loadFromStorage(): SecurityConfig | null {
    try {
      return readMigratedStorage({
        storage: localStorage,
        key: STORAGE_KEY,
        legacyKey: LEGACY_STORAGE_KEY,
        parse: parseSecurityConfig,
      });
    } catch {
      return null;
    }
  }

  private saveToStorage(): void {
    try {
      writePrismOSStorage(localStorage, STORAGE_KEY, JSON.stringify(this.config));
    } catch {
      // Storage full or unavailable
      console.warn('[SecurityConfig] Failed to save to localStorage');
    }
  }
}

function parseSecurityConfig(raw: string): SecurityConfig {
  const parsed: unknown = JSON.parse(raw);
  if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) {
    throw new Error("Invalid security config shape");
  }
  const record = parsed as Partial<SecurityConfig>;
  return {
    ...DEFAULT_SECURITY_CONFIG,
    ...record,
    securityPolicy: {
      ...DEFAULT_SECURITY_CONFIG.securityPolicy,
      ...(record.securityPolicy ?? {}),
    },
  };
}
