"use client";

import { 
  Monitor, 
  X, 
  Bot,
  PanelLeftOpenIcon,
  Palette
} from 'lucide-react';
import { usePathname, useSearchParams, useRouter } from 'next/navigation';
import React, { useState, useEffect, useRef, useMemo, useCallback } from 'react';
import { toast } from 'sonner';


import { TerminalContext } from '@/app/workspace/terminal/context';
import { TerminalAgentUI } from '@/app/workspace/terminal/terminal-agent-ui';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { ResizablePanel } from '@/components/ui/resizable-panel';
import { AssetSidebar } from '@/components/workspace/terminal/asset-sidebar';
import { WebTerminal } from '@/components/workspace/terminal/web-terminal';
import type { WebTerminalRef } from '@/components/workspace/terminal/web-terminal';
import { decodeContextFromURL, type IncidentContext } from '@/core/alerting/incident-context';
import { useSkillQueryIdentity } from '@/core/skills/query-identity';
import type { TerminalAsset, TerminalAssetGroup, TerminalCredential } from '@/core/terminal-agent/message-types';
import {
  loadHostSidebarCollapsed,
  loadTerminalTheme,
  saveHostSidebarCollapsed,
  saveTerminalTheme,
  type TerminalTheme,
} from '@/core/terminal-agent/terminal-preferences';

/**
 * Try to match an incident's service to an asset in the asset list.
 * Rules: exact name match → fuzzy name match → null.
 */
function tryMatchAsset(ctx: IncidentContext, assets: TerminalAsset[]): TerminalAsset | null {
  if (!ctx.service || assets.length === 0) return null;

  const service = ctx.service.toLowerCase();

  // 1. Exact match: asset.name === service
  const exact = assets.find(a => a.name?.toLowerCase() === service);
  if (exact) return exact;

  // 2. Fuzzy match: asset.name contains service, or service contains asset.name
  const fuzzy = assets.find(a => {
    const name = (a.name ?? '').toLowerCase();
    return name.includes(service) || service.includes(name);
  });
  if (fuzzy) return fuzzy;

  return null;
}

