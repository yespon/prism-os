/**
 * InteractionDetector - Core detection logic for interactive command execution
 *
 * Ported from Chaterm's src/main/agent/services/interaction-detector/index.ts
 * Adapted for browser environment (no Node.js EventEmitter dependency).
 *
 * Detection strategy:
 * 1. Quick rule matching (immediate) - for common patterns like password:, [Y/n]
 * 2. LLM intelligent detection (after timeout) - for complex cases
 *
 * Supported interaction types:
 * - confirm: Y/n, yes/no confirmations
 * - select: Numbered menu selections
 * - password: Password/passphrase input
 * - pager: less/more pagination controls
 * - enter: Press Enter to continue
 * - freeform: Generic text input
 */

import { TypedEventEmitter } from './event-emitter';
import type {
  InteractionResult,
  InteractionRequest,
  QuickPattern,
  InteractionDetectorConfig,
  TuiCategory,
  InteractionDetectorEvents,
  ConfirmValues,
} from './types';

// Re-export types
export * from './types';

/**
 * Simple ANSI string stripper (browser-compatible, no Node deps)
 */
function stripAnsi(str: string): string {
  return str.replace(/\x1b\[[0-9;]*[a-zA-Z]/g, '');
}

/**
 * Default configuration values
 */
const DEFAULT_CONFIG: Required<InteractionDetectorConfig> = {
  initialTimeout: 5000,
  maxTimeout: 60000,
  maxLlmCalls: 3,
  maxLines: 20,
  lineBufferMaxLength: 2048,
  maxLlmContextLength: 4000,
  maxNetworkFails: 3,
  maxHashUnchangedCount: 3,
  maxSilentTimeout: 30000,
  pagerObservationTimeout: 2000,
  userLocale: 'en-US',
  tuiCancelSilenceMs: 1500,
  tuiHardTimeoutMs: 2000,
};

// Simple hash function for dedup
function simpleHash(str: string): string {
  let hash = 0;
  for (let i = 0; i < str.length; i++) {
    const chr = str.charCodeAt(i);
    hash = ((hash << 5) - hash) + chr;
    hash |= 0;
  }
  return hash.toString(36);
}

// Generate unique command ID
function generateCommandId(taskId: string): string {
  return `${taskId}-${Date.now()}-${Math.random().toString(36).slice(2, 9)}`;
}

/**
 * InteractionDetector class
 *
 * Monitors command output and detects when user interaction is needed.
 * Uses a combination of fast regex rules and LLM-based detection.
 */
export class InteractionDetector extends TypedEventEmitter<InteractionDetectorEvents> {
  private readonly command: string;
  readonly commandId: string;
  private readonly taskId?: string;
  private readonly config: Required<InteractionDetectorConfig>;
  private readonly debugEnabled: boolean;

  // Timer management
  private timer: ReturnType<typeof setTimeout> | null = null;

  // Output buffering
  private outputBuffer: string[] = [];
  private lineBuffer = '';
  private pausedOutputBuffer: string[] = [];
  private pausedOutputSize = 0;

  // State management
  private _isPaused = false;
  private isDetecting = false;
  private lastOutputTime = 0;
  private llmCallCount = 0;
  private currentTimeout: number;

  // Network error handling
  private networkFailCount = 0;

  // Dismiss/suppress logic
  private dismissCount = 0;
  private _isSuppressed = false;

  // Hash deduplication
  private lastOutputHash = '';
  private hashUnchangedCount = 0;
  private lastHashChangeTime: number = Date.now();

  // Prompt debounce
  private promptDebounceTimer: ReturnType<typeof setTimeout> | null = null;
  private pendingPromptResult: InteractionResult | null = null;
  private readonly PROMPT_DEBOUNCE_MS = 300;

  // TUI detection
  private inAlternateScreen = false;

  // TUI auto-cancel state
  private tuiCategory: TuiCategory = null;
  private isShellSpawning = false;
  private tuiSilenceTimer: ReturnType<typeof setTimeout> | null = null;
  private tuiHardTimeoutTimer: ReturnType<typeof setTimeout> | null = null;
  private lastOutputTimeForTui = 0;

  // Pager state
  private isPager = false;
  private pagerObservationMode = false;
  private pagerObservationTimer: ReturnType<typeof setTimeout> | null = null;

  // Escape buffer for cross-chunk detection
  private escapeBuffer = '';
  private readonly ESCAPE_BUFFER_SIZE = 64;

  // LLM caller function (injected dependency)
  private llmCaller: ((command: string, output: string, locale: string) => Promise<InteractionResult>) | null = null;

  // Warning flag
  private warnedMissingLlm = false;

  // Disposal state
  private _disposed = false;

  get isPaused(): boolean { return this._isPaused; }
  get isSuppressed(): boolean { return this._isSuppressed; }
  get isStopped(): boolean { return this._disposed; }

  // === Quick pattern rules for immediate detection ===
  private readonly QUICK_PATTERNS: QuickPattern[] = [
    // Password prompts
    { pattern: /password\s*:/i, type: 'password' },
    { pattern: /passphrase\s*:/i, type: 'password' },
    { pattern: /口令\s*:/i, type: 'password' },
    { pattern: /密码\s*[:：]/i, type: 'password' },
    { pattern: /\[sudo\]\s*password\s+for/i, type: 'password' },

    // Confirm prompts
    { pattern: /\[Y\/n\]/i, type: 'confirm', confirmValues: { yes: 'Y', no: 'n', default: 'Y' } },
    { pattern: /\[y\/N\]/i, type: 'confirm', confirmValues: { yes: 'y', no: 'N', default: 'N' } },
    { pattern: /\(yes\/no\)/i, type: 'confirm', confirmValues: { yes: 'yes', no: 'no' } },
    { pattern: /\[是\/否\]/i, type: 'confirm', confirmValues: { yes: '是', no: '否' } },
    { pattern: /\(y\/n\)/i, type: 'confirm', confirmValues: { yes: 'y', no: 'n' } },

    // Enter to continue
    { pattern: /press enter/i, type: 'enter' },
    { pattern: /按.*回车/i, type: 'enter' },
    { pattern: /continue\?/i, type: 'enter' },
    { pattern: /press any key/i, type: 'enter' },

    // Pager strong patterns (end of line)
    { pattern: /--More--\s*$/i, type: 'pager' },
    { pattern: /\(END\)\s*$/i, type: 'pager' },
    { pattern: /^lines\s+\d+-\d+(?:\/\d+)?(?:\s*\(END\))?\s*$/i, type: 'pager' },
    { pattern: /^\s*:\s*$/, type: 'pager' },
  ];

  // Prompt suffix pattern
  private readonly PROMPT_SUFFIX_PATTERN = /[:?：？]\s*$/;

  // Prompt keywords whitelist
  private readonly PROMPT_KEYWORDS = [
    /password/i, /passwd/i, /密码/, /口令/,
    /username/i, /user\s*name/i, /用户名/,
    /login/i, /登录/,
    /enter/i, /input/i, /输入/, /请输入/,
    /continue/i, /proceed/i, /继续/,
    /confirm/i, /确认/,
    /passphrase/i, /token/i, /key/i, /secret/i,
    /verification/i, /code/i, /验证码/,
    /answer/i, /回答/,
    /choice/i, /select/i, /选择/,
    /value/i, /值/,
    /name/i, /名称/,
    /path/i, /路径/,
    /host/i, /主机/,
    /port/i, /端口/,
  ];

  // Confirm keywords
  private readonly CONFIRM_KEYWORDS = [
    /remove/i, /delete/i, /overwrite/i, /replace/i,
    /discard/i, /erase/i,
    /确认/, /删除/, /移除/, /覆盖/, /替换/, /丢弃/,
  ];

  // Exclusion list for log prefixes and URLs
  private readonly PROMPT_EXCLUSIONS = [
    /^\s*\[?(INFO|DEBUG|WARN|WARNING|ERROR|TRACE|FATAL)\]?\s*:/i,
    /^\s*(INFO|DEBUG|WARN|WARNING|ERROR|TRACE|FATAL)\s+\d/i,
    /^\d{4}-\d{2}-\d{2}[T\s]\d{2}:\d{2}/,
    /^\d{2}:\d{2}:\d{2}/,
    /https?:\/\//i,
    /:\d{2,5}\/?$/,
    /^\/[\w\-\.\/]+:/,
    /^[A-Z]:\\[\w\-\.\\]+:/i,
    /^\s*"[\w\-]+"\s*:/,
    /^\s*[\w\-]+\s*=\s*/,
    /^\s*\w+\s+\|\s+/,
    /^\s*<[\w\-]+>/,
  ];

  // Always-TUI commands
  private readonly ALWAYS_TUI_COMMANDS = [
    /^vim?\b/i, /^vi\b/i, /^nano\b/i, /^emacs\b/i,
    /^tmux\b/i, /^screen\b/i, /^mc\b/i, /^nnn\b/i,
    /^ranger\b/i,
    /^sudo\s+su\b/i, /^su\s*$/i, /^su\s+-/i, /^su\s+\w/i,
  ];

  // Shell-spawning patterns
  private readonly SHELL_SPAWNING_PATTERNS = [
    /^sudo\s+su\b/i, /^su\s*$/i, /^su\s+-/i, /^su\s+\w/i,
    /^bash\s*$/i, /^sh\s*$/i, /^zsh\s*$/i, /^ksh\s*$/i,
    /^csh\s*$/i, /^tcsh\s*$/i, /^fish\s*$/i, /^dash\s*$/i,
  ];

  // Conditional-TUI commands
  private readonly CONDITIONAL_TUI_COMMANDS: Array<{ pattern: RegExp; nonInteractiveArgs: RegExp[] }> = [
    { pattern: /^top\b/i, nonInteractiveArgs: [/-n\s*\d+/, /-b\b/] },
    { pattern: /^htop\b/i, nonInteractiveArgs: [] },
    { pattern: /^btop\b/i, nonInteractiveArgs: [] },
    { pattern: /^mysql\b/i, nonInteractiveArgs: [/-e\s/, /--execute\b/, /--batch\b/, /--silent\b/] },
    { pattern: /^psql\b/i, nonInteractiveArgs: [/-c\s/, /--command\b/, /-t\b/, /-A\b/] },
    { pattern: /^ssh\b/i, nonInteractiveArgs: [/-T\b/, /-o\s*BatchMode=yes/i, /\s+['"]?[^-]/] },
    { pattern: /^bash\b/i, nonInteractiveArgs: [/-c\s/, /\s+\S+\.\w+/, /\s+\/\S+/] },
    { pattern: /^sh\b/i, nonInteractiveArgs: [/-c\s/, /\s+\S+\.\w+/, /\s+\/\S+/] },
    { pattern: /^zsh\b/i, nonInteractiveArgs: [/-c\s/, /\s+\S+\.\w+/, /\s+\/\S+/] },
    { pattern: /^fish\b/i, nonInteractiveArgs: [/-c\s/, /\s+\S+\.\w+/, /\s+\/\S+/] },
  ];

  // Pager commands
  private readonly PAGER_COMMANDS = [
    /^less\b/i, /^more\b/i, /^most\b/i, /^pg\b/i, /^view\b/i,
    /^man\b/i, /^git\s+log\b/i, /^git\s+diff\b/i,
    /^journalctl\b/i, /^systemctl\s+status\b/i,
    /\|\s*less\b/i, /\|\s*more\b/i,
  ];

  // Pager output strong patterns
  private readonly PAGER_OUTPUT_PATTERNS = [
    /\(END\)\s*$/, /--More--\s*$/i,
    /^lines\s+\d+-\d+(?:\/\d+)?(?:\s*\(END\))?\s*$/i,
    /^\s*:\s*$/, /Manual page\s+/i,
    /^NAME\s*$/i, /^SYNOPSIS\s*$/i,
  ];

  // Alternate screen control sequences
  private readonly ALTERNATE_SCREEN_ENTER = ['\x1b[?1049h', '\x1b[?47h', '\x1b[?1047h'];
  private readonly ALTERNATE_SCREEN_EXIT = ['\x1b[?1049l', '\x1b[?47l', '\x1b[?1047l'];

  constructor(command: string, taskId?: string, config?: InteractionDetectorConfig) {
    super();

    this.command = command;
    this.commandId = generateCommandId(taskId ?? 'terminal');
    this.taskId = taskId;
    this.config = { ...DEFAULT_CONFIG, ...config };
    this.currentTimeout = this.config.initialTimeout;

    this.debugEnabled = process.env.NODE_ENV !== 'production';

    const tuiCategory = this.classifyTuiCommand();
    this.tuiCategory = tuiCategory;
    this.isShellSpawning = this.SHELL_SPAWNING_PATTERNS.some(p => p.test(this.command.trim()));

    this.debug('init', {
      command: this.command,
      commandId: this.commandId,
      tuiCategory: this.tuiCategory,
    });

    if (this.tuiCategory === 'always' || this.tuiCategory === 'conditional') {
      this.startTuiHardTimeout();
    }
  }

  /** Set the LLM caller function for intelligent detection */
  setLlmCaller(caller: (command: string, output: string, locale: string) => Promise<InteractionResult>): void {
    this.llmCaller = caller;
  }

  /** Process incoming output data */
  onOutput(data: string): void {
    if (this._disposed) return;
    this.lastOutputTime = Date.now();

    // Cross-chunk escape sequence detection
    const combined = this.escapeBuffer + data;
    this.escapeBuffer = combined.slice(-this.ESCAPE_BUFFER_SIZE);

    // Normalize CR and strip ANSI once for all subsequent processing
    const normalizedData = this.normalizeCR(data);
    const cleanData = stripAnsi(normalizedData);

    // 1. Check for pager output features first (highest priority)
    if (this.checkPagerOutput(cleanData)) {
      this.debug('pager-output-detected');
      this.isPager = true;
      this.cancelPagerObservation();
      if (!this._isPaused) {
        this.pause();
        this.emitInteractionNeeded({
          commandId: this.commandId,
          interactionType: 'pager',
          promptHint: 'Pager mode detected',
        });
      }
      return;
    }

    // 2. Detect alternate screen entry/exit
    let hasExitSeq = false;
    let hasEnterSeq = false;

    for (const seq of this.ALTERNATE_SCREEN_EXIT) {
      if (combined.includes(seq)) { hasExitSeq = true; break; }
    }
    for (const seq of this.ALTERNATE_SCREEN_ENTER) {
      if (combined.includes(seq)) { hasEnterSeq = true; break; }
    }

    if (hasExitSeq) {
      this.inAlternateScreen = false;
      this.isPager = false;
      this.cancelPagerObservation();
      this.cancelTuiSilenceTimer();
      this.resume();
      return;
    }

    if (hasEnterSeq) {
      this.inAlternateScreen = true;
      this.lastOutputTimeForTui = Date.now();

      if (this.isPagerCommand()) {
        this.isPager = true;
        this.cancelTuiSilenceTimer();
        this.pause();
        this.emitInteractionNeeded({
          commandId: this.commandId,
          interactionType: 'pager',
          promptHint: 'Pager mode detected',
        });
        return;
      }

      this.startPagerObservation();

      if (this.tuiCategory === 'always' || this.tuiCategory === 'conditional') {
        this.startTuiSilenceTimer();
        this.emit('alternate-screen-entered', { commandId: this.commandId, taskId: this.taskId, autoCancel: true });
      } else {
        this.emit('alternate-screen-entered', { commandId: this.commandId, taskId: this.taskId, autoCancel: false });
      }
      return;
    }

    // Reset TUI silence timer on new output
    if (this.inAlternateScreen && !this.isPager) {
      this.lastOutputTimeForTui = Date.now();
      if (this.tuiCategory === 'always' || this.tuiCategory === 'conditional') {
        this.startTuiSilenceTimer();
      }
    }

    // Continue detection during pager observation
    if (!this.pagerObservationMode && this.inAlternateScreen && !this.isPager) {
      return;
    }

    if (this._isPaused) {
      this.appendToPausedBuffer(cleanData);
      return;
    }

    // Reset backoff on new output
    this.currentTimeout = this.config.initialTimeout;
    this.llmCallCount = 0;
    this.networkFailCount = 0;
    this.hashUnchangedCount = 0;
    this.lastHashChangeTime = Date.now();

    this.clearPromptDebounce();

    // Process with line buffering
    this.processOutputForDetection(cleanData);

    // Quick rule matching
    const quickResult = this.tryQuickMatch(this.getFullOutput());
    if (quickResult) {
      this.debug('quick-match', { type: quickResult.interactionType });
      this.pause();
      this.emitInteractionNeeded({
        commandId: this.commandId,
        ...quickResult,
      });
      return;
    }

    this.resetTimer();
  }

  /** Pause detection (when UI is shown) */
  pause(): void {
    this._isPaused = true;
    if (this.timer) {
      clearTimeout(this.timer);
      this.timer = null;
    }
  }

  /** Resume detection (after user responds) */
  resume(): void {
    if (this.pausedOutputBuffer.length > 0) {
      const pausedData = this.pausedOutputBuffer.join('');
      this.lineBuffer += pausedData;
      const lines = this.lineBuffer.split('\n');
      this.lineBuffer = lines.pop() ?? '';
      for (const line of lines) {
        const trimmedLine = line.trim();
        if (trimmedLine) {
          this.outputBuffer.push(trimmedLine);
          while (this.outputBuffer.length > this.config.maxLines) {
            this.outputBuffer.shift();
          }
        }
      }
      this.pausedOutputBuffer = [];
      this.pausedOutputSize = 0;
    }
    this._isPaused = false;
    this.resetTimer();
  }

  onInteractionSubmitted(): void {
    this.clearPromptDebounce();
    this.outputBuffer = [];
    this.lineBuffer = '';
    this.pausedOutputBuffer = [];
    this.pausedOutputSize = 0;
    this.escapeBuffer = '';
    this.lastOutputHash = '';
    this.hashUnchangedCount = 0;
    this.lastHashChangeTime = Date.now();
  }

  onDismiss(): void {
    this.dismissCount++;
    if (this.dismissCount >= 3) {
      this.doSuppress();
      this.emit('interaction-suppressed', { commandId: this.commandId });
      return;
    }
    if (this.dismissCount >= 2) {
      this.currentTimeout = this.config.maxTimeout;
    }
    this.resume();
  }

  suppress(): void {
    this.doSuppress();
    this.emit('interaction-suppressed', { commandId: this.commandId });
  }

  unsuppress(): void {
    this._isSuppressed = false;
    this.dismissCount = 0;
    this.currentTimeout = this.config.initialTimeout;
    this.resume();
  }

  dispose(): void {
    this._disposed = true;
    this.cancelPagerObservation();
    this.clearPromptDebounce();
    this.cancelTuiSilenceTimer();
    this.cancelTuiHardTimeout();
    if (this.timer) {
      clearTimeout(this.timer);
      this.timer = null;
    }
    this._isSuppressed = false;
    this.dismissCount = 0;
    this.removeAllListeners();
  }

  getState(): { isPaused: boolean; isSuppressed: boolean; isPager: boolean; inAlternateScreen: boolean } {
    return {
      isPaused: this._isPaused,
      isSuppressed: this._isSuppressed,
      isPager: this.isPager,
      inAlternateScreen: this.inAlternateScreen,
    };
  }

  // ============================================================================
  // Private methods
  // ============================================================================

  private isPagerCommand(): boolean {
    return this.PAGER_COMMANDS.some(p => p.test(this.command.trim()));
  }

  private classifyTuiCommand(): TuiCategory {
    const cmd = this.command.trim();
    if (this.isPagerCommand()) return null;
    if (this.ALWAYS_TUI_COMMANDS.some(p => p.test(cmd))) return 'always';
    for (const entry of this.CONDITIONAL_TUI_COMMANDS) {
      if (entry.pattern.test(cmd)) {
        if (entry.nonInteractiveArgs.some(arg => arg.test(cmd))) return null;
        return 'conditional';
      }
    }
    return 'non-blacklist';
  }

  private checkPagerOutput(output: string): boolean {
    const lastLine = output.trim().split('\n').pop() ?? '';
    if (this.PAGER_OUTPUT_PATTERNS.some(p => p.test(lastLine))) return true;
    return false;
  }

  private appendToPausedBuffer(data: string): void {
    this.pausedOutputBuffer.push(data);
    this.pausedOutputSize += data.length;
  }

  private processOutputForDetection(data: string): void {
    this.lineBuffer += data;
    if (this.lineBuffer.length > this.config.lineBufferMaxLength) {
      this.lineBuffer = this.lineBuffer.slice(-this.config.lineBufferMaxLength);
    }
    const lines = this.lineBuffer.split('\n');
    this.lineBuffer = lines.pop() ?? '';
    for (const line of lines) {
      const trimmedLine = line.trim();
      if (trimmedLine) {
        this.outputBuffer.push(trimmedLine);
        while (this.outputBuffer.length > this.config.maxLines) {
          this.outputBuffer.shift();
        }
      }
    }
  }

  private getFullOutput(): string {
    return this.outputBuffer.slice(-this.config.maxLines).join('\n');
  }

  private getLlmOutput(): string {
    return this.outputBuffer.slice(-this.config.maxLines).join('\n').slice(-this.config.maxLlmContextLength);
  }

  private tryQuickMatch(output: string): InteractionResult | null {
    for (const rule of this.QUICK_PATTERNS) {
      if (rule.pattern.test(output)) {
        return {
          needsInteraction: true,
          interactionType: rule.type,
          promptHint: this.getDefaultHint(rule.type),
          confirmValues: rule.confirmValues,
          exitKey: rule.exitKey,
          exitAppendNewline: rule.exitAppendNewline,
        };
      }
    }
    return null;
  }

  private getDefaultHint(type: string): string {
    const hints: Record<string, string> = {
      password: 'Password required',
      confirm: 'Confirmation needed',
      select: 'Please select an option',
      pager: 'Pager mode - press q to exit',
      enter: 'Press Enter to continue',
      freeform: 'Input required',
    };
    return hints[type] ?? 'Input required';
  }

  private resetTimer(): void {
    if (this.timer) clearTimeout(this.timer);
    this.timer = setTimeout(() => void this.onTimerExpired(), this.currentTimeout);
  }

  private async onTimerExpired(): Promise<void> {
    if (this._isPaused || this._isSuppressed || this.isDetecting) return;

    // Check for silent timeout
    const elapsed = Date.now() - this.lastOutputTime;
    if (elapsed > this.config.maxSilentTimeout) {
      // Command likely finished without user interaction
      return;
    }

    // Check output hash for duplicates
    const fullOutput = this.getLlmOutput();
    const hash = simpleHash(fullOutput);
    if (hash === this.lastOutputHash) {
      this.hashUnchangedCount++;
      if (this.hashUnchangedCount >= this.config.maxHashUnchangedCount) {
        // Output unchanged for too long, force detection
        this.debug('hash-unchanged-force-detect');
      }
    } else {
      this.lastOutputHash = hash;
      this.hashUnchangedCount = 0;
      this.lastHashChangeTime = Date.now();
    }

    // Try LLM detection
    if (this.llmCaller && this.llmCallCount < this.config.maxLlmCalls) {
      await this.llmDetect();
    } else if (!this.warnedMissingLlm) {
      this.warnedMissingLlm = true;
      this.debug('no-llm-caller');
    }

    // Exponential backoff
    this.currentTimeout = Math.min(this.currentTimeout * 2, this.config.maxTimeout);
    this.resetTimer();
  }

  private async llmDetect(): Promise<void> {
    if (!this.llmCaller || this.isDetecting) return;
    this.isDetecting = true;
    this.llmCallCount++;

    try {
      const result = await this.llmCaller(
        this.command,
        this.getLlmOutput(),
        this.config.userLocale
      );

      if (result.needsInteraction) {
        // Debounce to prevent false triggers
        this.pendingPromptResult = result;
        this.promptDebounceTimer = setTimeout(() => {
          if (this.pendingPromptResult) {
            const finalResult = this.pendingPromptResult;
            this.pendingPromptResult = null;
            this.pause();
            this.emitInteractionNeeded({
              commandId: this.commandId,
              ...finalResult,
            });
          }
        }, this.PROMPT_DEBOUNCE_MS);
      }
    } catch (error) {
      this.networkFailCount++;
      if (this.networkFailCount >= this.config.maxNetworkFails) {
        this.currentTimeout = this.config.maxTimeout;
      }
      console.error('[InteractionDetector] LLM call error', error);
    } finally {
      this.isDetecting = false;
    }
  }

  private emitInteractionNeeded(request: InteractionRequest): void {
    this.emit('interaction-needed', request);
  }

  private clearPromptDebounce(): void {
    if (this.promptDebounceTimer) {
      clearTimeout(this.promptDebounceTimer);
      this.promptDebounceTimer = null;
    }
    this.pendingPromptResult = null;
  }

  private doSuppress(): void {
    this._isSuppressed = true;
    this.dismissCount = 0;
    if (this.timer) {
      clearTimeout(this.timer);
      this.timer = null;
    }
  }

  private normalizeCR(data: string): string {
    // Convert \r\n to \n, then standalone \r to \n
    return data.replace(/\r\n/g, '\n').replace(/\r/g, '\n');
  }

  private startPagerObservation(): void {
    this.pagerObservationMode = true;
    this.cancelPagerObservation();
    this.pagerObservationTimer = setTimeout(() => {
      this.pagerObservationMode = false;
    }, this.config.pagerObservationTimeout);
  }

  private cancelPagerObservation(): void {
    this.pagerObservationMode = false;
    if (this.pagerObservationTimer) {
      clearTimeout(this.pagerObservationTimer);
      this.pagerObservationTimer = null;
    }
  }

  private startTuiSilenceTimer(): void {
    this.cancelTuiSilenceTimer();
    this.tuiSilenceTimer = setTimeout(() => {
      // TUI has gone silent — likely waiting for user interaction
      // But we're in a non-interactive session, so emit the event
      this.emit('tui-detected', {
        commandId: this.commandId,
        taskId: this.taskId,
        message: 'TUI program detected - user interaction required',
        isShellSpawning: this.isShellSpawning,
      });
    }, this.config.tuiCancelSilenceMs);
  }

  private cancelTuiSilenceTimer(): void {
    if (this.tuiSilenceTimer) {
      clearTimeout(this.tuiSilenceTimer);
      this.tuiSilenceTimer = null;
    }
  }

  private startTuiHardTimeout(): void {
    this.cancelTuiHardTimeout();
    this.tuiHardTimeoutTimer = setTimeout(() => {
      // Emit TUI detected early for blacklisted commands
      if (this.tuiCategory === 'always') {
        this.emit('tui-detected', {
          commandId: this.commandId,
          taskId: this.taskId,
          message: 'TUI program detected - cancelling interaction',
          isShellSpawning: this.isShellSpawning,
        });
      }
    }, this.config.tuiHardTimeoutMs);
  }

  private cancelTuiHardTimeout(): void {
    if (this.tuiHardTimeoutTimer) {
      clearTimeout(this.tuiHardTimeoutTimer);
      this.tuiHardTimeoutTimer = null;
    }
  }

  private debug(label: string, data?: unknown): void {
    if (this.debugEnabled) {
      console.log(`[InteractionDetector:${this.commandId}] ${label}`, data ?? '');
    }
  }
}
