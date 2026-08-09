"use client";

import { FitAddon } from '@xterm/addon-fit';
import { WebLinksAddon } from '@xterm/addon-web-links';
import { Terminal } from '@xterm/xterm';
import { TerminalSquare, RefreshCw } from 'lucide-react';
import React, { useEffect, useRef, useState, useCallback, forwardRef, useImperativeHandle } from 'react';

import '@xterm/xterm/css/xterm.css';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';

import { PromptInterceptor } from './prompt-interceptor';

export interface WebTerminalRef {
  injectCommand: (cmd: string) => void;
  executeAndCapture: (cmd: string, timeoutMs?: number) => Promise<string>;
}

export interface WebTerminalProps {
  className?: string;
  wsUrl?: string; // WebSocket connection URL
  onData?: (data: string) => void;
  theme?: 'light' | 'dark' | 'hacker';
  onStatusChange?: (status: 'connecting' | 'connected' | 'disconnected' | 'error') => void;
}

export const WebTerminal = forwardRef<WebTerminalRef, WebTerminalProps>(({ className, wsUrl, onData, theme = 'light', onStatusChange }, ref) => {
  const terminalRef = useRef<HTMLDivElement>(null);
  const termInstance = useRef<Terminal | null>(null);
  const fitAddon = useRef<FitAddon | null>(null);
  const ws = useRef<WebSocket | null>(null);
  const interceptorRef = useRef(new PromptInterceptor());

  const [connected, setConnected] = useState(false);

  const onStatusChangeRef = useRef(onStatusChange);
  useEffect(() => {
    onStatusChangeRef.current = onStatusChange;
  }, [onStatusChange]);

  const connectWs = useCallback(() => {
    if (!wsUrl || !termInstance.current) return;

    if (ws.current) {
      ws.current.onclose = null;
      ws.current.onerror = null;
      ws.current.close();
    }

    onStatusChangeRef.current?.('connecting');
    const socket = new WebSocket(wsUrl);
    ws.current = socket;

    socket.onopen = () => {
      setConnected(true);
      onStatusChangeRef.current?.('connected');
      termInstance.current?.writeln('\x1b[32m[Connected to server]\x1b[0m');
    };

    socket.onmessage = (event) => {
      if (typeof event.data === 'string') {
        termInstance.current?.write(event.data);
        interceptorRef.current.appendData(event.data);
        onData?.(event.data);
      }
    };

    socket.onclose = () => {
      setConnected(false);
      onStatusChangeRef.current?.('disconnected');
      termInstance.current?.writeln('\r\n\x1b[31m[Disconnected from server]\x1b[0m');
    };

    socket.onerror = () => {
      onStatusChangeRef.current?.('error');
      termInstance.current?.writeln('\r\n\x1b[31m[WebSocket Error]\x1b[0m');
    };
  }, [wsUrl, onData]);

  useEffect(() => {
    if (!terminalRef.current) return;

    // Initialize Terminal
    const term = new Terminal({
      cursorBlink: true,
      theme: theme === 'light' ? {
        background: '#ffffff',
        foreground: '#333333',
        cursor: '#333333',
        selectionBackground: 'rgba(0, 100, 255, 0.2)',
        black: '#000000',
        blue: '#2563eb',
        brightBlue: '#3b82f6',
        green: '#16a34a',
        brightGreen: '#22c55e',
      } : theme === 'hacker' ? {
        background: '#0a0a0a',
        foreground: '#22c55e',
        cursor: '#22c55e',
        selectionBackground: 'rgba(34, 197, 94, 0.3)',
        black: '#0a0a0a',
        blue: '#3b82f6',
        brightBlue: '#60a5fa',
        green: '#22c55e',
        brightGreen: '#4ade80',
      } : {
        background: '#0d1117',
        foreground: '#c9d1d9',
        cursor: '#58a6ff',
        selectionBackground: 'rgba(88, 166, 255, 0.3)',
      },
      fontFamily: 'Menlo, Monaco, "Courier New", monospace',
      fontSize: 14,
    });
    
    termInstance.current = term;

    // Addons
    const fit = new FitAddon();
    fitAddon.current = fit;
    term.loadAddon(fit);
    term.loadAddon(new WebLinksAddon());

    term.open(terminalRef.current);
    fit.fit();

    term.writeln('\x1b[1;34mPrismOS\x1b[0m Terminal Ready. Connecting...');

    // On Data from Xterm (User typed something)
    term.onData((data) => {
      if (ws.current?.readyState === WebSocket.OPEN) {
        ws.current.send(data);
      }
    });

    const handleResize = () => {
      fit.fit();
      if (ws.current?.readyState === WebSocket.OPEN) {
        // Send resize event to backend (e.g. JSON format or special command)
        // Adjust this depending on how the backend expects resize signals
        ws.current.send(JSON.stringify({
          type: 'resize',
          cols: term.cols,
          rows: term.rows,
        }));
      }
    };

    const resizeObserver = new ResizeObserver(() => {
      // Small delay to ensure container dimensions have settled
      setTimeout(() => {
        if (terminalRef.current) {
          handleResize();
        }
      }, 50);
    });

    if (terminalRef.current) {
      resizeObserver.observe(terminalRef.current);
    }
    window.addEventListener('resize', handleResize);

    // Initial connect
    connectWs();

    return () => {
      window.removeEventListener('resize', handleResize);
      resizeObserver.disconnect();
      if (ws.current) {
        ws.current.onclose = null;
        ws.current.onerror = null;
        ws.current.close();
      }
      term.dispose();
    };
  }, [connectWs]);

  // Update theme dynamically without recreating the terminal
  useEffect(() => {
    if (termInstance.current) {
      termInstance.current.options.theme = theme === 'light' ? {
        background: '#ffffff',
        foreground: '#333333',
        cursor: '#333333',
        selectionBackground: 'rgba(0, 100, 255, 0.2)',
        black: '#000000',
        blue: '#2563eb',
        brightBlue: '#3b82f6',
        green: '#16a34a',
        brightGreen: '#22c55e',
      } : theme === 'hacker' ? {
        background: '#0a0a0a',
        foreground: '#22c55e',
        cursor: '#22c55e',
        selectionBackground: 'rgba(34, 197, 94, 0.3)',
        black: '#0a0a0a',
        blue: '#3b82f6',
        brightBlue: '#60a5fa',
        green: '#22c55e',
        brightGreen: '#4ade80',
      } : {
        background: '#0d1117',
        foreground: '#c9d1d9',
        cursor: '#58a6ff',
        selectionBackground: 'rgba(88, 166, 255, 0.3)',
      };
    }
  }, [theme]);

  // Expose methods to parent components
  useImperativeHandle(ref, () => ({
    injectCommand: (cmd: string) => {
      if (ws.current?.readyState === WebSocket.OPEN) {
        ws.current.send(cmd + '\r');
      }
    },
    executeAndCapture: (cmd: string, timeoutMs = 30000): Promise<string> => {
      return new Promise((resolve, reject) => {
        if (ws.current?.readyState !== WebSocket.OPEN) {
          reject(new Error('Terminal is not connected.'));
          return;
        }

        interceptorRef.current.startCapture(cmd, (output) => {
          resolve(output);
        }, timeoutMs);

        // Send the command
        ws.current.send(cmd + '\r');
      });
    }
  }));

  return (
    <div className={cn('flex flex-col size-full overflow-hidden relative group', className)}>
      {/* Terminal Container */}
      <div className={cn("flex-1 p-2 overflow-hidden", theme === 'light' ? 'bg-white' : theme === 'hacker' ? 'bg-[#0a0a0a]' : 'bg-[#0d1117]')} ref={terminalRef} />
      
      {/* Floating Reconnect Button (shows on hover if disconnected) */}
      {!connected && (
        <div className="absolute top-2 right-4 opacity-0 group-hover:opacity-100 transition-opacity">
          <Button variant="secondary" size="sm" className="h-7 text-xs bg-zinc-800 hover:bg-zinc-700 text-zinc-300 border-zinc-700" onClick={connectWs}>
            <RefreshCw className="w-3 h-3 mr-1.5" />
            Reconnect
          </Button>
        </div>
      )}
    </div>
  );
});

WebTerminal.displayName = 'WebTerminal';
