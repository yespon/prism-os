"use client";

import { useSearchParams } from 'next/navigation';

import { useLocalSettings } from '@/core/settings';

export default function TerminalPage() {
  // This page is intentionally left mostly empty.
  // The actual terminal UI is rendered globally via `PersistentTerminal` 
  // in `workspace-layout-client.tsx` to keep WebSockets alive during navigation.
  
  return null;
}
