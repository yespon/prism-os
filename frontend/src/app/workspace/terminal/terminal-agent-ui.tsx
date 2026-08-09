'use client';

import {
  Monitor, X, Plus, RotateCcw, Pencil,
  Image as ImageIcon, ArrowUp, ChevronDown,
  Loader2, AlertTriangle, Settings, History, Check,
  Terminal as TerminalIcon, Sparkles, CornerDownLeft
} from 'lucide-react';
import React, { useState, useEffect, useRef, useCallback, useMemo } from 'react';
import { toast } from 'sonner';

import { useTerminalContext } from '@/app/workspace/terminal/context';
import { Button } from '@/components/ui/button';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { Input } from '@/components/ui/input';
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/components/ui/tooltip';
import { MarkdownContent } from '@/components/workspace/messages/markdown-content';
import { SaveAsSkillDialog, extractTerminalSession } from '@/components/workspace/terminal/save-as-skill-dialog';
import { type IncidentContext, renderContextPrompt } from '@/core/alerting/incident-context';
import { useAvailableModels } from '@/core/models/hooks';
import { ChatHistoryManager, type ChatSession } from '@/core/terminal-agent/chat-history';
import { CommandInteractionInput } from '@/core/terminal-agent/command-interaction-input';
import type { InteractionType as CommandInteractionType } from '@/core/terminal-agent/command-interaction-input';
import type {
  TerminalAsset,
  TerminalMessage,
  TerminalToolInvocation,
} from '@/core/terminal-agent/message-types';
import { isTerminalMessagePart } from '@/core/terminal-agent/message-types';
import { SecuritySettingsPanel } from '@/core/terminal-agent/security/security-settings-ui';
import { useTerminalAgent } from '@/core/terminal-agent/useTerminalAgent';

// ------------------------------------------------------------------
// Message Utility Functions
// ------------------------------------------------------------------

function getMessageText(msg: TerminalMessage): string {
  if (!msg) return '';
  let text = '';
  // LangGraph SDK format: message.content is string or [{type:'text', text:'...'}]
  if (typeof msg.content === 'string') text = msg.content;
  else if (Array.isArray(msg.content)) {
    text = msg.content.filter((p) => p.type === 'text').map((p) => p.text ?? '').join('\n');
  }
  // AI SDK v6 format: message.parts
  else if (Array.isArray(msg.parts)) {
    text = msg.parts.filter((p) => p.type === 'text').map((p) => p.text ?? '').join('\n');
  }
  // Replace escaped newlines with actual newlines
  return text.replace(/\\n/g, '\n');
}

function getReasoningText(msg: TerminalMessage): string {
  // LangGraph SDK: reasoning is in additional_kwargs or content parts
  const reasoning = msg.additional_kwargs?.reasoning;
  if (typeof reasoning === 'string' && reasoning.length > 0) return reasoning;
  const parts = Array.isArray(msg.content) ? msg.content : msg.parts;
  if (Array.isArray(parts)) {
    return parts.filter((p) => p.type === 'reasoning').map((p) => p.text ?? p.reasoning ?? '').join('\n');
  }
  return '';
}

/** Get the display role: 'user' | 'assistant'. LangGraph uses type='human'/'ai', AI SDK uses role='user'/'assistant'. */
function getMessageRole(msg: TerminalMessage): 'user' | 'assistant' {
  if (msg.role === 'user' || msg.type === 'human') return 'user';
  return 'assistant';
}

function getToolInvocations(msg: TerminalMessage): TerminalToolInvocation[] {
  if (!msg) return [];
  // LangGraph SDK: tool messages have type='tool'
  if (msg.type === 'tool') {
    return [{
      toolCallId: msg.tool_call_id,
      toolName: msg.name,
      state: 'output-available',    // tool has completed execution
      input: {},
      args: {},
      output: typeof msg.content === 'string' ? msg.content : JSON.stringify(msg.content),
    }];
  }
  // LangGraph SDK: AI message with tool_calls array (agent mode: auto-executed)
  if (Array.isArray(msg.tool_calls) && msg.tool_calls.length > 0) {
    return msg.tool_calls.map((tc) => ({
      toolCallId: tc.id,
      toolName: tc.name,
      state: 'output-available',    // in agent mode, tool is auto-executed
      input: tc.args ?? {},
      args: tc.args ?? {},
      output: undefined,
    }));
  }
  // AI SDK v6 parts format (legacy cmd mode)
  if (Array.isArray(msg.parts)) {
    return msg.parts
      .filter((p) => p.type?.startsWith('tool-') ?? p.type === 'dynamic-tool')
      .map((p) => {
        const toolName = p.toolName ?? (p.type?.startsWith('tool-') ? p.type.slice(5) : p.type) ?? 'unknown';
        return {
          toolCallId: p.toolCallId,
          toolName,
          state: p.state,
          input: p.input ?? {},
          args: p.input ?? {},
          output: p.output,
          errorText: p.errorText,
          approval: p.approval,
        };
      });
  }
  return [];
}

function summarizeOutput(output: unknown): string {
  const text = typeof output === 'string' ? output : JSON.stringify(output ?? '');
  const lines = text.split('\n').map(line => line.trim()).filter(Boolean);
  if (lines.length === 0) return '命令已执行，无输出。';
  const errorLine = lines.find(line => /error|failed|denied|exception|not found/i.test(line));
  const firstLine = errorLine ?? lines[0] ?? '';
  return firstLine.length > 160 ? `${firstLine.slice(0, 160)}...` : firstLine;
}

function riskLabel(level?: string): string {
  if (level === 'critical') return '严重风险';
  if (level === 'high') return '高风险';
  if (level === 'medium') return '中风险';
  return '低风险';
}

function assetLabel(asset: TerminalAsset | null | undefined): string {
  return asset?.ip ?? asset?.hostname ?? asset?.name ?? asset?.id ?? '未知主机';
}

const ignoreInteractionCommand = (_commandId: string): void => undefined;
const ignoreTerminalFocus = (): void => undefined;

// ------------------------------------------------------------------
// TerminalAgentUI Component
// ------------------------------------------------------------------

