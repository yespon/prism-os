/**
 * A utility class to intercept and capture terminal output for a specific command execution.
 * It listens to the xterm.js output stream and stops when it detects the terminal prompt.
 */
export class PromptInterceptor {
  private buffer = '';
  private isCapturing = false;
  private command = '';
  private onComplete: ((output: string) => void) | null = null;
  private timeoutId: NodeJS.Timeout | null = null;

  // Common prompt regex (e.g. user@host:~$ or root@host:/#)
  private readonly promptRegex = /[\w\-\.]+@[\w\-\.]+:[^\n\r]+[\$#]\s*$/;

  startCapture(command: string, onComplete: (output: string) => void, timeoutMs = 30000) {
    this.buffer = '';
    this.command = command;
    this.isCapturing = true;
    this.onComplete = onComplete;

    if (this.timeoutId) {
      clearTimeout(this.timeoutId);
    }

    // Set a timeout to stop capturing if prompt is not detected
    this.timeoutId = setTimeout(() => {
      this.finishCapture(true);
    }, timeoutMs);
  }

  appendData(data: string) {
    if (!this.isCapturing) return;

    this.buffer += data;

    // Check if the output ends with a common bash/zsh prompt
    // Strip ANSI escape codes first to check cleanly
    const cleanData = this.stripAnsi(this.buffer);
    
    // If the clean data ends with a prompt, finish capturing
    if (this.promptRegex.test(cleanData.trimEnd())) {
      this.finishCapture(false);
    }
  }

  private finishCapture(isTimeout: boolean) {
    if (!this.isCapturing) return;

    this.isCapturing = false;
    if (this.timeoutId) {
      clearTimeout(this.timeoutId);
      this.timeoutId = null;
    }

    let cleanOutput = this.stripAnsi(this.buffer);
    
    // Remove the executed command echo from the beginning if present
    if (cleanOutput.startsWith(this.command)) {
      cleanOutput = cleanOutput.substring(this.command.length);
    }
    
    // Strip the trailing prompt
    const match = cleanOutput.match(this.promptRegex);
    if (match) {
      cleanOutput = cleanOutput.substring(0, match.index).trim();
    } else {
      cleanOutput = cleanOutput.trim();
    }

    // Replace terminal CR/LF with standard LF
    cleanOutput = cleanOutput.replace(/\r\n/g, '\n');

    if (this.onComplete) {
      this.onComplete(cleanOutput);
    }
  }

  private stripAnsi(str: string): string {
    const ansiRegex = /[\u001b\u009b][[()#;?]*(?:[0-9]{1,4}(?:;[0-9]{0,4})*)?[0-9A-ORZcf-nqry=><]/g;
    return str.replace(ansiRegex, '');
  }

  cancelCapture() {
    this.isCapturing = false;
    if (this.timeoutId) {
      clearTimeout(this.timeoutId);
      this.timeoutId = null;
    }
    this.buffer = '';
  }
}
