import { ChevronDown, HelpCircle, MessageSquarePlus, AlertTriangle, X } from "lucide-react";
import { useMemo, useState } from "react";

import { Button } from "@/components/ui/button";
import { useI18n } from "@/core/i18n/hooks";
import { cn } from "@/lib/utils";

import { MarkdownContent } from "./markdown-content";

interface ClarificationBlockProps {
  className?: string;
  content: string;
  isLoading: boolean;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  rehypePlugins?: any[];
  onSubmitOption?: (text: string) => void;
}

export function ClarificationBlock({
  className,
  content,
  isLoading,
  rehypePlugins,
  onSubmitOption,
}: ClarificationBlockProps) {
  const { t } = useI18n();
  const [selectedOption, setSelectedOption] = useState<string | null>(null);
  const [isCollapsed, setIsCollapsed] = useState(false);
  const [customInput, setCustomInput] = useState("");
  const [showCustomInput, setShowCustomInput] = useState(false);

  const { baseContent, options, isError } = useMemo(() => {
    // Detect if content contains an error message from tool invocation failure
    const isErrorContent =
      content.includes("Error invoking tool") ||
      content.includes("Please fix the error and try again");

    const lines = content.split("\n");
    const options: string[] = [];
    let splitIndex = lines.length;

    for (let i = lines.length - 1; i >= 0; i -= 1) {
      const line = lines[i];
      if (!line?.trim()) {
        continue;
      }

      // Match numbered options like "1. option text" or "① option text"
      const match = /^\s*(?:\d+[.．]|\u2460-\u2473)\s+(.+)$/.exec(line);
      if (match?.[1]) {
        options.unshift(match[1]);
        splitIndex = i;
      } else {
        break;
      }
    }

    if (splitIndex > 0) {
      const prevLine = lines[splitIndex - 1];
      if (prevLine && !prevLine.trim()) {
        splitIndex -= 1;
      }
    }

    const baseContent = lines.slice(0, splitIndex).join("\n");
    return { baseContent, options, isError: isErrorContent };
  }, [content]);

  const handleOptionSelect = (option: string) => {
    setSelectedOption(option);
    setShowCustomInput(false);
  };

  const handleConfirm = () => {
    if (selectedOption) {
      setIsCollapsed(true);
      onSubmitOption?.(selectedOption);
    }
  };

  const handleCustomSubmit = () => {
    if (customInput.trim()) {
      setIsCollapsed(true);
      onSubmitOption?.(customInput.trim());
    }
  };

  const handleDismiss = () => {
    setIsCollapsed(true);
  };

  // If it's an error message, show a cleaner version
  const displayContent = isError
    ? t.clarification.parseError
    : baseContent;

  const hasOptions = options.length > 0;
  const canSubmit =
    Boolean(selectedOption) || Boolean(showCustomInput && customInput.trim());

  return (
    <div
      className={cn(
        "bg-card border rounded-lg shadow-sm overflow-hidden",
        isError ? "border-amber-200 dark:border-amber-800" : "border-border",
        className
      )}
    >
      {/* Header */}
      <div
        className={cn(
          "flex items-center justify-between px-4 py-3 border-b",
          isError
            ? "bg-amber-50 dark:bg-amber-950/30 border-amber-200 dark:border-amber-800"
            : "bg-muted/50 border-border"
        )}
      >
        <div className="flex items-center gap-2">
          {isError ? (
            <AlertTriangle className="h-4 w-4 text-amber-600 dark:text-amber-400" />
          ) : (
            <HelpCircle className="h-4 w-4 text-muted-foreground" />
          )}
          <span className="font-medium text-sm">
            {isError ? t.clarification.parseError : t.clarification.confirmTitle}
          </span>
        </div>
        <div className="flex items-center gap-1">
          <Button
            variant="ghost"
            size="icon"
            className="h-6 w-6"
            onClick={() => setIsCollapsed(!isCollapsed)}
          >
            <ChevronDown
              className={cn(
                "h-4 w-4 transition-transform",
                isCollapsed && "rotate-180"
              )}
            />
          </Button>
          <Button
            variant="ghost"
            size="icon"
            className="h-6 w-6"
            onClick={handleDismiss}
          >
            <X className="h-3.5 w-3.5" />
          </Button>
        </div>
      </div>

      {!isCollapsed && (
        <div className="p-4">
          {/* Question content */}
          <div className="mb-5">
            <MarkdownContent
              content={displayContent}
              isLoading={isLoading}
              rehypePlugins={rehypePlugins}
              className="text-foreground"
            />
          </div>

          {/* Options */}
          {hasOptions && (
            <div className="mb-4">
              <div className="flex flex-col gap-2">
                {options.map((option, index) => (
                  <button
                    key={index}
                    onClick={() => handleOptionSelect(option)}
                    disabled={isLoading}
                    className={cn(
                      "flex items-start gap-3 p-3.5 rounded-lg text-left transition-all duration-200 border",
                      "hover:bg-muted/60 hover:border-muted-foreground/20",
                      selectedOption === option &&
                        "bg-primary/10 border-primary/40 shadow-sm",
                      selectedOption !== option && "border-transparent bg-muted/30",
                      isLoading && "opacity-50 cursor-not-allowed"
                    )}
                  >
                    <div
                      className={cn(
                        "mt-0.5 h-4 w-4 rounded-full border-2 flex items-center justify-center shrink-0 transition-colors",
                        selectedOption === option
                          ? "border-primary bg-primary"
                          : "border-muted-foreground/40"
                      )}
                    >
                      {selectedOption === option && (
                        <div className="h-1.5 w-1.5 rounded-full bg-primary-foreground" />
                      )}
                    </div>
                    <span className="text-sm leading-relaxed">{option}</span>
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* Custom input toggle */}
          {!showCustomInput && (
            <button
              onClick={() => {
                setShowCustomInput(true);
                setSelectedOption(null);
              }}
              disabled={isLoading}
              className={cn(
                "flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground transition-colors mb-3",
                isLoading && "opacity-50 cursor-not-allowed"
              )}
            >
              <MessageSquarePlus className="h-3.5 w-3.5" />
              <span>{t.clarification.customReply}</span>
            </button>
          )}

          {/* Custom input area */}
          {showCustomInput && (
            <div className="mb-4">
              <textarea
                value={customInput}
                onChange={(e) => setCustomInput(e.target.value)}
                placeholder={t.clarification.customReplyPlaceholder}
                disabled={isLoading}
                className={cn(
                  "w-full min-h-[80px] p-3 rounded-lg border bg-background text-sm resize-y",
                  "focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary/40",
                  "placeholder:text-muted-foreground/60",
                  isLoading && "opacity-50 cursor-not-allowed"
                )}
              />
            </div>
          )}

          {/* Action buttons */}
          <div className="flex justify-end gap-2">
            {(hasOptions || showCustomInput) && (
              <Button
                variant="outline"
                size="sm"
                onClick={handleDismiss}
                disabled={isLoading}
              >
                {t.common.cancel}
              </Button>
            )}
            {(hasOptions || showCustomInput) && (
              <Button
                onClick={showCustomInput ? handleCustomSubmit : handleConfirm}
                disabled={!canSubmit || isLoading}
                size="sm"
              >
                {t.clarification.confirm}
              </Button>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
