/**
 * Command Security Checker — Enhanced version.
 * Ported from Chaterm's CommandSecurityManager with full compound parsing,
 * strict mode, per-severity policies, and wildcard blacklist matching.
 */

import type { SecurityPolicy } from './security/security-config';

export interface SecurityCheckResult {
  isSafe: boolean;
  reason: string;
  severity: 'low' | 'medium' | 'high' | 'critical';
  category: 'dangerous' | 'blacklist' | 'blocked' | 'whitelist' | 'safe' | 'permission';
  /** Whether this should ask the user vs. be blocked outright */
  action: 'allow' | 'ask' | 'block';
  /** Whether user approval is required */
  requiresApproval: boolean;
}

export interface CheckOptions {
  /** Max command length (default: 10000) */
  maxCommandLength?: number;
  /** Enable strict whitelist mode */
  strictMode?: boolean;
  /** Whitelist patterns (only used when strictMode is true) */
  whitelistPatterns?: string[];
  /** Blacklist patterns */
  blacklistPatterns?: string[];
  /** Dangerous command executables */
  dangerousCommands?: string[];
  /** Security policy */
  securityPolicy?: SecurityPolicy;
}

// Default dangerous commands with severity
const DANGEROUS_COMMANDS_SEVERITY: Record<string, { severity: 'critical' | 'high' | 'medium'; reason: string }> = {
  // Critical
  rm: { severity: 'critical', reason: '删除文件/目录，可能导致数据丢失' },
  del: { severity: 'critical', reason: '删除文件，可能导致数据丢失' },
  format: { severity: 'critical', reason: '格式化磁盘，会导致数据永久丢失' },
  shutdown: { severity: 'critical', reason: '关闭系统，会导致服务中断' },
  reboot: { severity: 'critical', reason: '重启系统，会导致服务中断' },
  halt: { severity: 'critical', reason: '停止系统，会导致服务中断' },
  poweroff: { severity: 'critical', reason: '关闭电源，会导致服务中断' },
  dd: { severity: 'critical', reason: '磁盘操作，误用会导致数据丢失' },
  mkfs: { severity: 'critical', reason: '创建文件系统，会清空磁盘数据' },
  fdisk: { severity: 'critical', reason: '磁盘分区操作，误用会导致数据丢失' },
  parted: { severity: 'critical', reason: '磁盘分区工具，误操作会导致数据丢失' },
  init: { severity: 'critical', reason: '改变系统运行级别，可能导致服务中断' },

  // High
  killall: { severity: 'high', reason: '批量终止进程，可能影响系统稳定性' },
  pkill: { severity: 'high', reason: '模式匹配终止进程，可能误杀关键进程' },
  systemctl: { severity: 'high', reason: '管理系统服务，可能影响服务运行' },
  service: { severity: 'high', reason: '管理系统服务，可能影响服务运行' },
  chmod: { severity: 'high', reason: '修改文件权限，可能导致安全漏洞' },
  chown: { severity: 'high', reason: '修改文件所有者，可能影响系统安全' },
  mount: { severity: 'high', reason: '挂载文件系统，不当操作可能影响系统' },
  umount: { severity: 'high', reason: '卸载文件系统，可能导致数据不一致' },

  // Medium
  iptables: { severity: 'medium', reason: '修改防火墙规则，可能影响网络访问' },
  ufw: { severity: 'medium', reason: '修改防火墙设置，可能影响网络访问' },
  'firewall-cmd': { severity: 'medium', reason: '修改防火墙配置，可能影响网络访问' },
  sudo: { severity: 'medium', reason: '以超级用户权限执行命令，请确认必要性' },
  su: { severity: 'medium', reason: '切换用户身份，请确认必要性' },
};

