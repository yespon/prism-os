"use client";

import {
  LockKeyhole,
  Send,
  Check,
  X,
  AlertTriangle,
  ListChecks,
  Keyboard,
  Ellipsis,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  ArrowDownToLine,
  ArrowUpToLine,
  CornerDownLeft,
  EyeOff,
  Play,
  Pause,
  RotateCcw,
  CircleAlert,
  Loader2,
} from 'lucide-react';
import React, { useState, useRef, useEffect } from 'react';

import { Button } from '@/components/ui/button';

export type InteractionType =
  | 'password'
  | 'confirm'
  | 'select'
  | 'pager'
  | 'enter'
  | 'freeform';

export interface ConfirmValues {
  yes?: string;
  no?: string;
  default?: boolean;
}

export interface InteractionState {
  commandId: string;
  interactionType: InteractionType;
  promptHint: string;
  options?: string[];
  optionValues?: string[];
  confirmValues?: ConfirmValues;
  exitKey?: string;
  exitAppendNewline?: boolean;
  isSuppressed?: boolean;
  tuiDetected?: boolean;
  tuiMessage?: string;
  errorMessage?: string;
  isSubmitting?: boolean;
}

interface CommandInteractionInputProps {
  state: InteractionState;
  onSubmit: (params: {
    commandId: string;
    input: string;
    appendNewline: boolean;
    interactionType: InteractionType;
  }) => void;
  onCancel: (commandId: string) => void;
  onDismiss: (commandId: string) => void;
  onSuppress: (commandId: string) => void;
  onUnsuppress: (commandId: string) => void;
  onFocusTerminal: () => void;
  onClearError: (commandId: string) => void;
}