export function PersistentTerminal() {
  const identity = useSkillQueryIdentity();
  const identityRef = useRef(identity);
  identityRef.current = identity;
  const requestGeneration = useRef(0);
  const [loadedIdentity, setLoadedIdentity] = useState<string | null>(null);
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const router = useRouter();
  const isTerminalPage = pathname?.startsWith('/workspace/terminal');

  const [isSidebarCollapsed, setIsSidebarCollapsed] = useState(false);
  const [openSessions, setOpenSessions] = useState<{sessionId: string, asset: TerminalAsset, title: string, status?: 'connecting' | 'connected' | 'disconnected' | 'error'}[]>([]);
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  const [isAgentOpen, setIsAgentOpen] = useState(false);
  const [terminalTheme, setTerminalTheme] = useState<'light' | 'dark' | 'hacker'>('light');
  const [incidentContext, setIncidentContext] = useState<IncidentContext | null>(null);
  const [assets, setAssets] = useState<TerminalAsset[]>([]);
  const [credentials, setCredentials] = useState<TerminalCredential[]>([]);
  const [groups, setGroups] = useState<TerminalAssetGroup[]>([]);

  // Track the last consumed context to avoid duplicate processing
  const lastConsumedCtxRef = useRef<string | null>(null);
  const visibleSessions = loadedIdentity === identity.key && identity.identityReady ? openSessions : [];

  // Centralized data fetching — shared with AssetSidebar
  const fetchAssets = useCallback(async () => {
    const scope = identityRef.current;
    const generation = ++requestGeneration.current;
    const current = () => generation === requestGeneration.current && scope.key === identityRef.current.key && scope.isCurrent();
    if (!scope.identityReady) return;
    try {
      const responses = await Promise.all([
        fetch('/api/v1/assets/local', { cache: 'no-store' }),
        fetch('/api/v1/assets/keychains', { cache: 'no-store' }),
        fetch('/api/v1/assets/groups', { cache: 'no-store' }),
      ]);
      if (!current()) return;
      if (responses.some(response => !response.ok)) throw new Error('Current asset scope unavailable');
      const values = await Promise.all(responses.map(response => response.json()));
      if (!current()) return;
      if (values.some(value => !Array.isArray(value))) throw new Error("Invalid current asset list");
      setAssets(values[0] as TerminalAsset[]);
      setCredentials(values[1] as TerminalCredential[]);
      setGroups(values[2] as TerminalAssetGroup[]);
      setLoadedIdentity(scope.key);
    } catch {
      if (!current()) return;
      setAssets([]); setCredentials([]); setGroups([]); setLoadedIdentity(null);
      setOpenSessions([]); setActiveSessionId(null);
    }
  }, []);

  useEffect(() => {
    setAssets([]); setCredentials([]); setGroups([]); setLoadedIdentity(null);
    setOpenSessions([]); setActiveSessionId(null); setIncidentContext(null);
    void fetchAssets();
    return () => { requestGeneration.current += 1; };
  }, [identity.key, identity.identityReady, fetchAssets]);

  // Load saved preferences
  useEffect(() => {
    const savedSidebar = loadHostSidebarCollapsed(localStorage);
    if (savedSidebar === true) {
      setIsSidebarCollapsed(true);
    }
    
    const savedTheme = loadTerminalTheme(localStorage);
    if (savedTheme) {
      setTerminalTheme(savedTheme);
    }

  }, []);

  // Handle incoming incident context from URL
  useEffect(() => {
    const ctxParam = searchParams.get('ctx');
    if (!ctxParam) return;

    // Skip if we've already processed this exact context
    if (lastConsumedCtxRef.current === ctxParam) return;

    const ctx = decodeContextFromURL(ctxParam);
    if (!ctx) return;

    // Mark as consumed so we don't reprocess on re-renders
    lastConsumedCtxRef.current = ctxParam;

    setIncidentContext(ctx);
    setIsAgentOpen(true);

    // Try to match service to an asset
    const matched = tryMatchAsset(ctx, assets);
    if (matched) {
      // Auto-create session for matched asset
      handleSelectAsset(matched);
    } else if (assets.length === 0) {
      // No hosts registered at all — guide user to add one
      toast.warning('当前没有已注册的主机，请先在左侧主机管理中添加目标主机和 SSH 凭证。');
    }
    // If assets exist but no match, user can manually pick from sidebar

    // Clean up URL params to prevent re-injection on refresh, but keep it
    // in the URL long enough for the agent to consume it
    router.replace('/workspace/terminal', { scroll: false });
  }, [searchParams, assets]);

  const handleThemeChange = (theme: TerminalTheme) => {
    setTerminalTheme(theme);
    saveTerminalTheme(localStorage, theme);
  };

  const handleToggleSidebar = () => {
    setIsSidebarCollapsed((prev) => {
      const next = !prev;
      saveHostSidebarCollapsed(localStorage, next);
      return next;
    });
  };

  const wsBaseUrl = typeof window !== 'undefined' 
    ? `${window.location.protocol === 'https:' ? 'wss:' : 'ws:'}//${window.location.host}` 
    : '';

  // Terminal refs map for routing commands
  const terminalRefs = useRef<Record<string, WebTerminalRef | null>>({});
  const sendMessageRef = useRef<((text: string) => void) | null>(null);

  const handleSelectAsset = (asset: TerminalAsset) => {
    if (loadedIdentity !== identity.key || !identity.isCurrent()) return;
    const sessionId = 'sess_' + Date.now().toString() + '_' + Math.random().toString(36).substring(2, 9);
    setOpenSessions((prev) => {
      const existingCount = prev.filter((s) => s.asset.id === asset.id).length;
      const baseTitle = asset.name ?? asset.ip;
      const title = existingCount > 0 ? `${baseTitle} (${existingCount + 1})` : baseTitle;
      return [...prev, { sessionId, asset, title }];
    });
    setActiveSessionId(sessionId);
  };

  const handleCloseSession = (sessionId: string) => {
    setOpenSessions((prev) => {
      const filtered = prev.filter((s) => s.sessionId !== sessionId);
      if (activeSessionId === sessionId) {
        // Switch to the last remaining tab, or null
        const lastSession = filtered[filtered.length - 1];
        setActiveSessionId(lastSession ? lastSession.sessionId : null);
      }
      return filtered;
    });
    // Cleanup ref
    delete terminalRefs.current[sessionId];
  };

  const handleStatusChange = (sessionId: string, status: 'connecting' | 'connected' | 'disconnected' | 'error') => {
    setOpenSessions((prev) => prev.map((s) => s.sessionId === sessionId ? { ...s, status } : s));
  };

  const executeCommand = async (cmd: string): Promise<string> => {
    if (!activeSessionId) {
      throw new Error("No active terminal tab");
    }
    const term = terminalRefs.current[activeSessionId];
    if (!term) {
      throw new Error("Terminal is not ready");
    }
    return term.executeAndCapture(cmd);
  };

  // Provide the current active terminal's ref
  const activeTerminalRef = useMemo(() => {
    return {
      get current() {
        if (!activeSessionId) return null;
        return terminalRefs.current[activeSessionId] ?? null;
      }
    };
  }, [activeSessionId]);

  const activeAsset = useMemo(() => {
    const session = openSessions.find((s) => s.sessionId === activeSessionId);
    return session?.asset ?? null;
  }, [openSessions, activeSessionId]);

  return (
    <TerminalContext.Provider value={{ terminalRef: activeTerminalRef as React.RefObject<WebTerminalRef | null>, executeCommand, sendMessageRef, activeSessionId }}>
      <div className={`${isTerminalPage ? 'flex size-full bg-white text-zinc-800 overflow-hidden text-[13px]' : 'hidden'}`}>
        
        {/* 1. Left Panel: Asset Management */}
        <AssetSidebar
            key={identity.key}
          onSelectAsset={handleSelectAsset} 
          isCollapsed={isSidebarCollapsed}
          onToggleCollapse={handleToggleSidebar}
          assets={loadedIdentity === identity.key && identity.identityReady ? assets : []}
          credentials={loadedIdentity === identity.key && identity.identityReady ? credentials : []}
          groups={loadedIdentity === identity.key && identity.identityReady ? groups : []}
          onDataChanged={fetchAssets}
        />

        {/* 2. Middle Panel: Terminal View (fills remaining space) */}
        <div className="flex-1 flex flex-col min-w-0 bg-white">
          {/* Terminal Header Tabs */}
          <div className="flex items-end justify-between h-10 border-b border-zinc-200 bg-zinc-50/80 px-2 overflow-x-auto overflow-y-hidden hide-scrollbar">
            <div className="flex items-end gap-1 shrink-0 pt-1 h-full">
              {isSidebarCollapsed && (
                <button
                  onClick={handleToggleSidebar}
                  className="flex items-center justify-center h-8 w-8 text-zinc-400 hover:text-zinc-600 hover:bg-zinc-200/50 rounded-lg mb-1 mr-1 shrink-0 transition-colors"
                  title="展开主机管理"
                >
                  <PanelLeftOpenIcon className="w-4 h-4" />
                </button>
              )}
              {visibleSessions.map((session) => (
                <div 
                  key={session.sessionId}
                  onClick={() => setActiveSessionId(session.sessionId)}
                  className={`flex items-center gap-2 px-3 py-1.5 border rounded-t-lg -mb-px cursor-pointer select-none transition-colors ${
                    activeSessionId === session.sessionId 
                      ? 'bg-white border-zinc-200 border-b-white text-blue-600 font-medium z-10' 
                      : 'bg-zinc-50/50 border-transparent text-zinc-500 hover:bg-zinc-100 hover:text-zinc-700'
                  }`}
                >
                  <div className="relative shrink-0">
                    <Monitor className={`w-4 h-4 ${activeSessionId === session.sessionId ? 'text-blue-500' : 'text-zinc-400'}`} />
                    {session.status && (
                      <span className={`absolute -bottom-0.5 -right-0.5 size-2 rounded-full border border-white shadow-sm ${
                        session.status === 'connected' ? 'bg-emerald-500' :
                        session.status === 'connecting' ? 'bg-amber-400 animate-pulse' :
                        session.status === 'error' ? 'bg-red-500' :
                        'bg-zinc-400'
                      }`}></span>
                    )}
                  </div>
                  <span className="truncate max-w-[120px]" title={session.title}>{session.title}</span>
                  <button 
                    className="hover:bg-zinc-200/50 rounded-sm p-0.5 ml-1 text-zinc-400 hover:text-zinc-600" 
                    onClick={(e) => {
                      e.stopPropagation();
                      handleCloseSession(session.sessionId);
                    }}
                  >
                    <X className="w-3.5 h-3.5" />
                  </button>
                </div>
              ))}
            </div>
            
            <div className="mb-1 shrink-0 sticky right-0 bg-gradient-to-l from-zinc-50/80 via-zinc-50/80 to-transparent pl-4 flex items-center gap-1">
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <button 
                    className="flex items-center justify-center w-7 h-7 text-zinc-400 hover:text-zinc-600 hover:bg-zinc-200/50 rounded-md transition-colors"
                    title="切换终端主题"
                  >
                    <Palette className="w-3.5 h-3.5" />
                  </button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end" className="w-32">
                  <DropdownMenuItem onClick={() => handleThemeChange('light')}>
                    <span className={terminalTheme === 'light' ? 'font-medium' : ''}>亮色 (Light)</span>
                  </DropdownMenuItem>
                  <DropdownMenuItem onClick={() => handleThemeChange('dark')}>
                    <span className={terminalTheme === 'dark' ? 'font-medium' : ''}>暗色 (Dark)</span>
                  </DropdownMenuItem>
                  <DropdownMenuItem onClick={() => handleThemeChange('hacker')}>
                    <span className={terminalTheme === 'hacker' ? 'text-emerald-500 font-medium' : ''}>骇客 (Hacker)</span>
                  </DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>

              <button 
                onClick={() => setIsAgentOpen(!isAgentOpen)}
                className={`flex items-center gap-1.5 px-3 py-1 text-xs font-medium rounded-md transition-colors ${
                  isAgentOpen ? 'bg-blue-50 text-blue-600' : 'text-zinc-500 hover:bg-zinc-200/50'
                }`}
              >
                <Bot className="w-3.5 h-3.5" />
                {isAgentOpen ? '收起助手' : 'AI 助手'}
              </button>
            </div>
          </div>
          
          {/* Terminal Content Area */}
          <div className={`flex-1 p-2 relative ${terminalTheme === 'light' ? 'bg-[#ffffff]' : terminalTheme === 'hacker' ? 'bg-[#0a0a0a]' : 'bg-[#0d1117]'}`}>
            {visibleSessions.length > 0 ? (
              visibleSessions.map((session) => (
                <div 
                  key={`term-${session.sessionId}`} 
                  className={`absolute inset-2 ${activeSessionId === session.sessionId ? 'block' : 'hidden'}`}
                >
                  {/* WebTerminal will dynamically update xterm theme without unmounting, keeping WebSocket alive */}
                  <WebTerminal 
                    ref={(el) => { terminalRefs.current[session.sessionId] = el; }}
                    wsUrl={wsBaseUrl ? `${wsBaseUrl}/api/v1/terminal/ws?asset_id=${session.asset.id}&session_id=${session.sessionId}` : ''} 
                    theme={terminalTheme} 
                    className="absolute inset-0"
                    onStatusChange={(status) => handleStatusChange(session.sessionId, status)}
                  />
                </div>
              ))
            ) : (
              <div className="absolute inset-0 flex flex-col items-center justify-center text-zinc-400">
                <div className="w-16 h-16 rounded-full bg-zinc-50 border border-zinc-100 flex items-center justify-center mb-4 shadow-sm">
                  <Monitor className="w-8 h-8 text-zinc-300" />
                </div>
                <p className="text-sm font-medium text-zinc-500">未选择主机</p>
                <p className="text-xs mt-1">请在左侧侧边栏选择一台主机以建立 SSH 连接</p>
              </div>
            )}
          </div>
        </div>

        {/* 3. Right Panel: Resizable Agent Chat */}
        {isAgentOpen && (
          <ResizablePanel
            defaultWidth={420}
            minWidth={320}
            maxWidth={800}
            position="right"
          >
            <TerminalAgentUI activeAsset={activeAsset} injectedContext={incidentContext} />
          </ResizablePanel>
        )}
      </div>
    </TerminalContext.Provider>
  );
}
