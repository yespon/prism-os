import os

new_code = """'use client';

import React, { useState, useEffect, useRef, useCallback } from 'react';
import { useTerminalAgent } from '@/core/terminal-agent/useTerminalAgent';
import { CommandInteractionInput } from '@/core/terminal-agent/command-interaction-input';
import { useTerminalContext } from '@/app/workspace/terminal/context';
import { SecuritySettingsPanel } from '@/core/terminal-agent/security/security-settings-ui';
import { ChatHistoryManager, type ChatMessage } from '@/core/terminal-agent/chat-history';
import {
  Monitor, X, Plus, RotateCcw, MoreHorizontal,
  Mic, Image as ImageIcon, ArrowUp, ChevronDown,
  TerminalSquare, Loader2, ShieldAlert, AlertTriangle,
  ThumbsUp, ThumbsDown, Settings, History, Check, ChevronLeft, Bot,
  Terminal as TerminalIcon, Sparkles, Play, StopCircle, CornerDownLeft
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { useAvailableModels } from '@/core/models/hooks';

function getMessageText(msg: any): string {
  if (!msg?.parts) return msg?.content || '';
  return msg.parts.filter((p: any) => p.type === 'text').map((p: any) => p.text).join('\\n');
}

function getReasoningText(msg: any): string {
  if (!msg?.parts) return '';
  return msg.parts.filter((p: any) => p.type === 'reasoning').map((p: any) => p.text).join('\\n');
}

function getToolInvocations(msg: any): any[] {
  if (!msg) return [];
  if (Array.isArray(msg.parts)) {
    return msg.parts
      .filter((p: any) => p.type?.startsWith('tool-') || p.type === 'dynamic-tool')
      .map((p: any) => {
        const toolName = p.toolName || (p.type && p.type.startsWith('tool-') ? p.type.slice(5) : p.type);
        return {
          toolCallId: p.toolCallId,
          toolName,
          state: p.state,
          input: p.input || {},
          output: p.output,
          errorText: p.errorText,
          get args() { return this.input; },
          get result() { return this.output; },
        };
      });
  }
  return [];
}

export function TerminalAgentUI({ activeAsset }: { activeAsset: any }) {
  const terminalContext = useTerminalContext();
  const { models } = useAvailableModels();
  const [selectedModel, setSelectedModel] = useState<string>('gpt-4o');
  const [showSecuritySettings, setShowSecuritySettings] = useState(false);
  const [showHistory, setShowHistory] = useState(false);
  const [sessionId] = useState(() => ChatHistoryManager.generateId());
  const [sessionTitle, setSessionTitle] = useState('新会话');
  const [messageFeedback, setMessageFeedback] = useState<Record<string, 'up' | 'down'>>({});
  const [mode, setMode] = useState<'cmd' | 'agent'>('cmd');
  const [showContextMenu, setShowContextMenu] = useState(false);
  const [contextMenuSearch, setContextMenuSearch] = useState('');
  const [assets, setAssets] = useState<any[]>([]);
  const [selectedAgentAsset, setSelectedAgentAsset] = useState<any | null>(null);
  const chatEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    fetch('/api/v1/assets/local')
      .then(res => res.json())
      .then(data => setAssets(Array.isArray(data) ? data : []))
      .catch(console.error);
  }, []);

  useEffect(() => {
    if (models.length > 0 && !models.find((m) => m.name === selectedModel)) {
      setSelectedModel(models[0]?.name || 'gpt-4o');
    }
  }, [models]);

  const handleExecuteCommand = async (command: string): Promise<string> => {
    if (!terminalContext?.executeCommand) throw new Error('Terminal not ready');
    return terminalContext.executeCommand(command);
  };

  const handleSendInput = (input: string): void => {
    if (!terminalContext?.terminalRef?.current) return;
    terminalContext.terminalRef.current.injectCommand(input);
  };

  const handleCancelCommand = (): void => {
    if (!terminalContext?.terminalRef?.current) return;
    terminalContext.terminalRef.current.injectCommand('\\x03');
  };

  const {
    messages, input, handleInputChange, handleSubmit,
    isLoading, isDetectingInteraction,
    sendMessage,
    currentInteraction,
    submitInteraction, dismissInteraction, suppressInteraction,
    cancelCommand, isCommandRunning,
    executePendingCommand, rejectPendingCommand,
    pendingDangerousTool, confirmDangerousCommand, rejectDangerousCommand,
  } = useTerminalAgent({
    taskId: sessionId,
    terminalSessionId: terminalContext?.activeSessionId,
    mode,
    modelName: selectedModel,
    assetId: mode === 'agent' && selectedAgentAsset ? selectedAgentAsset.id : activeAsset?.id,
    assetIp: mode === 'agent' && selectedAgentAsset ? selectedAgentAsset.ip : activeAsset?.ip,
    onExecuteCommand: handleExecuteCommand,
    onSendInput: handleSendInput,
    onCancelCommand: handleCancelCommand,
  });

  const handleSlashSubmit = useCallback((e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const text = (input || '').trim();
    if (!text || isLoading) return;

    if (text.startsWith('/summary')) {
      (sendMessage as any)({ text: text + '\\n【system】用户要求总结，请输出结构化 Markdown。' });
      return;
    }
    handleSubmit(e);
  }, [input, isLoading, handleSubmit, sendMessage]);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isLoading, isDetectingInteraction]);

  // Handle Keyboard escape and Cmd+/
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === '/') {
        e.preventDefault();
        setMode(m => m === 'agent' ? 'cmd' : 'agent');
      }
      if (e.key === 'Escape' && currentInteraction) {
        dismissInteraction();
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [currentInteraction, dismissInteraction]);

  return (
    <div className="w-full h-full flex flex-col bg-white relative z-10 text-zinc-800">
      {/* 极简 Header */}
      <div className="flex items-center justify-between h-12 px-4 shrink-0 bg-white/80 backdrop-blur-md z-10">
        <div className="flex items-center gap-2">
          <Button variant="ghost" size="icon" className="h-8 w-8 text-zinc-400 hover:text-zinc-700" onClick={() => setShowHistory(!showHistory)} title="历史会话">
            <History className="w-4 h-4" />
          </Button>
          <span className="text-[13px] font-medium text-zinc-600">{sessionTitle}</span>
        </div>
        <div className="flex items-center gap-1">
          <Button variant="ghost" size="icon" className="h-8 w-8 text-zinc-400 hover:text-zinc-700" onClick={() => setShowSecuritySettings(true)} title="安全设置">
            <Settings className="w-4 h-4" />
          </Button>
          <Button variant="ghost" size="icon" className="h-8 w-8 text-zinc-400 hover:text-zinc-700" onClick={() => window.location.reload()} title="新会话">
            <Plus className="w-4 h-4" />
          </Button>
        </div>
      </div>

      {/* History Drawer */}
      {showHistory && (
        <div className="absolute top-12 left-4 w-64 bg-white border border-zinc-200 rounded-xl shadow-xl z-20 max-h-80 overflow-y-auto">
          <div className="px-3 py-2 border-b border-zinc-100 text-xs font-semibold text-zinc-500">聊天历史</div>
          {ChatHistoryManager.getSessionsPage(1).map((s) => (
            <button key={s.id} className="w-full text-left px-3 py-2 hover:bg-zinc-50 text-xs text-zinc-600">
              <div className="font-medium truncate">{s.title || '未命名会话'}</div>
              <div className="text-zinc-400 text-[10px] mt-0.5">{s.mode} · {new Date(s.updatedAt).toLocaleDateString()}</div>
            </button>
          ))}
        </div>
      )}

      {/* Chat Content */}
      <div className="flex-1 overflow-y-auto px-4 sm:px-6 md:px-8 pt-4 pb-24 scroll-smooth">
        {messages.length === 0 ? (
          <div className="h-full flex flex-col items-center justify-center text-zinc-400">
            <div className="w-12 h-12 rounded-2xl bg-gradient-to-tr from-blue-500 to-indigo-500 flex items-center justify-center mb-4 shadow-sm shadow-blue-500/20 text-white">
              <Sparkles className="w-6 h-6" />
            </div>
            <p className="text-sm font-medium text-zinc-700 mb-1">PrismOS Assistant</p>
            <p className="text-xs text-zinc-500">I can analyze logs, run commands, and debug your servers.</p>
          </div>
        ) : (
          <div className="max-w-4xl mx-auto flex flex-col gap-6">
            {messages.map((m: any) => {
              const textContent = getMessageText(m);
              let reasoningText = getReasoningText(m);
              const toolInvocations = getToolInvocations(m);

              // Fallback reasoning extraction
              if (!reasoningText && !textContent && toolInvocations.length > 0) {
                const firstCmd = toolInvocations.find(t => t.toolName === 'execute_command');
                if (firstCmd?.args?.reason) reasoningText = firstCmd.args.reason;
              }

              return (
                <div key={m.id} className={`flex gap-3 w-full ${m.role === 'user' ? 'justify-end' : ''}`}>
                  
                  {/* AI Avatar */}
                  {m.role === 'assistant' && (
                    <div className="w-7 h-7 rounded-lg bg-blue-50 border border-blue-100 flex items-center justify-center shrink-0 mt-0.5">
                      <Sparkles className="w-4 h-4 text-blue-600" />
                    </div>
                  )}

                  <div className={`flex flex-col gap-2 max-w-[85%] ${m.role === 'user' ? 'items-end' : ''}`}>
                    {/* User Bubble */}
                    {m.role === 'user' && textContent && !textContent.startsWith('[SYSTEM_INTERNAL]') && (
                      <div className="bg-zinc-800 text-white px-4 py-2.5 rounded-2xl rounded-tr-sm text-[13px] whitespace-pre-wrap shadow-sm">
                        {textContent.replace(/\[SYSTEM_INTERNAL\]\\s*/, '')}
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
                              Thought Process
                            </summary>
                            <div className="mt-2 pl-4 border-l-2 border-zinc-200 py-1 whitespace-pre-wrap text-zinc-500">
                              {reasoningText}
                            </div>
                          </details>
                        )}

                        {/* Steps (Execution Plan) */}
                        {m.parts?.filter((p: any) => p.type === 'step').length > 0 && (
                          <div className="flex flex-col gap-2 my-1">
                            {m.parts.filter((p: any) => p.type === 'step').map((step: any, idx: number) => (
                              <div key={idx} className="flex items-start gap-2.5 text-[13px]">
                                {step.state === 'completed' ? (
                                  <div className="w-4 h-4 rounded-full bg-emerald-500/10 flex items-center justify-center shrink-0 mt-0.5">
                                    <Check className="w-3 h-3 text-emerald-600" />
                                  </div>
                                ) : (
                                  <Loader2 className="w-4 h-4 text-blue-500 animate-spin shrink-0 mt-0.5" />
                                )}
                                <span className={step.state === 'completed' ? 'text-zinc-400 line-through' : 'text-zinc-800 font-medium'}>
                                  {step.stepName}
                                </span>
                              </div>
                            ))}
                          </div>
                        )}

                        {/* Normal Text */}
                        {textContent && (
                          <div className="text-[14px] leading-relaxed text-zinc-800 whitespace-pre-wrap">
                            {textContent}
                          </div>
                        )}

                        {/* Commands / Tools */}
                        {toolInvocations.map((tool: any) => {
                          const isCall = tool.state === 'input-available' || tool.state === 'input-streaming';
                          const isDone = tool.state === 'output-available';
                          
                          if (tool.toolName === 'execute_command') {
                            return (
                              <div key={tool.toolCallId} className="w-full flex flex-col rounded-xl overflow-hidden border border-zinc-200/80 bg-[#0d1117] shadow-sm my-1">
                                <div className="flex items-center justify-between px-3 py-2 border-b border-white/10 bg-[#161b22]">
                                  <div className="flex items-center gap-2 text-[11px] font-medium text-zinc-400">
                                    <TerminalIcon className="w-3.5 h-3.5 text-zinc-500" />
                                    Terminal Command
                                  </div>
                                  
                                  {/* Inline Status & Actions */}
                                  <div className="flex items-center gap-2">
                                    {isDone ? (
                                      <span className="text-[10px] text-emerald-400 flex items-center gap-1"><Check className="w-3 h-3"/> Executed</span>
                                    ) : isCommandRunning ? (
                                      <span className="text-[10px] text-blue-400 flex items-center gap-1"><Loader2 className="w-3 h-3 animate-spin"/> Running</span>
                                    ) : mode === 'cmd' && isCall ? (
                                      <div className="flex items-center gap-1">
                                        <Button variant="ghost" size="sm" onClick={() => rejectPendingCommand(tool.toolCallId, tool.toolName)} className="h-6 px-2 text-[10px] text-zinc-400 hover:text-red-400 hover:bg-red-500/10">Reject</Button>
                                        <Button size="sm" onClick={() => executePendingCommand(tool.toolCallId, tool.toolName, tool.args?.command||'')} className="h-6 px-3 text-[10px] bg-blue-600 hover:bg-blue-500 text-white">Run <CornerDownLeft className="w-3 h-3 ml-1"/></Button>
                                      </div>
                                    ) : (
                                      <span className="text-[10px] text-zinc-500">Pending</span>
                                    )}
                                  </div>
                                </div>
                                <div className="p-3 text-[13px] font-mono text-zinc-100 whitespace-pre-wrap leading-relaxed">
                                  <span className="text-zinc-500 select-none mr-3">$</span>
                                  {tool.args?.command || '(waiting for command...)'}
                                </div>
                                
                                {isDone && tool.output && (
                                  <div className="border-t border-white/10 bg-[#0a0c10]">
                                    <details className="group">
                                      <summary className="px-3 py-2 text-[10px] text-zinc-500 hover:text-zinc-300 font-mono cursor-pointer select-none list-none [&::-webkit-details-marker]:hidden flex items-center">
                                        <ChevronDown className="w-3 h-3 mr-1.5 transition-transform group-open:-rotate-180" />
                                        Show Output
                                      </summary>
                                      <div className="px-3 pb-3 text-[11px] font-mono text-zinc-400 whitespace-pre-wrap max-h-64 overflow-y-auto">
                                        {typeof tool.output === 'string' ? tool.output : JSON.stringify(tool.output, null, 2)}
                                      </div>
                                    </details>
                                  </div>
                                )}
                              </div>
                            );
                          }
                          // Generic Tool fallback...
                          return (
                            <div key={tool.toolCallId} className="w-full p-3 rounded-xl border border-zinc-200 bg-zinc-50 text-[11px] font-mono text-zinc-600">
                              <span className="font-semibold text-zinc-800">{tool.toolName}</span> {tool.state}
                            </div>
                          );
                        })}
                      </div>
                    )}
                  </div>
                </div>
              );
            })}

            {isLoading && !messages.find((m:any) => m.role === 'assistant' && !getMessageText(m)) && (
              <div className="flex items-center gap-2 text-zinc-400 text-xs mt-2">
                <Loader2 className="w-4 h-4 animate-spin text-blue-500" />
                <span>Agent is thinking...</span>
              </div>
            )}
          </div>
        )}
        <div ref={chatEndRef} />
      </div>

      {/* Floating Omnibar */}
      <div className="absolute bottom-6 left-1/2 -translate-x-1/2 w-full max-w-3xl px-4 z-20">
        <div className="bg-white rounded-2xl shadow-[0_8px_30px_rgb(0,0,0,0.08)] border border-zinc-200 overflow-visible relative flex flex-col focus-within:shadow-[0_8px_30px_rgb(0,0,0,0.12)] focus-within:border-zinc-300 transition-all">
          
          {/* Internal Tabs for Mode */}
          <div className="absolute -top-[34px] left-4 flex items-center gap-1 bg-zinc-100 p-1 rounded-t-xl rounded-b-none border-t border-l border-r border-zinc-200 shadow-sm">
            <button
              onClick={() => setMode('cmd')}
              className={`px-3 py-1 rounded-md text-[11px] font-medium transition-all ${mode === 'cmd' ? 'bg-white text-zinc-800 shadow-sm' : 'text-zinc-500 hover:text-zinc-700'}`}
            >
              Command
            </button>
            <button
              onClick={() => setMode('agent')}
              className={`px-3 py-1 rounded-md text-[11px] font-medium transition-all flex items-center gap-1 ${mode === 'agent' ? 'bg-white text-blue-600 shadow-sm' : 'text-zinc-500 hover:text-zinc-700'}`}
            >
              <Sparkles className="w-3 h-3"/> Agent
            </button>
          </div>

          <form onSubmit={handleSlashSubmit} className="flex flex-col pt-3">
            {/* Context Mentions */}
            <div className="px-4 pb-1 flex items-center gap-2 flex-wrap">
              {mode === 'cmd' ? (
                <div className="inline-flex items-center gap-1.5 bg-zinc-100/80 text-zinc-600 text-[11px] px-2.5 py-1 rounded-lg font-medium border border-zinc-200/50">
                  <TerminalIcon className="w-3 h-3" />
                  {activeAsset ? activeAsset.ip : 'localhost'}
                </div>
              ) : selectedAgentAsset ? (
                <div className="inline-flex items-center gap-1.5 bg-blue-50/80 text-blue-700 text-[11px] px-2.5 py-1 rounded-lg font-medium border border-blue-100/50 pr-1">
                  <span className="text-blue-500 font-bold">@</span>
                  {selectedAgentAsset.ip}
                  <button type="button" onClick={() => setSelectedAgentAsset(null)} className="ml-0.5 p-0.5 hover:bg-blue-100 rounded text-blue-500"><X className="w-3 h-3" /></button>
                </div>
              ) : null}
              
              <button 
                type="button" 
                onClick={() => setShowContextMenu(!showContextMenu)}
                className="inline-flex items-center gap-1 text-zinc-400 hover:text-zinc-700 text-[12px] px-1 py-1 rounded font-medium transition-colors"
              >
                <span className="font-bold">@</span> Mention...
              </button>
            </div>

            <textarea
              value={input || ''}
              onChange={handleInputChange}
              disabled={models.length === 0 || isLoading}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault();
                  handleSubmit(e as any);
                }
              }}
              placeholder={mode === 'cmd' ? "Ask anything or type a command... (Cmd+/ to toggle mode)" : "Ask Agent to analyze or explore..."}
              className="w-full bg-transparent border-0 resize-none px-4 py-2 text-[14px] text-zinc-800 placeholder:text-zinc-400 disabled:opacity-50 focus:outline-none focus:ring-0 min-h-[50px] max-h-[200px]"
              rows={input.split('\\n').length > 1 ? Math.min(input.split('\\n').length, 8) : 1}
            />

            <div className="flex items-center justify-between px-3 py-2">
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
              <div className="flex items-center gap-1.5">
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
"""

with open("frontend/src/app/workspace/terminal/terminal-agent-ui.tsx", "w") as f:
    f.write(new_code)