// Default blacklist patterns
const DEFAULT_BLACKLIST = [
  'rm -rf /',
  'rm -rf /*',
  'rm -fr /',
  'rm -fr /*',
  'chmod 777 /',
  'chmod -R 777 /',
  'chown -R /',
  'dd if=/dev/zero',
  ':(){ :|:& };:',
  'wget * -O - | sh',
  'curl * | sh',
];

// Default whitelist (for strict mode)
const DEFAULT_WHITELIST = [
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
  'git', 'docker', 'kubectl',
  'journalctl', 'dmesg',
];

/**
 * Find pipe position outside of quotes.
 */
function findPipeOutsideQuotes(command: string): number {
  let inSingle = false;
  let inDouble = false;
  for (let i = 0; i < command.length; i++) {
    const ch = command[i];
    if (ch === "'" && !inDouble) { inSingle = !inSingle; continue; }
    if (ch === '"' && !inSingle) { inDouble = !inDouble; continue; }
    if (!inSingle && !inDouble && ch === '|') return i;
  }
  return -1;
}

/**
 * Split compound command into individual commands (handles &&, ||, ;, |).
 */
function splitCompound(command: string): string[] {
  const parts: string[] = [];
  let current = '';
  let inSingle = false;
  let inDouble = false;

  for (let i = 0; i < command.length; i++) {
    const ch = command[i];

    if (ch === "'" && !inDouble) { inSingle = !inSingle; current += ch; continue; }
    if (ch === '"' && !inSingle) { inDouble = !inDouble; current += ch; continue; }

    if (!inSingle && !inDouble) {
      if (ch === '&' && command[i + 1] === '&') {
        if (current.trim()) parts.push(current.trim());
        current = '';
        i++; // skip second &
        continue;
      }
      if (ch === '|' && command[i + 1] === '|') {
        if (current.trim()) parts.push(current.trim());
        current = '';
        i++; // skip second |
        continue;
      }
      if (ch === ';') {
        if (current.trim()) parts.push(current.trim());
        current = '';
        continue;
      }
    }

    current += ch;
  }

  if (current.trim()) parts.push(current.trim());
  return parts.length > 1 ? parts : [command.trim()];
}

/**
 * Extract the primary executable from a command.
 */
function extractExecutable(command: string): string {
  const stripped = command
    .replace(/^(sudo|timeout|nice|ionice|nohup|setsid|chroot|flock|stdbuf)\s+/, '')
    .trim();

  // Handle pipes — only check first command
  const pipeIndex = findPipeOutsideQuotes(stripped);
  const firstCommand = pipeIndex >= 0 ? stripped.slice(0, pipeIndex).trim() : stripped;

  const match = /^([a-zA-Z0-9_][a-zA-Z0-9_.-]*)/.exec(firstCommand);
  return match ? (match[1] ?? '') : '';
}

/**
 * Match a command against a wildcard pattern.
 */
function matchesPattern(command: string, pattern: string): boolean {
  if (pattern.includes('*')) {
    const regexPattern = pattern.replace(/\*/g, '.*');
    const regex = new RegExp(`^${regexPattern}$`, 'i');
    return regex.test(command);
  }

  const escapedPattern = pattern.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');

  // For root directory dangerous operations, use anchored matching
  if (pattern.endsWith(' /') || pattern.endsWith(' / ')) {
    return new RegExp(`^${escapedPattern}(\\s|$)`, 'i').test(command);
  }

  return new RegExp(`(^|\\s)${escapedPattern}(\\s|$)`, 'i').test(command);
}

