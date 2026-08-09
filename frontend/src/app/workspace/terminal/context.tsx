"use client";

import React, { createContext, useContext, useRef, useState } from "react";

import type { WebTerminalRef } from "@/components/workspace/terminal/web-terminal";

interface TerminalContextValue {
  terminalRef: React.RefObject<WebTerminalRef | null>;
  executeCommand: (cmd: string) => Promise<string>;
  sendMessageRef: React.MutableRefObject<((text: string) => void) | null>;
  activeSessionId?: string | null;
}

export const TerminalContext = createContext<TerminalContextValue | null>(null);

export function useTerminalContext() {
  return useContext(TerminalContext);
}

export function TerminalProvider({ children }: { children: React.ReactNode }) {
  const terminalRef = useRef<WebTerminalRef>(null);
  const sendMessageRef = useRef<((text: string) => void) | null>(null);

  const executeCommand = async (cmd: string): Promise<string> => {
    if (!terminalRef.current) {
      throw new Error("Terminal is not ready");
    }
    return terminalRef.current.executeAndCapture(cmd);
  };

  return (
    <TerminalContext.Provider value={{ terminalRef, executeCommand, sendMessageRef }}>
      {children}
    </TerminalContext.Provider>
  );
}