export function CommandInteractionInput({
  state,
  onSubmit,
  onCancel,
  onDismiss,
  onSuppress,
  onUnsuppress,
  onFocusTerminal,
  onClearError,
}: CommandInteractionInputProps) {
  const [inputValue, setInputValue] = useState('');
  const [manualInput, setManualInput] = useState('');
  const [isManualMode, setIsManualMode] = useState(false);
  const [showMoreMenu, setShowMoreMenu] = useState(false);

  const passwordInputRef = useRef<HTMLInputElement>(null);
  const manualInputRef = useRef<HTMLInputElement>(null);
  const freeformInputRef = useRef<HTMLInputElement>(null);

  // Reset state when interaction type changes
  useEffect(() => {
    setInputValue('');
    setManualInput('');
    setIsManualMode(false);
  }, [state.interactionType, state.commandId]);

  // Auto-focus on mount/visibility
  useEffect(() => {
    const timer = setTimeout(() => {
      if (state.interactionType === 'password' && passwordInputRef.current) {
        passwordInputRef.current.focus();
      } else if (state.interactionType === 'freeform' && freeformInputRef.current) {
        freeformInputRef.current.focus();
      } else if (isManualMode && manualInputRef.current) {
        manualInputRef.current.focus();
      }
    }, 100);
    return () => clearTimeout(timer);
  }, [state.interactionType, state.commandId, isManualMode]);

  const handleSubmit = (input: string, appendNewline: boolean) => {
    onSubmit({
      commandId: state.commandId,
      input,
      appendNewline,
      interactionType: state.interactionType,
    });
    setInputValue('');
    setManualInput('');
  };

  // ------ Exit key logic (matching Chaterm) ------
  const ctrlCVariants = ['\\x03', 'ctrlc', 'ctrl+c', '^c'];
  const normalizedExit = state.exitKey?.toLowerCase().replace(/[\s\-_]/g, '') ?? '';
  const hasCustomExitKey =
    state.interactionType !== 'pager' &&
    !!state.exitKey &&
    !ctrlCVariants.includes(normalizedExit);

  const exitButtonLabel = hasCustomExitKey
    ? `Exit (${state.exitKey})`
    : 'Ctrl+C';

  const handleExit = () => {
    if (hasCustomExitKey && state.exitKey) {
      const appendNewline = state.exitAppendNewline ?? true;
      handleSubmit(state.exitKey, appendNewline);
    } else {
      onCancel(state.commandId);
    }
  };

  // Map interaction type to icon
  const InteractionIcon = {
    password: LockKeyhole,
    confirm: AlertTriangle,
    select: ListChecks,
    pager: ArrowDownToLine,
    enter: CornerDownLeft,
    freeform: Keyboard,
  }[state.interactionType] || Keyboard;

  const iconColor = {
    password: 'text-amber-500',
    confirm: 'text-orange-500',
    select: 'text-blue-500',
    pager: 'text-purple-500',
    enter: 'text-emerald-500',
    freeform: 'text-zinc-500',
  }[state.interactionType] || 'text-zinc-500';

  return (
    <div className="bg-zinc-50/80 border border-zinc-200 rounded-xl p-4 my-3 shadow-sm">
      {/* Header: Icon + Hint + Exit button + More menu */}
      <div className="flex items-start justify-between mb-3">
        <div className="flex items-center gap-2.5 flex-1">
          <InteractionIcon className={`w-4 h-4 shrink-0 mt-0.5 ${iconColor}`} />
          <span className="text-[13px] font-semibold text-zinc-800 leading-snug break-words">
            {state.promptHint || 'Input required'}
          </span>
        </div>

        <div className="flex items-center gap-1.5 ml-2 shrink-0">
          {/* Exit/Cancel button */}
          {!state.isSuppressed && (
            <Button
              variant="ghost"
              size="sm"
              className="h-6 text-[10px] font-mono text-red-500 hover:text-red-700 hover:bg-red-50 px-2 rounded"
              onClick={handleExit}
              title={exitButtonLabel}
            >
              {exitButtonLabel}
            </Button>
          )}

          {/* More menu: Dismiss / Suppress / Restore */}
          <div className="relative">
            <Button
              variant="ghost"
              size="icon"
              className="h-6 w-6 text-zinc-400 hover:text-zinc-600"
              onClick={() => setShowMoreMenu(!showMoreMenu)}
            >
              <Ellipsis className="w-3.5 h-3.5" />
            </Button>
            {showMoreMenu && (
              <>
                <div
                  className="fixed inset-0 z-10"
                  onClick={() => setShowMoreMenu(false)}
                />
                <div className="absolute right-0 top-full mt-1 bg-white border border-zinc-200 rounded-lg shadow-lg z-20 py-1 min-w-[140px]">
                  {!state.isSuppressed && (
                    <>
                      <button
                        className="w-full text-left px-3 py-1.5 text-xs text-zinc-600 hover:bg-zinc-50"
                        onClick={() => { setShowMoreMenu(false); onDismiss(state.commandId); }}
                      >
                        Dismiss
                      </button>
                      <button
                        className="w-full text-left px-3 py-1.5 text-xs text-zinc-600 hover:bg-zinc-50"
                        onClick={() => { setShowMoreMenu(false); onSuppress(state.commandId); }}
                      >
                        Suppress
                      </button>
                    </>
                  )}
                  {state.isSuppressed && (
                    <button
                      className="w-full text-left px-3 py-1.5 text-xs text-blue-600 hover:bg-blue-50"
                      onClick={() => { setShowMoreMenu(false); onUnsuppress(state.commandId); }}
                    >
                      Restore interaction
                    </button>
                  )}
                </div>
              </>
            )}
          </div>
        </div>
      </div>

      {/* Suppressed notice */}
      {state.isSuppressed && (
        <div className="flex items-center justify-between px-3 py-2 bg-amber-50 border border-amber-200 rounded-lg mb-2">
          <span className="text-xs text-amber-700">
            Interaction suppressed — output may still appear in terminal.
          </span>
          <Button
            variant="ghost"
            size="sm"
            className="h-6 text-xs text-blue-600 hover:text-blue-700 hover:bg-blue-50"
            onClick={() => onUnsuppress(state.commandId)}
          >
            Restore
          </Button>
        </div>
      )}

      {/* Main Interaction Body */}
      {!state.isSuppressed && (
        <div className="space-y-3">
          {/* Password */}
          {state.interactionType === 'password' && (
            <div className="flex gap-2 items-center">
              <div className="relative flex-1">
                <LockKeyhole className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-zinc-400" />
                <input
                  ref={passwordInputRef}
                  type="password"
                  value={inputValue}
                  onChange={(e) => setInputValue(e.target.value)}
                  placeholder="Enter password..."
                  className="w-full pl-9 pr-3 py-1.5 text-[13px] border border-zinc-200 rounded-md focus:outline-none focus:border-blue-400 focus:ring-1 focus:ring-blue-400/30 bg-white"
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' && inputValue.trim()) {
                      handleSubmit(inputValue, true);
                    }
                  }}
                />
              </div>
              <Button
                size="sm"
                className="h-8 text-xs bg-blue-600 hover:bg-blue-700 text-white rounded-md"
                onClick={() => inputValue.trim() && handleSubmit(inputValue, true)}
                disabled={!inputValue.trim()}
              >
                <Send className="w-3 h-3 mr-1" />
                Send
              </Button>
            </div>
          )}

          {/* Confirm */}
          {state.interactionType === 'confirm' && !isManualMode && (
            <div className="flex flex-wrap gap-2">
              <Button
                size="sm"
                className="h-7 text-xs bg-emerald-600 hover:bg-emerald-700 text-white rounded-md"
                onClick={() => handleSubmit(state.confirmValues?.yes ?? 'y', true)}
              >
                <Check className="w-3 h-3 mr-1" />
                Yes ({state.confirmValues?.yes ?? 'y'})
              </Button>
              <Button
                size="sm"
                variant="outline"
                className="h-7 text-xs rounded-md"
                onClick={() => handleSubmit(state.confirmValues?.no ?? 'n', true)}
              >
                <X className="w-3 h-3 mr-1" />
                No ({state.confirmValues?.no ?? 'n'})
              </Button>
              {state.confirmValues?.default && (
                <Button
                  size="sm"
                  variant="ghost"
                  className="h-7 text-xs rounded-md"
                  onClick={() => handleSubmit('', true)}
                >
                  <CornerDownLeft className="w-3 h-3 mr-1" />
                  Default (Enter)
                </Button>
              )}
              <Button
                size="sm"
                variant="ghost"
                className="h-7 text-xs text-zinc-500 rounded-md border-dashed border"
                onClick={() => setIsManualMode(true)}
              >
                Manual input
              </Button>
            </div>
          )}

          {/* Select */}
          {state.interactionType === 'select' && !isManualMode && (
            <div className="flex flex-wrap gap-2">
              {state.options?.map((option, i) => (
                <Button
                  key={i}
                  size="sm"
                  variant="outline"
                  className="h-7 text-xs rounded-md hover:bg-blue-50 hover:border-blue-300"
                  onClick={() =>
                    handleSubmit(
                      state.optionValues?.[i] ?? String(i + 1),
                      true
                    )
                  }
                >
                  {option}
                </Button>
              ))}
              <Button
                size="sm"
                variant="ghost"
                className="h-7 text-xs text-zinc-500 rounded-md border-dashed border"
                onClick={() => setIsManualMode(true)}
              >
                Manual input
              </Button>
            </div>
          )}

          {/* Pager */}
          {state.interactionType === 'pager' && !isManualMode && (
            <div className="flex flex-wrap gap-1.5 p-2 bg-zinc-100/70 rounded-lg">
              <Button
                size="sm"
                variant="ghost"
                className="h-7 text-xs rounded-md"
                onClick={() => handleSubmit('b', false)}
                title="Page up / Back"
              >
                <ChevronLeft className="w-3 h-3 mr-1" />
                Back (b)
              </Button>
              <Button
                size="sm"
                className="h-7 text-xs bg-blue-600 hover:bg-blue-700 text-white rounded-md"
                onClick={() => handleSubmit(' ', false)}
                title="Page down / Next"
              >
                Next (Space)
                <ChevronRight className="w-3 h-3 ml-1" />
              </Button>
              <Button
                size="sm"
                variant="ghost"
                className="h-7 text-xs rounded-md"
                onClick={() => handleSubmit('g', false)}
                title="Go to top"
              >
                <ArrowUpToLine className="w-3 h-3 mr-1" />
                Home (g)
              </Button>
              <Button
                size="sm"
                variant="ghost"
                className="h-7 text-xs rounded-md"
                onClick={() => handleSubmit('G', false)}
                title="Go to bottom"
              >
                <ArrowDownToLine className="w-3 h-3 mr-1" />
                End (G)
              </Button>
              <Button
                size="sm"
                variant="ghost"
                className="h-7 text-xs text-zinc-500 rounded-md border-dashed border"
                onClick={() => setIsManualMode(true)}
              >
                More...
              </Button>
              <Button
                size="sm"
                variant="ghost"
                className="h-7 text-xs text-red-500 hover:text-red-700 hover:bg-red-50 rounded-md"
                onClick={() => handleSubmit('q', false)}
              >
                Quit (q)
              </Button>
            </div>
          )}

          {/* Enter */}
          {state.interactionType === 'enter' && !isManualMode && (
            <div className="flex items-center gap-2">
              <Button
                size="sm"
                className="h-7 text-xs bg-blue-600 hover:bg-blue-700 text-white rounded-md min-w-[120px]"
                onClick={() => handleSubmit('', true)}
              >
                <CornerDownLeft className="w-3 h-3 mr-1" />
                Press Enter
              </Button>
              <Button
                size="sm"
                variant="link"
                className="h-7 text-xs text-zinc-500"
                onClick={() => setIsManualMode(true)}
              >
                Manual input
              </Button>
            </div>
          )}

          {/* Freeform (default) */}
          {state.interactionType === 'freeform' && (
            <div className="flex gap-2 items-center">
              <div className="relative flex-1">
                <Keyboard className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-zinc-400" />
                <input
                  ref={freeformInputRef}
                  type="text"
                  value={inputValue}
                  onChange={(e) => setInputValue(e.target.value)}
                  placeholder={state.promptHint || 'Enter input...'}
                  className="w-full pl-9 pr-3 py-1.5 text-[13px] border border-zinc-200 rounded-md focus:outline-none focus:border-blue-400 focus:ring-1 focus:ring-blue-400/30 bg-white"
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' && inputValue.trim()) {
                      handleSubmit(inputValue, true);
                    }
                  }}
                />
              </div>
              <Button
                size="sm"
                className="h-8 text-xs bg-blue-600 hover:bg-blue-700 text-white rounded-md"
                onClick={() => inputValue.trim() && handleSubmit(inputValue, true)}
                disabled={!inputValue.trim()}
              >
                <Send className="w-3 h-3 mr-1" />
                Send
              </Button>
            </div>
          )}

          {/* Manual input mode (shared across confirm/select/pager/enter) */}
          {isManualMode && (
            <div className="flex gap-2 items-center mt-2">
              <input
                ref={manualInputRef}
                type="text"
                value={manualInput}
                onChange={(e) => setManualInput(e.target.value)}
                placeholder="Enter custom input..."
                className="flex-1 px-3 py-1.5 text-[13px] border border-zinc-200 rounded-md focus:outline-none focus:border-blue-400 focus:ring-1 focus:ring-blue-400/30 bg-white"
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && manualInput.trim()) {
                    handleSubmit(
                      manualInput,
                      state.interactionType !== 'pager'
                    );
                  }
                }}
              />
              <Button
                size="sm"
                className="h-8 text-xs bg-blue-600 hover:bg-blue-700 text-white rounded-md"
                onClick={() =>
                  manualInput.trim() &&
                  handleSubmit(
                    manualInput,
                    state.interactionType !== 'pager'
                  )
                }
                disabled={!manualInput.trim()}
              >
                <Send className="w-3 h-3 mr-1" />
                Send
              </Button>
              <Button
                size="sm"
                variant="ghost"
                className="h-8 text-xs rounded-md"
                onClick={() => {
                  setIsManualMode(false);
                  setManualInput('');
                }}
              >
                Back
              </Button>
            </div>
          )}
        </div>
      )}

      {/* Error message */}
      {state.errorMessage && (
        <div className="flex items-center gap-2 px-3 py-2 bg-red-50 border border-red-200 rounded-md mt-3 text-[12px] text-red-700">
          <CircleAlert className="w-3.5 h-3.5 shrink-0" />
          <span className="flex-1">{state.errorMessage}</span>
          <button
            className="text-red-400 hover:text-red-600"
            onClick={() => onClearError(state.commandId)}
          >
            <X className="w-3.5 h-3.5" />
          </button>
        </div>
      )}

      {/* Loading state */}
      {state.isSubmitting && (
        <div className="flex items-center gap-2 px-3 py-2 text-zinc-500 text-xs mt-2">
          <Loader2 className="w-3 h-3 animate-spin" />
          <span>Sending input...</span>
        </div>
      )}

      {/* TUI detected notice */}
      {state.tuiDetected && (
        <div className="flex items-center gap-2 px-3 py-2 bg-amber-50 border border-amber-200 rounded-md mt-2 text-xs text-amber-700">
          <AlertTriangle className="w-3.5 h-3.5 shrink-0" />
          <span className="flex-1">{state.tuiMessage ?? 'TUI program detected — use terminal directly for best experience.'}</span>
          <Button
            variant="link"
            size="sm"
            className="h-6 text-xs text-blue-600 hover:text-blue-700"
            onClick={onFocusTerminal}
          >
            Switch to terminal
          </Button>
        </div>
      )}
    </div>
  );
}