export function TerminalAgentUI({ activeAsset, injectedContext }: { activeAsset: TerminalAsset | null; injectedContext?: IncidentContext | null }) {
  const terminalContext = useTerminalContext();
  const { models } = useAvailableModels();
  const [selectedModel, setSelectedModel] = useState<string>('gpt-4o');
  const [showSecuritySettings, setShowSecuritySettings] = useState(false);
  const [showHistory, setShowHistory] = useState(false);
  const [sessionId, setSessionId] = useState(() => ChatHistoryManager.generateId());
  const [sessionTitle, setSessionTitle] = useState('新会话');
  const [messageFeedback, setMessageFeedback] = useState<Record<string, 'up' | 'down'>>({});
  const [mode, setMode] = useState<'cmd' | 'agent'>(injectedContext ? 'agent' : 'cmd');
  const [showContextMenu, setShowContextMenu] = useState(false);
  const [contextMenuSearch, setContextMenuSearch] = useState('');
  const [assets, setAssets] = useState<TerminalAsset[]>([]);
  const [isRefreshingAssets, setIsRefreshingAssets] = useState(false);
  const [selectedAgentAssets, setSelectedAgentAssets] = useState<TerminalAsset[]>([]);
  const [input, setInput] = useState('');
  const [editingSessionId, setEditingSessionId] = useState<string | null>(null);
  const [editingSessionTitle, setEditingSessionTitle] = useState('');
  const chatEndRef = useRef<HTMLDivElement>(null);

  // Handler functions — defined BEFORE useTerminalAgent which references them
  const handleExecuteCommand = useCallback(async (command: string): Promise<string> => {
    if (!terminalContext?.executeCommand) throw new Error('Terminal not ready');
    return terminalContext.executeCommand(command);
  }, [terminalContext]);

  const handleSendInput = useCallback((input: string): void => {
    if (!terminalContext?.terminalRef?.current) return;
    terminalContext.terminalRef.current.injectCommand(input);
  }, [terminalContext]);

  const handleCancelCommand = useCallback((): void => {
    if (!terminalContext?.terminalRef?.current) return;
    terminalContext.terminalRef.current.injectCommand('\x03');
  }, [terminalContext]);

  const targetAgentAssets = useMemo(() => {
    if (mode === 'agent') {
      return selectedAgentAssets;
    }
    return activeAsset ? [activeAsset] : [];
  }, [activeAsset, selectedAgentAssets, mode]);

  // Keep useTerminalAgent for both modes
  const {
    messages, input: agentInput, handleInputChange, handleSubmit,
    isLoading, isDetectingInteraction,
    sendMessage: agentSendMessage,
    currentInteraction,
    submitInteraction, dismissInteraction, suppressInteraction,
    cancelCommand, isCommandRunning,
    executePendingCommand, rejectPendingCommand,
    hydrateMessages,
  } = useTerminalAgent({
    taskId: sessionId,
    terminalSessionId: terminalContext?.activeSessionId,
    mode,
    modelName: selectedModel,
    assetId: mode === 'agent' ? undefined : activeAsset?.id,
    assetIp: mode === 'agent' ? undefined : activeAsset?.ip,
    selectedAssets: targetAgentAssets.map(a => ({ id: a.id, ip: a.ip ?? a.hostname ?? '', name: a.name })),
    onExecuteCommand: handleExecuteCommand,
    onSendInput: handleSendInput,
    onCancelCommand: handleCancelCommand,
  });

  // Auto-inject incident context when coming from incident detail page
  const contextInjectedRef = useRef<string | null>(null);  // track by incident_id
  useEffect(() => {
    if (!injectedContext) return;

    // If we've already injected for this incident, skip
    if (contextInjectedRef.current === injectedContext.incident_id) return;

    // Wait a short tick for the agent to initialize
    const timer = setTimeout(() => {
      const prompt = renderContextPrompt(injectedContext);
      void agentSendMessage({ text: prompt });
      contextInjectedRef.current = injectedContext.incident_id;
    }, 500);
    return () => clearTimeout(timer);
  }, [injectedContext, agentSendMessage]);

  useEffect(() => {
    if (messages.length === 0) return;
    const firstUser = messages.find((m) => getMessageRole(m) === 'user');
    const title = firstUser ? getMessageText(firstUser).slice(0, 28) || '新会话' : sessionTitle;
    setSessionTitle(title);
    ChatHistoryManager.saveSession({
      id: sessionId,
      title,
      modelName: selectedModel,
      mode,
      assetId: activeAsset?.id,
      assetIp: activeAsset?.ip,
      messages: messages.map((m) => ({
        id: m.id ?? `${Date.now()}-${Math.random()}`,
        role: getMessageRole(m),
        content: getMessageText(m),
        parts: m.parts,
        toolInvocations: getToolInvocations(m),
        timestamp: new Date().toISOString(),
      })),
      createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString(),
    });
  }, [activeAsset?.id, activeAsset?.ip, messages, mode, selectedModel, sessionId, sessionTitle]);

  const restoreSession = useCallback((saved: ChatSession) => {
    setSessionId(saved.id);
    setSessionTitle(saved.title ?? '未命名会话');
    setMode(saved.mode ?? 'cmd');
    hydrateMessages((saved.messages ?? []).map((m) => ({
      id: m.id,
      role: m.role,
      content: m.content,
      parts: Array.isArray(m.parts) ? m.parts.filter(isTerminalMessagePart) : [],
    })));
    setShowHistory(false);
  }, [hydrateMessages]);

  // Assets fetching & models
  const fetchAssets = useCallback(async () => {
    setIsRefreshingAssets(true);
    try {
      const res = await fetch('/api/v1/assets/local');
      if (res.ok) {
        const data = await res.json();
        setAssets(Array.isArray(data) ? data : []);
      }
    } catch (e) {
      console.error('Failed to fetch assets', e);
    } finally {
      setIsRefreshingAssets(false);
    }
  }, []);

  useEffect(() => {
    void fetchAssets();
  }, [fetchAssets]);

  useEffect(() => {
    if (showContextMenu) {
      void fetchAssets();
    }
  }, [showContextMenu, fetchAssets]);

  useEffect(() => {
    if (models.length > 0 && !models.find((m) => m.name === selectedModel)) {
        setSelectedModel(models[0]?.name ?? 'gpt-4o');
    }
  }, [models]);

  const filteredAssets = assets.filter(a =>
    !contextMenuSearch ||
    (a.ip ?? a.hostname ?? '').toLowerCase().includes(contextMenuSearch.toLowerCase()) ||
    (a.name ?? '').toLowerCase().includes(contextMenuSearch.toLowerCase())
  );

  const toggleAssetSelection = (asset: TerminalAsset) => {
    setSelectedAgentAssets(prev => {
      const exists = prev.find(a => a.id === asset.id);
      if (exists) {
        return prev.filter(a => a.id !== asset.id);
      } else {
        // Remove trailing '@' from input text if it's there
        setInput(prevInput => {
          const trimmed = prevInput.trim();
          if (trimmed.endsWith('@')) {
            const lastIdx = prevInput.lastIndexOf('@');
            return prevInput.substring(0, lastIdx) + prevInput.substring(lastIdx + 1);
          }
          return prevInput;
        });
        return [...prev, asset];
      }
    });
  };

  const removeSelectedAsset = (assetId: string) => {
    setSelectedAgentAssets(prev => prev.filter(a => a.id !== assetId));
  };

  const handleTextareaChange = useCallback((e: React.ChangeEvent<HTMLTextAreaElement>) => {
    const value = e.target.value;
    setInput(value);

    // Check if the user typed '@'
    const cursorPosition = e.target.selectionStart || 0;
    const textBeforeCursor = value.slice(0, cursorPosition);
    
    if (/(?:^|\s)@$/.test(textBeforeCursor)) {
      setShowContextMenu(true);
      setContextMenuSearch('');
    }
  }, []);

  const handleSlashSubmit = useCallback((e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const text = (input || '').trim();
    if (!text || isLoading) return;

    if (mode === 'cmd' && !terminalContext?.activeSessionId) {
      toast.error('手动模式下需要左侧有活跃的终端会话。请先在左侧打开并连接一个终端标签页。');
      return;
    }

    if (mode === 'agent' && selectedAgentAssets.length === 0) {
      toast.error('自动模式下请先选择目标主机。您可以输入 @ 或点击输入框上方的 @ 按钮来选择主机。');
      return;
    }

    void agentSendMessage({ text: text });
    setInput('');
  }, [input, isLoading, mode, selectedAgentAssets, terminalContext, agentSendMessage, setInput]);

  const handleNewSession = useCallback(() => {
    if (isLoading || isCommandRunning) {
      toast.warning('当前会话仍在执行中，请等待完成或停止后再新建会话。');
      return;
    }

    setSessionId(ChatHistoryManager.generateId());
    setSessionTitle('新会话');
    hydrateMessages([]);
    setMessageFeedback({});
    setInput('');
    setShowHistory(false);
    setEditingSessionId(null);
    setEditingSessionTitle('');
    setShowContextMenu(false);
    setContextMenuSearch('');
    dismissInteraction();
  }, [dismissInteraction, hydrateMessages, isCommandRunning, isLoading]);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isLoading, isDetectingInteraction]);

  // Keyboard shortcuts: Cmd+/ to toggle mode, Escape to dismiss interaction
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === '/') {
        e.preventDefault();
        setMode(m => m === 'agent' ? 'cmd' : 'agent');
      }
      if (e.key === 'Escape') {
        if (showContextMenu) {
          setShowContextMenu(false);
        } else if (currentInteraction) {
          dismissInteraction();
        }
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [currentInteraction, dismissInteraction, showContextMenu]);

  return (
    <div className="w-full h-full flex flex-col bg-white relative z-10 text-zinc-800 min-h-0">
      {/* Header */}
      <div className="flex items-center justify-between h-12 px-4 shrink-0 bg-white/80 backdrop-blur-md z-10 border-b border-zinc-100">
        <div className="flex items-center gap-2">
          <Button variant="ghost" size="icon" className="h-8 w-8 text-zinc-400 hover:text-zinc-700" onClick={() => setShowHistory(!showHistory)} title="历史会话">
            <History className="w-4 h-4" />
          </Button>
          <span className="text-[13px] font-medium text-zinc-600">{sessionTitle}</span>
          {/* Mode Indicator */}
          <span className={`text-[10px] font-medium px-2 py-0.5 rounded-full ${
            mode === 'cmd' 
              ? 'bg-zinc-100 text-zinc-600' 
              : 'bg-blue-50 text-blue-600'
          }`}>
            {mode === 'cmd' ? '手动模式' : '自动模式'}
          </span>
        </div>
        <div className="flex items-center gap-1">
          {/* Save as Skill — only visible when session has content */}
          {messages.length > 1 && (() => {
            const extracted = extractTerminalSession(messages);
            return extracted.diagnosisText ? (
              <SaveAsSkillDialog
                sessionTitle={sessionTitle}
                diagnosisText={extracted.diagnosisText}
                diagnosisSteps={extracted.diagnosisSteps}
                toolCallsSummary={extracted.toolCallsSummary}
              />
            ) : null;
          })()}
          <Button variant="ghost" size="icon" className="h-8 w-8 text-zinc-400 hover:text-zinc-700" onClick={() => setShowSecuritySettings(true)} title="安全设置">
            <Settings className="w-4 h-4" />
          </Button>
          <Button variant="ghost" size="icon" className="h-8 w-8 text-zinc-400 hover:text-zinc-700" onClick={handleNewSession} title="新建会话">
            <Plus className="w-4 h-4" />
          </Button>
        </div>
      </div>

      {/* History Drawer */}
      {showHistory && (
        <div className="absolute top-12 left-4 w-64 bg-white border border-zinc-200 rounded-xl shadow-xl z-20 max-h-80 overflow-y-auto">
          <div className="px-3 py-2 border-b border-zinc-100 text-xs font-semibold text-zinc-500">聊天历史</div>
          {ChatHistoryManager.getSessionsPage(1).map((s) => (
            <div key={s.id} className="group flex items-center justify-between gap-1 px-2 hover:bg-zinc-50">
              {editingSessionId === s.id ? (
                <input
                  type="text"
                  value={editingSessionTitle}
                  onChange={(e) => setEditingSessionTitle(e.target.value)}
                  onBlur={() => {
                    if (editingSessionTitle.trim()) {
                      const sessionToUpdate = ChatHistoryManager.loadSession(s.id);
                      if (sessionToUpdate) {
                        sessionToUpdate.title = editingSessionTitle.trim();
                        ChatHistoryManager.saveSession(sessionToUpdate);
                      }
                    }
                    setEditingSessionId(null);
                  }}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') {
                      if (editingSessionTitle.trim()) {
                        const sessionToUpdate = ChatHistoryManager.loadSession(s.id);
                        if (sessionToUpdate) {
                          sessionToUpdate.title = editingSessionTitle.trim();
                          ChatHistoryManager.saveSession(sessionToUpdate);
                        }
                      }
                      setEditingSessionId(null);
                    } else if (e.key === 'Escape') {
                      setEditingSessionId(null);
                    }
                  }}
                  className="min-w-0 flex-1 text-xs border border-zinc-200 px-1 py-1 rounded focus:outline-none"
                  autoFocus
                />
              ) : (
                <button onClick={() => restoreSession(s)} className="min-w-0 flex-1 text-left px-1 py-2 text-xs text-zinc-600">
                  <div className="font-medium truncate">{s.title ?? '未命名会话'}</div>
                  <div className="text-zinc-400 text-[10px] mt-0.5">{s.mode === 'agent' ? '自动模式' : '手动模式'} · {new Date(s.updatedAt).toLocaleDateString()}</div>
                </button>
              )}
              {editingSessionId !== s.id && (
                <div className="flex items-center gap-0.5 opacity-0 group-hover:opacity-100 shrink-0">
                  <button
                    type="button"
                    className="p-1 rounded text-zinc-400 hover:text-zinc-600 hover:bg-zinc-100"
                    onClick={(e) => {
                      e.stopPropagation();
                      setEditingSessionId(s.id);
                      setEditingSessionTitle(s.title ?? '未命名会话');
                    }}
                    title="重命名"
                  >
                    <Pencil className="w-3 h-3" />
                  </button>
                  <button
                    type="button"
                    className="p-1 rounded text-zinc-400 hover:text-red-500 hover:bg-red-50"
                    onClick={(e) => {
                      e.stopPropagation();
                      if (confirm('确定要删除此会话历史吗？')) {
                        ChatHistoryManager.deleteSession(s.id);
                        setShowHistory(false);
                        setTimeout(() => setShowHistory(true), 0);
                      }
                    }}
                    title="删除历史"
                  >
                    <X className="w-3 h-3" />
                  </button>
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {/* Chat Content */}
      <div className="flex-1 overflow-y-auto px-4 sm:px-6 md:px-8 pt-4 scroll-smooth">
        {messages.length === 0 ? (
          <div className="h-full flex flex-col items-center justify-center text-zinc-400">
            <div className="w-12 h-12 rounded-2xl bg-gradient-to-tr from-blue-500 to-indigo-500 flex items-center justify-center mb-4 shadow-sm shadow-blue-500/20 text-white">
              <Sparkles className="w-6 h-6" />
            </div>
            <p className="text-sm font-medium text-zinc-700 mb-1">PrismOS Assistant</p>
            <p className="text-xs text-zinc-500 text-center max-w-[240px]">
              {mode === 'cmd' 
                ? '输入你的需求，系统会生成命令，由你确认后在终端中执行。'
                : '系统会在后台自主分析并执行安全命令，危险操作将要求你确认。'}
            </p>
            <div className="mt-4 grid gap-2 w-full max-w-[320px]">
              {['检查磁盘空间 and 使用率', '分析 Nginx 错误日志', '查看当前系统负载与服务状态'].map((example) => (
                <button
                  key={example}
                  type="button"
                  onClick={() => setInput(example)}
                  className="rounded-lg border border-zinc-200 bg-white px-3 py-2 text-left text-xs text-zinc-600 shadow-sm hover:border-zinc-300 hover:bg-zinc-50"
                >
                  {example}
                </button>
              ))}
            </div>
          </div>
        ) : (
          <div className="max-w-4xl mx-auto flex flex-col gap-6">
            {messages.map((m) => {
              let textContent = getMessageText(m);
              const reasoningText = getReasoningText(m);
              const toolInvocations = getToolInvocations(m);

              // Fallback: If model puts text in the tool's reason arg
              if (!textContent && toolInvocations.length > 0) {
                const firstCmd = toolInvocations.find(t => t.toolName === 'execute_command');
                if (firstCmd?.args?.reason) {
                  textContent = firstCmd.args.reason;
                }
              }

              const isEmpty = !textContent && !reasoningText && toolInvocations.length === 0 && (!m.parts || m.parts.filter((p) => p.type === 'step').length === 0) && (!m.tool_calls || m.tool_calls.length === 0);
              if (isEmpty) return null;

              return (
                <div key={m.id} className={`flex gap-3 w-full ${m.role === 'user' || m.type === 'human' ? 'justify-end' : ''}`}>
                  
                  {/* AI Avatar */}
                  {m.role === 'assistant' || m.type === 'ai' && (
                    <div className="w-7 h-7 rounded-lg bg-blue-50 border border-blue-100 flex items-center justify-center shrink-0 mt-0.5">
                      <Sparkles className="w-4 h-4 text-blue-600" />
                    </div>
                  )}

                  <div className={`flex flex-col gap-2 max-w-[85%] ${m.role === 'user' || m.type === 'human' ? 'items-end' : ''}`}>
                    {/* User Bubble */}
                    {m.role === 'user' && textContent && !textContent.startsWith('[SYSTEM_INTERNAL]') && (
                      <div className="bg-zinc-800 text-white px-4 py-2.5 rounded-2xl rounded-tr-sm text-[13px] whitespace-pre-wrap shadow-sm">
                        {textContent.replace(/\[SYSTEM_INTERNAL\]\s*/, '')}
                      </div>
                    )}

                    {/* AI Content */}
                    {m.role === 'assistant' && (
                      <div className="flex flex-col gap-3 w-full">
                        
                        {/* Thinking Process */}
                        {reasoningText && (
                          <details className="group text-[12px] text-zinc-500">
                            <summary className="flex items-center gap-1.5 cursor-pointer hover:text-zinc-700 select-none list-none [&::-webkit-details-marker]:hidden font-medium">
                              <ChevronDown className="w-3.5 h-3.5 transition-transform group-open:-rotate-180" />
                              执行思路
                            </summary>
                            <div className="mt-2 pl-4 border-l-2 border-zinc-200 py-1 whitespace-pre-wrap text-zinc-500">
                              {reasoningText}
                            </div>
                          </details>
                        )}

                        {/* Steps (Execution Plan) */}
                        {(m.parts ?? []).filter((p) => p.type === 'step').length > 0 && (
                          <div className="relative pl-6 my-3 border-l border-zinc-200 space-y-4">
                            {(() => {
                              const stepParts = m.parts?.filter((p) => p.type === 'step') ?? [];
                              return stepParts.map((step, idx: number) => {
                                const isCompleted = step.state === 'completed';
                                return (
                                  <div key={idx} className="relative flex items-center gap-3 text-[13px] leading-none">
                                    {/* Icon Anchor */}
                                    <div className="absolute -left-[32px] flex items-center justify-center bg-white rounded-full p-0.5 z-10 w-5 h-5">
                                      {isCompleted ? (
                                        <div className="w-4 h-4 rounded-full bg-emerald-50 border border-emerald-200 flex items-center justify-center shrink-0">
                                          <Check className="w-2.5 h-2.5 text-emerald-600" />
                                        </div>
                                      ) : (
                                        <div className="w-4 h-4 rounded-full bg-blue-50 border border-blue-200 flex items-center justify-center shrink-0">
                                          <Loader2 className="w-2.5 h-2.5 text-blue-500 animate-spin" />
                                        </div>
                                      )}
                                    </div>
                                    <span className={isCompleted ? 'text-zinc-400 line-through' : 'text-zinc-800 font-medium'}>
                                      {step.stepName}
                                    </span>
                                  </div>
                                );
                              });
                            })()}
                          </div>
                        )}

                        {textContent && (
                          <div className="markdown-body text-[14px] leading-relaxed text-zinc-800 whitespace-pre-wrap mt-2">
                            <MarkdownContent content={textContent} isLoading={false} rehypePlugins={null} />
                          </div>
                        )}

                        {/* Commands / Tools */}
                        {(() => {
                          const toolNameMap: Record<string, string> = {
                            'read_file': '读取文件',
                            'write_file': '写入文件',
                            'grep_search': '文本检索',
                            'web_fetch': '网页获取',
                            'execute_command': '执行命令',
                            'ask_followup_question': '追问问题',
                          };
                          const toolStateMap: Record<string, string> = {
                            'input-streaming': '正在生成输入',
                            'input-available': '等待确认执行',
                            'output-available': '执行完成',
                            'output-error': '执行失败',
                            'auto-executing': '正在自动执行',
                          };

                          return toolInvocations.map((tool) => {
                            const toolCallId = tool.toolCallId ?? '';
                            const toolName = tool.toolName ?? 'unknown';
                            const command: string = typeof tool.args.command === 'string' ? tool.args.command : '';
                            const outputText: string = typeof tool.output === 'string'
                              ? tool.output
                              : JSON.stringify(tool.output, null, 2) ?? '';
                            const isCall = tool.state === 'input-available' || tool.state === 'input-streaming';
                            const isAutoExecuting = tool.state === 'auto-executing';
                            const isDone = tool.state === 'output-available';
                            const isError = tool.state === 'output-error';
                            
                            if (toolName === 'execute_command') {
                              // In agent mode, show target host IP from approval data
                              // Fallback: use selectedAgentAssets (agent mode) or activeAsset (cmd mode)
                              const targetIp = tool.approval?.targetAssets?.[0]?.ip
                                ?? (mode === 'agent' ? selectedAgentAssets[0]?.ip : undefined)
                                ?? activeAsset?.ip;
                              return (
                                <div key={toolCallId} className="w-full flex flex-col rounded-xl border border-zinc-200/80 bg-[#0d1117] shadow-sm my-1">
                                  {/* Command Header */}
                                  <div className="flex items-center justify-between px-3 py-2 border-b border-white/10 bg-[#161b22] rounded-t-xl">
                                    <div className="flex items-center gap-2 text-[11px] font-medium text-zinc-400">
                                      <TerminalIcon className="w-3.5 h-3.5 text-zinc-500" />
                                      终端命令
                                      {targetIp && (
                                        <span className="text-[10px] text-blue-400 bg-blue-500/10 px-1.5 py-0.5 rounded font-mono">
                                          {targetIp}
                                        </span>
                                      )}
                                    </div>
                                    
                                    {/* Status & Actions */}
                                    <div className="flex items-center gap-2">
                                      {isError ? (
                                        <span className="text-[10px] text-red-400 flex items-center gap-1">
                                          <AlertTriangle className="w-3 h-3"/> 执行失败
                                        </span>
                                      ) : isDone ? (
                                        <span className="text-[10px] text-emerald-400 flex items-center gap-1">
                                          <Check className="w-3 h-3"/> 已执行
                                        </span>
                                      ) : isAutoExecuting || isCommandRunning ? (
                                        <span className="text-[10px] text-blue-400 flex items-center gap-1">
                                          <Loader2 className="w-3 h-3 animate-spin"/> {isAutoExecuting ? '自动执行中' : '执行中'}
                                        </span>
                                      ) : isCall ? (
                                        <div className="flex items-center gap-1">
                                          <Button
                                            variant="ghost"
                                            size="sm"
                                            onClick={() => rejectPendingCommand(toolCallId, toolName)}
                                            className="h-6 px-2 text-[10px] text-zinc-400 hover:text-red-400 hover:bg-red-500/10"
                                          >
                                            拒绝
                                          </Button>
                                          <Button
                                            size="sm"
                                            onClick={() => executePendingCommand(toolCallId, toolName, command)}
                                            className="h-6 px-3 text-[10px] bg-blue-600 hover:bg-blue-500 text-white"
                                          >
                                            执行 <CornerDownLeft className="w-3 h-3 ml-1"/>
                                          </Button>
                                        </div>
                                      ) : (
                                        <span className="text-[10px] text-zinc-500">等待中</span>
                                      )}
                                    </div>
                                  </div>

                                  {isCall && tool.approval && (
                                    <div className="mx-3 mt-3 rounded-lg border border-amber-400/30 bg-amber-400/10 p-3 text-[12px] text-amber-100">
                                      <div className="flex items-center gap-2 font-medium text-amber-200">
                                        <AlertTriangle className="w-3.5 h-3.5" />
                                        需要确认 · {riskLabel(tool.approval.riskLevel)}
                                      </div>
                                      <div className="mt-2 text-amber-100/90">
                                        {tool.approval.reason ?? '该操作需要你确认后才能继续执行。'}
                                      </div>
                                      <div className="mt-2 flex flex-wrap gap-1.5">
                                        {(tool.approval.targetAssets ?? []).map((asset) => (
                                          <span key={asset.id ?? asset.name} className="rounded bg-black/20 px-2 py-0.5 text-[10px] text-amber-50">
                                            {asset.ip ?? asset.name ?? asset.id}
                                          </span>
                                        ))}
                                        {tool.approval.isStateChanging && (
                                          <span className="rounded bg-red-500/20 px-2 py-0.5 text-[10px] text-red-100">
                                            会修改远程状态
                                          </span>
                                        )}
                                      </div>
                                    </div>
                                  )}

                                  {/* Command Text */}
                                  {command ? (
                                    <div className="p-3 text-[13px] font-mono text-zinc-100 whitespace-pre-wrap break-all leading-relaxed">
                                      <span className="text-zinc-500 select-none mr-3">$</span>
                                      {command}
                                    </div>
                                  ) : outputText ? (
                                    /* Tool result (from tool message) — show output directly */
                                    <div className="p-3 text-[13px] font-mono whitespace-pre-wrap break-all leading-relaxed max-h-96 overflow-y-auto">
                                      {outputText}
                                    </div>
                                  ) : (
                                    <div className="p-3 text-[13px] font-mono text-zinc-500 whitespace-pre-wrap">
                                      (等待命令...)
                                    </div>
                                  )}
                                  
                                  {/* Command Output */}
                                  {(isDone || isError) && outputText.length > 0 && (
                                    <div className="border-t border-white/10 bg-[#0a0c10]">
                                      <div className="px-3 pt-3 text-[11px] text-zinc-300">
                                        <span className="text-zinc-500">结果摘要：</span>{summarizeOutput(outputText)}
                                      </div>
                                      <details className="group" open={isError}>
                                        <summary className="px-3 py-2 text-[10px] text-zinc-500 hover:text-zinc-300 font-mono cursor-pointer select-none list-none [&::-webkit-details-marker]:hidden flex items-center">
                                          <ChevronDown className="w-3 h-3 mr-1.5 transition-transform group-open:-rotate-180" />
                                          {isError ? '错误详情' : '查看原始输出'}
                                        </summary>
                                        <div className={`px-3 pb-3 text-[11px] font-mono whitespace-pre-wrap break-all max-h-64 overflow-y-auto ${
                                          isError ? 'text-red-400' : 'text-zinc-400'
                                        }`}>
                                          {outputText}
                                        </div>
                                      </details>
                                    </div>
                                  )}
                                </div>
                              );
                            }

                            // Other tools (read_file, write_file, grep_search, web_fetch, etc.)
                            if (toolName === 'ask_followup_question' && isCall) {
                              return (
                                <div key={toolCallId} className="w-full mt-1 p-3 rounded-xl border border-blue-200 bg-blue-50/50">
                                  <p className="text-[13px] font-medium text-blue-800 mb-2">{tool.args.question ?? '需要补充信息'}</p>
                                  {tool.args.options && tool.args.options.length > 0 && (
                                    <div className="flex flex-wrap gap-2">
                                      {tool.args.options.map((opt: string, i: number) => (
                                        <button
                                          key={i}
                                          className="px-3 py-1.5 text-[12px] bg-white border border-blue-200 rounded-lg hover:bg-blue-100 text-blue-700 shadow-sm transition-colors"
                                          onClick={() => handleSendInput(opt)}
                                        >
                                          {opt}
                                        </button>
                                      ))}
                                    </div>
                                  )}
                                </div>
                              );
                            }

                            // Generic tool (read_file, write_file, grep_search, web_fetch)
                            const isRemoteTool = ['read_file', 'write_file', 'grep_search', 'web_fetch'].includes(toolName);
                            
                            if (isRemoteTool) {
                              return (
                                <div key={toolCallId} className="w-full rounded-xl overflow-hidden border border-zinc-200/80 bg-zinc-50 shadow-sm my-1">
                                  <div className="flex items-center justify-between px-3 py-2 border-b border-zinc-200 bg-white">
                                    <div className="flex items-center gap-2 text-[11px] font-medium text-zinc-600">
                                      <Sparkles className="w-3.5 h-3.5 text-blue-500" />
                                      {toolNameMap[toolName] ?? toolName}
                                    </div>
                                    <div className="flex items-center gap-2">
                                      {isError ? (
                                        <span className="text-[10px] text-red-400">失败</span>
                                      ) : isDone ? (
                                        <span className="text-[10px] text-emerald-500 flex items-center gap-1"><Check className="w-3 h-3"/> 完成</span>
                                      ) : isAutoExecuting ? (
                                        <span className="text-[10px] text-blue-400 flex items-center gap-1"><Loader2 className="w-3 h-3 animate-spin"/> 执行中</span>
                                      ) : isCall ? (
                                        <div className="flex items-center gap-1">
                                          <Button variant="ghost" size="sm" onClick={() => rejectPendingCommand(toolCallId, toolName)} className="h-6 px-2 text-[10px] text-zinc-400 hover:text-red-400">拒绝</Button>
                                          <Button size="sm" onClick={() => executePendingCommand(toolCallId, toolName, '')} className="h-6 px-3 text-[10px] bg-blue-600 hover:bg-blue-500 text-white">执行</Button>
                                        </div>
                                      ) : (
                                        <span className="text-[10px] text-zinc-400">...</span>
                                      )}
                                    </div>
                                  </div>
                                  {outputText && (
                                    <div className="p-3 text-[12px] font-mono text-zinc-600 whitespace-pre-wrap max-h-48 overflow-y-auto">
                                      {outputText}
                                    </div>
                                  )}
                                </div>
                              );
                            }

                            return (
                                <div key={toolCallId} className="w-full p-3 rounded-xl border border-zinc-200 bg-zinc-50 text-[11px] font-mono text-zinc-600">
                                <span className="font-semibold text-zinc-800">{toolNameMap[toolName] ?? toolName}</span> {toolStateMap[tool.state ?? ''] ?? tool.state}
                              </div>
                            );
                          });
                        })()}

                      </div>
                    )}
                  </div>
                </div>
              );
            })}

            {/* Loading indicator */}
            {isLoading && !messages.find((m) => (m.role === 'assistant' || m.type === 'ai') && !getMessageText(m)) && (
              <div className="flex items-center gap-2 text-zinc-400 text-xs mt-2">
                <Loader2 className="w-4 h-4 animate-spin text-blue-500" />
                <span>Agent 正在分析...</span>
              </div>
            )}

            {/* Interaction prompt (e.g., follow-up question from agent) */}
            {currentInteraction && (
              <CommandInteractionInput
                state={{
                  commandId: currentInteraction.commandId,
                  interactionType: currentInteraction.interactionType as CommandInteractionType,
                  promptHint: currentInteraction.promptHint ?? '',
                  options: currentInteraction.options ?? [],
                  optionValues: currentInteraction.optionValues ?? [],
                  confirmValues: currentInteraction.confirmValues
                    ? {
                        yes: currentInteraction.confirmValues.yes,
                        no: currentInteraction.confirmValues.no,
                        default: currentInteraction.confirmValues.default !== undefined,
                      }
                    : undefined,
                  exitKey: currentInteraction.exitKey,
                  exitAppendNewline: currentInteraction.exitAppendNewline,
                  isSuppressed: false,
                  tuiDetected: false,
                  tuiMessage: '',
                  errorMessage: '',
                  isSubmitting: false,
                }}
                onSubmit={({ commandId, input, appendNewline, interactionType }) => {
                  submitInteraction({ commandId, input, appendNewline, interactionType });
                }}
                onCancel={() => cancelCommand()}
                onDismiss={() => dismissInteraction()}
                onSuppress={() => suppressInteraction()}
                onUnsuppress={ignoreInteractionCommand}
                onFocusTerminal={ignoreTerminalFocus}
                onClearError={ignoreInteractionCommand}
              />
            )}
          </div>
        )}
        <div ref={chatEndRef} />
      </div>

      {/* Input Bar — part of normal flex flow, messages scroll above it */}
      <div className="shrink-0 w-full max-w-3xl mx-auto px-4 pb-6 z-20">
        <div className="bg-white rounded-2xl shadow-[0_4px_20px_rgb(0,0,0,0.06)] border border-zinc-200 overflow-visible relative flex flex-col focus-within:shadow-[0_4px_24px_rgb(0,0,0,0.10)] focus-within:border-zinc-300 transition-all">
          
          <form onSubmit={handleSlashSubmit} className="flex flex-col pt-3">
            {/* Context Mentions */}
            <div className="px-4 pb-1 flex items-center gap-2 overflow-visible">
              {mode === 'cmd' ? (
                <div className="inline-flex items-center gap-1.5 bg-zinc-100/80 text-zinc-600 text-[11px] px-2.5 py-1 rounded-lg font-medium border border-zinc-200/50">
                  <TerminalIcon className="w-3.5 h-3.5" />
                  {activeAsset ? activeAsset.ip : 'localhost'}
                </div>
              ) : (
                <div className="flex items-center gap-2 w-full overflow-visible">
                  {/* @ picker button — always visible in Agent mode, pinned on the left */}
                  <div className="relative shrink-0">
                    <button
                      type="button"
                      onClick={() => {
                        setShowContextMenu(!showContextMenu);
                        setContextMenuSearch('');
                      }}
                      className="inline-flex items-center text-zinc-400 hover:text-zinc-700 text-[13px] px-2 py-0.5 rounded font-semibold transition-colors hover:bg-zinc-50 border border-zinc-100 hover:border-zinc-200 shadow-sm shrink-0"
                      title="选择目标主机"
                    >
                      <span className="text-blue-500 mr-0.5 font-bold">@</span> 主机
                    </button>

                    {/* Dropdown — Premium design with modern colors, shadows, and spacing */}
                    {showContextMenu && (
                      <>
                        <div className="fixed inset-0 z-40 bg-transparent" onClick={() => setShowContextMenu(false)} />
                        <div className="absolute left-0 bottom-full mb-2 w-80 bg-white border border-zinc-200/80 rounded-2xl shadow-[0_8px_32px_rgba(0,0,0,0.08)] z-50 flex flex-col overflow-hidden transition-all duration-200 animate-in fade-in slide-in-from-bottom-2" style={{ maxHeight: '360px' }}>
                          
                          {/* Header: Title, Search, and Manual Refresh */}
                          <div className="px-3 py-2.5 border-b border-zinc-100 bg-zinc-50/50 flex items-center justify-between gap-2 shrink-0">
                            <div className="relative flex-1">
                              <Input
                                type="text"
                                placeholder="搜索主机名称或 IP..."
                                value={contextMenuSearch}
                                onChange={(e) => setContextMenuSearch(e.target.value)}
                                className="h-8 pl-2 pr-7 text-[12px] bg-white border-zinc-200 focus-visible:ring-1 focus-visible:ring-blue-500 rounded-lg shadow-inner"
                                autoFocus
                                onKeyDown={(e) => e.stopPropagation()}
                              />
                              {contextMenuSearch && (
                                <button
                                  type="button"
                                  onClick={() => setContextMenuSearch('')}
                                  className="absolute right-2.5 top-1/2 -translate-y-1/2 text-zinc-400 hover:text-zinc-600"
                                >
                                  <X className="w-3.5 h-3.5" />
                                </button>
                              )}
                            </div>
                            
                            {/* Manual Refresh Button with spin animation */}
                            <button
                              type="button"
                              onClick={fetchAssets}
                              disabled={isRefreshingAssets}
                              className={`p-1.5 rounded-lg border border-zinc-200 hover:border-zinc-300 bg-white hover:bg-zinc-50 text-zinc-500 hover:text-zinc-700 transition-colors shadow-sm ${
                                isRefreshingAssets ? 'opacity-70 cursor-not-allowed' : ''
                              }`}
                              title="刷新主机列表"
                            >
                              <RotateCcw className={`w-3.5 h-3.5 ${isRefreshingAssets ? 'animate-spin' : ''}`} />
                            </button>
                          </div>

                          {/* Host List */}
                          <div className="flex-1 overflow-y-auto min-h-0 py-1 divide-y divide-zinc-50/30">
                            {filteredAssets.length === 0 ? (
                              <div className="px-3 py-8 text-[12px] text-zinc-400 text-center flex flex-col items-center justify-center gap-2">
                                <Monitor className="w-8 h-8 text-zinc-200 stroke-[1.5]" />
                                <span>{assets.length === 0 ? '暂无已配置的主机' : '未找到匹配的主机'}</span>
                              </div>
                            ) : (
                              filteredAssets.map(asset => {
                                const isSelected = selectedAgentAssets.some(a => a.id === asset.id);
                                return (
                                  <button
                                    key={asset.id}
                                    type="button"
                                    onClick={() => toggleAssetSelection(asset)}
                                    className="w-full flex items-center gap-3 px-3.5 py-2.5 hover:bg-zinc-50/60 text-left transition-colors group relative"
                                  >
                                    {/* Custom Checkbox */}
                                    <div className={`w-4.5 h-4.5 rounded-md border flex items-center justify-center shrink-0 transition-all ${
                                      isSelected
                                        ? 'bg-blue-600 border-blue-600 shadow-sm shadow-blue-100'
                                        : 'border-zinc-300 group-hover:border-zinc-400 bg-white'
                                    }`}>
                                      {isSelected && <Check className="w-3 h-3 text-white" strokeWidth={3.5} />}
                                    </div>

                                    {/* Host Icon */}
                                    <div className={`p-1.5 rounded-lg shrink-0 transition-colors ${
                                      isSelected ? 'bg-blue-50 text-blue-600' : 'bg-zinc-100 text-zinc-500 group-hover:bg-zinc-200/50 group-hover:text-zinc-700'
                                    }`}>
                                      <Monitor className="w-3.5 h-3.5" />
                                    </div>

                                    {/* Host Info */}
                                    <div className="flex-1 min-w-0">
                                      <div className="text-[12.5px] font-medium text-zinc-700 truncate group-hover:text-zinc-900">
                                        {asset.name ?? asset.hostname}
                                      </div>
                                      <div className="text-[10.5px] text-zinc-400 font-mono truncate mt-0.5">
                                        {asset.username ? `${asset.username}@` : ''}{asset.ip}
                                      </div>
                                    </div>
                                  </button>
                                );
                              })
                            )}
                          </div>

                          {/* Footer: Stats, Clear All, Done */}
                          <div className="px-3.5 py-2.5 border-t border-zinc-100 bg-zinc-50/50 flex items-center justify-between shrink-0">
                            <div className="flex items-center gap-2">
                              <span className="text-[11px] font-medium text-zinc-500 bg-zinc-100 px-2 py-0.5 rounded-full">
                                {selectedAgentAssets.length > 0 ? `已选 ${selectedAgentAssets.length} 台` : '未选择目标'}
                              </span>
                              {selectedAgentAssets.length > 0 && (
                                <button
                                  type="button"
                                  onClick={() => setSelectedAgentAssets([])}
                                  className="text-[11px] text-zinc-400 hover:text-red-500 transition-colors"
                                >
                                  清空
                                </button>
                              )}
                            </div>
                            <button
                              type="button"
                              onClick={() => setShowContextMenu(false)}
                              className="text-[11px] font-semibold text-blue-600 hover:text-blue-700 bg-white hover:bg-zinc-100/80 px-3 py-1 rounded-lg border border-zinc-200 shadow-sm transition-all active:scale-[0.98]"
                            >
                              完成
                            </button>
                          </div>
                        </div>
                      </>
                    )}
                  </div>

                  {/* Divider line if there are tags */}
                  {targetAgentAssets.length > 0 && <span className="text-zinc-300 shrink-0 select-none">|</span>}

                  {/* Selected host tags — scrollable list */}
                  <div className="flex-1 flex items-center gap-2 overflow-x-auto scrollbar-none py-0.5">
                    {targetAgentAssets.map(asset => {
                      const isExplicit = selectedAgentAssets.some(a => a.id === asset.id);
                      return (
                        <div
                          key={asset.id}
                          className={`inline-flex items-center gap-1.5 text-[11px] px-2.5 py-1 rounded-lg font-medium border shrink-0 ${
                            isExplicit ? 'bg-blue-50 text-blue-700 border-blue-200' : 'bg-zinc-100/80 text-zinc-600 border-zinc-200/50'
                          }`}
                        >
                          <span className={isExplicit ? 'text-blue-500 font-bold' : 'text-zinc-400 font-bold'}>@</span>
                          {assetLabel(asset)}
                          {isExplicit && (
                            <button
                              type="button"
                              onClick={(e) => {
                                e.stopPropagation();
                                removeSelectedAsset(asset.id);
                              }}
                              className="ml-0.5 p-0.5 hover:bg-blue-100 rounded text-blue-400 hover:text-blue-600"
                            >
                              <X className="w-3.5 h-3.5" />
                            </button>
                          )}
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}
            </div>

            <textarea
              value={input || ''}
              onChange={handleTextareaChange}
              disabled={models.length === 0 || isLoading || (mode === 'cmd' && !terminalContext?.activeSessionId)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault();
                  const form = e.currentTarget.closest('form');
                  if (form) form.requestSubmit();
                }
              }}
              placeholder={
                mode === 'cmd' 
                  ? (terminalContext?.activeSessionId
                    ? "输入你的运维需求，系统将生成命令，经你确认后在终端中执行... (⌘+/)"
                    : "请先在左侧打开并连接一个终端标签页，然后在此输入运维需求...")
                  : "输入你的运维目标，系统将自动进行诊断并在后台执行安全命令..."
              }
              className="w-full bg-transparent border-0 resize-none px-4 py-2 text-[14px] text-zinc-800 placeholder:text-zinc-400 disabled:opacity-50 focus:outline-none focus:ring-0 min-h-[50px] max-h-[200px]"
              rows={input.split('\n').length > 1 ? Math.min(input.split('\n').length, 8) : 1}
            />

            <div className="flex items-center justify-between px-3 py-2">
              <div className="flex items-center gap-2">
                {/* Agent / Command mode toggle */}
                <div className="flex items-center gap-0.5 bg-zinc-100 p-0.5 rounded-lg border border-zinc-200">
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <button
                        type="button"
                        onClick={() => setMode('agent')}
                        className={`px-2.5 py-1 rounded-md text-[10px] font-medium transition-all flex items-center gap-1 ${
                          mode === 'agent' 
                            ? 'bg-white text-blue-600 shadow-sm' 
                            : 'text-zinc-500 hover:text-zinc-700'
                        }`}
                      >
                        <Sparkles className="w-3 h-3"/> 自动模式
                      </button>
                    </TooltipTrigger>
                    <TooltipContent side="top" className="max-w-[260px]">
                      自动模式：系统在后台自主分析并自动执行安全命令，高/中危操作将暂停由您审批确认。
                    </TooltipContent>
                  </Tooltip>
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <button
                        type="button"
                        onClick={() => setMode('cmd')}
                        className={`px-2.5 py-1 rounded-md text-[10px] font-medium transition-all ${
                          mode === 'cmd' 
                            ? 'bg-white text-zinc-800 shadow-sm' 
                            : 'text-zinc-500 hover:text-zinc-700'
                        }`}
                      >
                        手动模式
                      </button>
                    </TooltipTrigger>
                    <TooltipContent side="top" className="max-w-[260px]">
                      手动模式：系统在后台分析并生成建议命令，需您手动确认后方可在终端中执行。
                    </TooltipContent>
                  </Tooltip>
                </div>
                <div className="flex items-center gap-1">
                <DropdownMenu>
                  <DropdownMenuTrigger asChild>
                    <button type="button" className="flex items-center gap-1 text-[11px] font-medium text-zinc-400 hover:text-zinc-600 px-2 py-1 rounded hover:bg-zinc-50">
                      {selectedModel} <ChevronDown className="w-3 h-3" />
                    </button>
                  </DropdownMenuTrigger>
                  <DropdownMenuContent align="start" className="text-[12px]">
                    {models.map((m) => (
                      <DropdownMenuItem key={m.name} onClick={() => setSelectedModel(m.name)}>{m.display_name || m.name}</DropdownMenuItem>
                    ))}
                  </DropdownMenuContent>
                </DropdownMenu>
                </div>
              </div>
              <div className="flex items-center gap-1.5">
                <span className="hidden sm:inline text-[11px] text-zinc-400">
                  {mode === 'agent'
                    ? `目标主机: ${targetAgentAssets.length || 0} 台`
                    : activeAsset ? `目标主机: ${assetLabel(activeAsset)}` : '未连接主机'}
                </span>
                <button type="button" className="text-zinc-400 hover:text-zinc-600 p-1.5 rounded-md hover:bg-zinc-50"><ImageIcon className="w-4 h-4" /></button>
                <Button type="submit" disabled={!input?.trim() || isLoading} size="icon" className="h-8 w-8 rounded-xl bg-zinc-800 hover:bg-zinc-700 text-white shadow-sm ml-1">
                  <ArrowUp className="w-4 h-4" />
                </Button>
              </div>
            </div>
          </form>
        </div>
      </div>
      
      <SecuritySettingsPanel open={showSecuritySettings} onClose={() => setShowSecuritySettings(false)} />
    </div>
  );
}