export class CommandSecurityChecker {
  /**
   * Full security check with configurable options.
   */
  static check(command: string, options: CheckOptions = {}): SecurityCheckResult {
    const trimmed = command.trim();

    if (!trimmed) {
      return { isSafe: true, reason: '', severity: 'low', category: 'safe', action: 'allow', requiresApproval: false };
    }

    const {
      maxCommandLength = 10000,
      strictMode = false,
      whitelistPatterns = DEFAULT_WHITELIST,
      blacklistPatterns = DEFAULT_BLACKLIST,
      securityPolicy,
    } = options;

    // 1. Length check
    if (trimmed.length > maxCommandLength) {
      return {
        isSafe: false,
        reason: `命令长度超过限制 (${maxCommandLength} 字符)`,
        severity: 'medium',
        category: 'permission',
        action: 'block',
        requiresApproval: false,
      };
    }

    // 2. Split into compound commands and check each
    const compounds = splitCompound(trimmed);

    // 3. Blacklist check (each compound)
    for (const cmd of compounds) {
      const blacklistResult = CommandSecurityChecker.checkBlacklist(cmd, blacklistPatterns, securityPolicy);
      if (blacklistResult) return blacklistResult;
    }

    // 4. Dangerous command check (each compound)
    for (const cmd of compounds) {
      const dangerousResult = CommandSecurityChecker.checkDangerous(cmd, securityPolicy);
      if (dangerousResult) return dangerousResult;
    }

    // 5. Strict mode whitelist check (each compound)
    if (strictMode) {
      for (const cmd of compounds) {
        const executable = extractExecutable(cmd);
        if (!executable) continue;
        const fullCmd = cmd.toLowerCase();
        const isWhitelisted = whitelistPatterns.some((p) => matchesPattern(fullCmd, p.toLowerCase()) || executable === p.toLowerCase().split(' ')[0]);
        if (!isWhitelisted) {
          return {
            isSafe: false,
            reason: `命令 "${executable}" 不在白名单中（严格模式已启用）`,
            severity: 'medium',
            category: 'whitelist',
            action: 'block',
            requiresApproval: false,
          };
        }
      }
    }

    return { isSafe: true, reason: '', severity: 'low', category: 'safe', action: 'allow', requiresApproval: false };
  }

  /**
   * Check a single command against blacklist patterns.
   */
  private static checkBlacklist(
    command: string,
    blacklistPatterns: string[],
    securityPolicy?: SecurityPolicy
  ): SecurityCheckResult | null {
    const lower = command.toLowerCase().trim();

    for (const pattern of blacklistPatterns) {
      if (matchesPattern(lower, pattern.toLowerCase())) {
        const shouldAsk = securityPolicy?.askForBlacklist ?? false;
        return {
          isSafe: shouldAsk,
          reason: `命令匹配黑名单模式: ${pattern}`,
          severity: 'critical',
          category: 'blacklist',
          action: shouldAsk ? 'ask' : 'block',
          requiresApproval: shouldAsk,
        };
      }
    }

    return null;
  }

  /**
   * Check a single command against dangerous command list.
   */
  private static checkDangerous(
    command: string,
    securityPolicy?: SecurityPolicy
  ): SecurityCheckResult | null {
    const executable = extractExecutable(command);
    if (!executable) return null;

    const info = DANGEROUS_COMMANDS_SEVERITY[executable.toLowerCase()];
    if (!info) return null;

    const shouldAsk = CommandSecurityChecker.shouldAskForSeverity(info.severity, securityPolicy);

    return {
      isSafe: shouldAsk,
      reason: info.reason,
      severity: info.severity,
      category: 'dangerous',
      action: shouldAsk ? 'ask' : 'block',
      requiresApproval: shouldAsk,
    };
  }

  /**
   * Determine if we should ask the user based on severity and policy.
   */
  private static shouldAskForSeverity(
    severity: 'low' | 'medium' | 'high' | 'critical',
    policy?: SecurityPolicy
  ): boolean {
    switch (severity) {
      case 'critical':
        // Always ask for critical — never silently block
        return true;
      case 'high':
        return policy?.askForHigh ?? true;
      case 'medium':
        return policy?.askForMedium ?? true;
      case 'low':
        return true;
      default:
        return true;
    }
  }

  /**
   * Quick check — is this command safe? (compatibility wrapper with old API)
   */
  static isSafe(command: string): boolean {
    return CommandSecurityChecker.check(command).isSafe;
  }
}
