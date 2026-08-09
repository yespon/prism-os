import { useCallback, useState, useRef } from 'react';

import { asJsonObject, asTerminalAssets, errorMessage } from './message-types';
import type { TerminalMessage, TerminalMessagePart } from './message-types';
import type { InteractionRequest, InteractionResponse } from './types';

export interface TerminalAgentOptions {
  taskId: string;
  terminalSessionId?: string | null;
  modelName?: string;
  assetId?: string;
  assetIp?: string;
  selectedAssets?: { id: string; ip: string; name?: string }[];  // Multi-host in Agent mode
  mode: 'cmd' | 'agent';
  onExecuteCommand: (command: string) => Promise<string>;
  onSendInput?: (input: string) => void;
  onCancelCommand?: () => void;
  skillInstructions?: string;
}

/**
 * Thin communication layer between the frontend UI and the backend LangGraph terminal agent.
 *
 * Responsibilities:
 *   - Send user messages to the backend agent API (SSE streaming)
 *   - Parse AG-UI protocol events into React state
 *   - Handle tool call approval/rejection
 *
 * Architecture: Frontend → Next.js BFF API → FastAPI /api/v1/agent/terminal/invoke → LangGraph
 */
export function useTerminalAgent({
  taskId,
  terminalSessionId,
  modelName = 'gpt-4o',
  assetId,
  assetIp: _assetIp,
  selectedAssets,
  mode,
  onExecuteCommand,
  onSendInput,
  onCancelCommand,
  skillInstructions,
}: TerminalAgentOptions) {
  const [input, setInput] = useState('');
  const [messages, setMessages] = useState<TerminalMessage[]>([]);
  const [isLoading, setIsLoading] = useState(false);

  // Current interaction state (e.g., clarify question from agent)
  const [currentInteraction, setCurrentInteraction] = useState<InteractionRequest | null>(null);

  // Command execution state (for UI feedback)
  const [isCommandRunning, setIsCommandRunning] = useState(false);

  // Dangerous command pending user confirmation
  const [pendingDangerousTool] = useState<{
    toolCallId: string;
    command: string;
    reason?: string;
  } | null>(null);

  // Dedup refs for SSE stream events (prevent graph-resume duplicates)
  const startedMessageIdsRef = useRef<Set<string>>(new Set());
  const lastContentLengthRef = useRef(0);

  // Abort controller for cancelling in-flight requests
  const abortControllerRef = useRef<AbortController | null>(null);

  // ------------------------------------------------------------------
  // SSE Stream Parser — parses AG-UI protocol events from the backend
  // ------------------------------------------------------------------

  const processStream = useCallback(async (res: Response) => {
    if (!res.body) return;

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop() ?? '';

      for (const line of lines) {
        if (line.startsWith('data: ')) {
          try {
            const data = JSON.parse(line.slice(6));

            switch (data.type) {
              // --- Lifecycle ---
              case 'RUN_STARTED':
                break;

              case 'RUN_FINISHED':
                console.log('[useTerminalAgent] RUN_FINISHED');
                setIsLoading(false);
                setIsCommandRunning(false);
                break;

              case 'RUN_ERROR':
                console.error('[useTerminalAgent] RUN_ERROR:', data.message);
                setMessages(prev => {
                  if (prev.some(m => m.id === `msg-${taskId}`)) {
                    return prev.map(m =>
                      m.id === `msg-${taskId}`
                        ? { ...m, content: `❌ Error: ${data.message}` }
                        : m
                    );
                  }
                  return [
                    ...prev,
                    {
                      role: 'assistant',
                      content: `❌ Error: ${data.message}`,
                      id: `err-${Date.now()}`,
                      parts: [],
                    },
                  ];
                });
                setIsLoading(false);
                break;

              // --- Text Messages ---
               case 'TEXT_MESSAGE_START':
                if (startedMessageIdsRef.current.has(data.messageId)) break;
                startedMessageIdsRef.current.add(data.messageId);
                setMessages(prev => {
                  if (prev.some(m => m.id === data.messageId)) return prev;
                  return [...prev, { role: 'assistant', content: '', id: data.messageId, parts: [] }];
                });
                break;

              case 'TEXT_MESSAGE_CONTENT':
                setMessages(prev => {
                  const updated = prev.map(m =>
                    m.id === data.messageId
                      ? {
                          ...m,
                          content: `${typeof m.content === 'string' ? m.content : ''}${data.delta ?? ''}`,
                        }
                      : m
                  );
                  return updated;
                });
                break;

              case 'TEXT_MESSAGE_END':
                // Message complete — no action needed
                break;

              // --- Thinking (Reasoning) ---
              case 'THINKING_START':
                setMessages(prev => {
                  const last = prev[prev.length - 1];
                  if (!last) return prev;
                  const newParts = last.parts ? [...last.parts] : [];
                  newParts.push({ type: 'reasoning', id: data.messageId, text: '' });
                  return [...prev.slice(0, -1), { ...last, parts: newParts }];
                });
                break;

              case 'THINKING_CONTENT':
                setMessages(prev => {
                  const last = prev[prev.length - 1];
                  if (!last) return prev;
                  const newParts = last.parts?.map((p: TerminalMessagePart) => {
                    if (p.type === 'reasoning' && p.id === data.messageId) {
                      return { ...p, text: `${p.text ?? ''}${data.delta ?? ''}` };
                    }
                    return p;
                  });
                  return [...prev.slice(0, -1), { ...last, parts: newParts }];
                });
                break;

              case 'THINKING_END':
                // Reasoning block complete
                break;

              // --- Steps (Execution Plan) ---
              case 'STEP_STARTED':
                setMessages(prev => {
                  const targetId = data.messageId;
                  const targetIdx = targetId
                    ? prev.findIndex(m => m.id === targetId)
                    : prev.length - 1;
                  if (targetIdx < 0) return prev;
                  const last = prev[targetIdx];
                  if (!last) return prev;
                  const newParts = last.parts ? [...last.parts] : [];
                  newParts.push({ type: 'step', stepName: data.stepName, state: 'running' });
                  return [...prev.slice(0, targetIdx), { ...last, parts: newParts }, ...prev.slice(targetIdx + 1)];
                });
                break;

              case 'STEP_FINISHED':
                setMessages(prev => {
                  const targetId = data.messageId;
                  const targetIdx = targetId
                    ? prev.findIndex(m => m.id === targetId)
                    : prev.length - 1;
                  if (targetIdx < 0) return prev;
                  const last = prev[targetIdx];
                  if (!last) return prev;
                  const newParts = last.parts?.map((p: TerminalMessagePart) => {
                    if (p.type === 'step' && p.stepName === data.stepName) {
                      return { ...p, state: 'completed' };
                    }
                    return p;
                  });
                  return [...prev.slice(0, targetIdx), { ...last, parts: newParts }, ...prev.slice(targetIdx + 1)];
                });
                break;

              // --- Tool Calls ---
              case 'TOOL_CALL_START':
                setIsCommandRunning(true);
                setMessages(prev => {
                  const targetId = data.messageId;
                  const targetIdx = targetId
                    ? prev.findIndex(m => m.id === targetId)
                    : prev.length - 1;
                  if (targetIdx < 0) return prev;
                  const last = prev[targetIdx];
                  if (!last) return prev;
                  const newParts = last.parts ? [...last.parts] : [];
                  newParts.push({
                    type: `tool-${data.toolCallName}`,
                    toolName: data.toolCallName,
                    toolCallId: data.toolCallId,
                    state: 'input-streaming',
                    input: {},
                  });
                  return [...prev.slice(0, targetIdx), { ...last, parts: newParts }, ...prev.slice(targetIdx + 1)];
                });
                break;

              case 'TOOL_CALL_ARGS':
                setMessages(prev => {
                  const targetId = data.messageId;
                  const targetIdx = targetId
                    ? prev.findIndex(m => m.id === targetId)
                    : prev.length - 1;
                  if (targetIdx < 0) return prev;
                  const last = prev[targetIdx];
                  if (!last) return prev;
                  const newParts = last.parts?.map((p: TerminalMessagePart) => {
                    if (p.toolCallId === data.toolCallId) {
                      return { ...p, _rawArgs: `${p._rawArgs ?? ''}${data.delta ?? ''}` };
                    }
                    return p;
                  });
                  return [...prev.slice(0, targetIdx), { ...last, parts: newParts }, ...prev.slice(targetIdx + 1)];
                });
                break;

              case 'TOOL_CALL_END':
                setMessages(prev => {
                  const targetId = data.messageId;
                  const targetIdx = targetId
                    ? prev.findIndex(m => m.id === targetId)
                    : prev.length - 1;
                  if (targetIdx < 0) return prev;
                  const last = prev[targetIdx];
                  if (!last) return prev;
                  const newParts = last.parts?.map((p: TerminalMessagePart) => {
                    if (p.toolCallId === data.toolCallId) {
                      let finalInput = p.input ?? {};
                      if (p._rawArgs) {
                        try {
                          finalInput = asJsonObject(JSON.parse(p._rawArgs));
                        } catch (e) {
                          console.error('Failed to parse tool args', e, p._rawArgs);
                        }
                      }
                      // Agent mode: tools auto-execute by default (show 'auto-executing' state)
                      // Command mode: tools need confirmation (show Run/Reject via 'input-available')
                      const defaultState = mode === 'agent' ? 'auto-executing' : 'input-available';
                      return { ...p, state: defaultState, input: finalInput };
                    }
                    return p;
                  });
                  return [...prev.slice(0, targetIdx), { ...last, parts: newParts }, ...prev.slice(targetIdx + 1)];
                });
                break;

              case 'TOOL_CALL_RESULT':
                setMessages(prev => {
                  let found = false;
                  const updated = prev.map(m => {
                    if (!m.parts) return m;
                    let modified = false;
                    const newParts = m.parts.map((p: TerminalMessagePart) => {
                      if (p.toolCallId === data.toolCallId) {
                        found = true;
                        modified = true;
                        return {
                          ...p,
                          state: data.isError ? 'output-error' : 'output-available',
                          output: data.content,
                          errorText: data.isError ? data.content : undefined,
                        };
                      }
                      return p;
                    });
                    return modified ? { ...m, parts: newParts } : m;
                  });

                  if (!found) {
                    updated.push({
                      role: 'assistant',
                      id: `msg-${data.toolCallId}`,
                      parts: [
                        {
                          type: 'tool-unknown',
                          toolName: 'unknown',
                          toolCallId: data.toolCallId,
                          state: data.isError ? 'output-error' : 'output-available',
                          output: data.content,
                          errorText: data.isError ? data.content : undefined,
                        },
                      ],
                    });
                  }
                  return updated;
                });
                setIsCommandRunning(false);
                break;

              // --- Clarification / Human-in-the-Loop ---
              case 'CLARIFICATION_REQUEST':
                setCurrentInteraction({
                  commandId: data.messageId,
                  interactionType: 'freeform',
                  promptHint: data.question,
                  options: data.options ?? [],
                  optionValues: data.options ?? [],
                });
                break;

              case 'CLARIFICATION_RESPONSE':
                setCurrentInteraction(null);
                break;

              // --- Agent Mode: Tool Approval Required ---
              case 'TOOL_APPROVAL_REQUIRED':
                // Switch matching tool calls from 'auto-executing' to 'input-available'
                  if (data.toolCalls && Array.isArray(data.toolCalls)) {
                    const toolCalls = data.toolCalls as Array<{
                      toolCallId?: string;
                      security?: {
                        reason?: string;
                        risk_level?: string;
                        is_state_changing?: boolean;
                      target_assets?: unknown;
                      };
                    }>;
                    setMessages(prev =>
                    prev.map(m => {
                      if (!m.parts) return m;
                      const newParts = m.parts.map((p: TerminalMessagePart) => {
                        const match = toolCalls.find((tc) => tc.toolCallId === p.toolCallId);
                        if (match) {
                          return {
                            ...p,
                            state: 'input-available',
                            approval: {
                              reason: match.security?.reason,
                              riskLevel: match.security?.risk_level,
                              isStateChanging: match.security?.is_state_changing,
                              targetAssets: asTerminalAssets(match.security?.target_assets),
                            },
                          };
                        }
                        return p;
                      });
                      return { ...m, parts: newParts };
                    })
                  );
                }
                break;

              default:
                // Unknown event type — log for debugging
                console.debug('[useTerminalAgent] Unknown event:', data.type, data);
            }
          } catch {
            // Ignore parse errors for non-JSON lines
          }
        }
      }
    }
  }, [mode]);

  // ------------------------------------------------------------------
  // Send Message — posts user input to the backend agent
  // ------------------------------------------------------------------

  const sendMessage = useCallback(
    async (msg: { text: string }) => {
      setIsLoading(true);
      setIsCommandRunning(false);

      // Rename the old active assistant message ID to avoid collision with the new message,
      // then append the new user message and a pre-created assistant message with the active ID.
      setMessages(prev => {
        const renamed = prev.map(m => {
          if (m.id === `msg-${taskId}`) {
            return { ...m, id: `msg-${taskId}-${Date.now()}` };
          }
          return m;
        });
        return [
          ...renamed,
          { role: 'user', content: msg.text, id: `user-${Date.now()}` },
          { role: 'assistant', content: '', id: `msg-${taskId}`, parts: [] }
        ];
      });

      // Reset dedup state
      startedMessageIdsRef.current.clear();
      lastContentLengthRef.current = 0;

      // Create abort controller for this request
      abortControllerRef.current = new AbortController();

      try {
        const res = await fetch('/api/terminal/chat', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            session_id: taskId,
            terminal_session_id: mode === 'agent' ? '' : (terminalSessionId ?? ''),
            model_name: modelName,
            asset_id: assetId ?? '',
            selected_assets: selectedAssets ?? [],
            mode,
            user_input: msg.text,
            skill_instructions: skillInstructions ?? "",
          }),
          signal: abortControllerRef.current.signal,
        });

        if (!res.ok) {
          const errText = await res.text();
          setMessages(prev => {
            if (prev.some(m => m.id === `msg-${taskId}`)) {
              return prev.map(m =>
                m.id === `msg-${taskId}`
                  ? { ...m, content: `❌ Backend error (${res.status}): ${errText}` }
                  : m
              );
            }
            return [
              ...prev,
              {
                role: 'assistant',
                content: `❌ Backend error (${res.status}): ${errText}`,
                id: `err-${Date.now()}`,
                parts: [],
              },
            ];
          });
          setIsLoading(false);
          return;
        }

        await processStream(res);
      } catch (error: unknown) {
        if (error instanceof Error && error.name === 'AbortError') {
          console.log('[useTerminalAgent] Request cancelled');
        } else {
          console.error('[useTerminalAgent] sendMessage error:', error);
          setMessages(prev => {
            if (prev.some(m => m.id === `msg-${taskId}`)) {
              return prev.map(m =>
                m.id === `msg-${taskId}`
                  ? { ...m, content: `❌ Network error: ${errorMessage(error)}` }
                  : m
              );
            }
            return [
              ...prev,
              {
                role: 'assistant',
                content: `❌ Network error: ${errorMessage(error)}`,
                id: `err-${Date.now()}`,
                parts: [],
              },
            ];
          });
        }
        setIsLoading(false);
      }
    },
    [taskId, terminalSessionId, modelName, assetId, selectedAssets, mode, skillInstructions, processStream]
  );

  // ------------------------------------------------------------------
  // Tool Approval — approve or reject a pending tool call
  // ------------------------------------------------------------------

  const approveToolCall = useCallback(
    async (toolCallId: string, approved: boolean) => {
      try {
        const res = await fetch('/api/terminal/chat/approve', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            session_id: taskId,
            tool_call_id: toolCallId,
            approved,
          }),
        });

        if (!res.ok) {
          console.error('[useTerminalAgent] Approve failed:', res.status);
          return;
        }

        // If rejected, update UI immediately
        if (!approved) {
          setMessages(prev =>
            prev.map(m => {
              if (!m.parts) return m;
              const newParts = m.parts.map((p: TerminalMessagePart) => {
                if (p.toolCallId === toolCallId) {
                  return {
                    ...p,
                    state: 'output-error',
                    errorText: 'User rejected the command.',
                  };
                }
                return p;
              });
              return { ...m, parts: newParts };
            })
          );
        }

        setIsCommandRunning(true);
        
        // Reset dedup refs for the new SSE stream from graph resume
        startedMessageIdsRef.current.clear();
        lastContentLengthRef.current = 0;
        
        // Update tool part state to 'auto-executing' (running)
        setMessages(prev =>
          prev.map(m => {
            if (!m.parts) return m;
            const newParts = m.parts.map((p: TerminalMessagePart) => {
              if (p.toolCallId === toolCallId) {
                return { ...p, state: 'auto-executing' };
              }
              return p;
            });
            return { ...m, parts: newParts };
          })
        );
        
        await processStream(res);
      } catch (error: unknown) {
        console.error('[useTerminalAgent] approveToolCall error:', errorMessage(error));
      }
    },
    [taskId, processStream]
  );

  const executePendingCommand = useCallback(
    (toolCallId: string, _toolName: string, _command: string) => {
      void approveToolCall(toolCallId, true);
    },
    [approveToolCall]
  );

  const rejectPendingCommand = useCallback(
    (toolCallId: string, _toolName: string) => {
      void approveToolCall(toolCallId, false);
    },
    [approveToolCall]
  );

  // ------------------------------------------------------------------
  // Interaction Handlers
  // ------------------------------------------------------------------

  const submitInteraction = useCallback(
    (response: InteractionResponse) => {
      if (onSendInput) {
        onSendInput(response.input + (response.appendNewline ? '\n' : ''));
      }
      setCurrentInteraction(null);
    },
    [onSendInput]
  );

  const dismissInteraction = useCallback(() => {
    setCurrentInteraction(null);
  }, []);

  const suppressInteraction = useCallback(() => {
    setCurrentInteraction(null);
  }, []);

  const cancelCommand = useCallback(() => {
    setCurrentInteraction(null);
    setIsCommandRunning(false);
    if (onCancelCommand) {
      onCancelCommand();
    }
  }, [onCancelCommand]);

  // ------------------------------------------------------------------
  // Input Handlers
  // ------------------------------------------------------------------

  const handleInputChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => {
      setInput(e.target.value);
    },
    []
  );

  const handleSubmit = useCallback(
    (e: React.FormEvent<HTMLFormElement>) => {
      e.preventDefault();
      if (!input.trim() || isLoading) return;
      void sendMessage({ text: input });
      setInput('');
    },
    [input, isLoading, sendMessage]
  );

  // ------------------------------------------------------------------
  // Return value
  // ------------------------------------------------------------------

  return {
    messages,
    input,
    handleInputChange,
    handleSubmit,
    isLoading,
    isDetectingInteraction: false, // No longer needed — backend handles this
    sendMessage,
    addToolResult: useCallback(() => undefined, []), // Placeholder for future use
    todos: [], // Managed by backend graph state
    focusChain: null, // Managed by backend
    currentInteraction,
    submitInteraction,
    dismissInteraction,
    suppressInteraction,
    cancelCommand,
    commandOutput: '', // Streamed via messages now
    isCommandRunning,
    executeCommandWithInteraction: onExecuteCommand, // Direct passthrough
    executePendingCommand,
    rejectPendingCommand,
    pendingDangerousTool,
    confirmDangerousCommand: () => undefined, // Placeholder
    rejectDangerousCommand: () => undefined, // Placeholder
    detectInteraction: async () => null, // No longer needed — backend handles this
    hydrateMessages: setMessages,
  };
}
