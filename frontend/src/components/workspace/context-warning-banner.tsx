"use client";

import type { Message } from "@langchain/langgraph-sdk";
import { AlertTriangle, ArrowRight, SquarePen } from "lucide-react";
import { useMemo } from "react";

import { Button } from "@/components/ui/button";
import { useI18n } from "@/core/i18n/hooks";
import { accumulateUsage } from "@/core/messages/usage";
import { cn } from "@/lib/utils";

/** Hard-cap fraction matching backend HARD_CAP_FRACTION */
const HARD_CAP_FRACTION = 0.80;

interface ContextWarningBannerProps {
  messages: Message[];
  modelMaxTokens?: number;
  onNewChat?: () => void;
  className?: string;
}

/**
 * ContextWarningBanner displays a warning when the conversation context
 * exceeds 80% of the model's capacity, with a call-to-action to start
 * a new chat session.
 *
 * Design rationale:
 * - Yellow/amber warning style: signals caution, not error
 * - Compact banner: doesn't interrupt the conversation flow
 * - Actionable: provides a direct "New Session" button
 * - Auto-dismisses: disappears when context drops below threshold
 */
export function ContextWarningBanner({
  messages,
  modelMaxTokens,
  onNewChat,
  className,
}: ContextWarningBannerProps) {
  const { t } = useI18n();

  const shouldWarn = useMemo(() => {
    if (!modelMaxTokens || modelMaxTokens <= 0) return false;

    const usage = accumulateUsage(messages);
    if (!usage || usage.totalTokens === 0) return false;

    const hardCap = Math.round(modelMaxTokens * HARD_CAP_FRACTION);
    return usage.totalTokens >= hardCap;
  }, [messages, modelMaxTokens]);

  if (!shouldWarn) return null;

  return (
    <div
      className={cn(
        "mx-auto w-full max-w-5xl shrink-0 animate-in fade-in slide-in-from-top-2 duration-300",
        className,
      )}
    >
      <div
        className={cn(
          "flex items-center justify-between gap-3 rounded-xl border px-4 py-2.5",
          "border-amber-200/80 dark:border-amber-800/60",
          "bg-amber-50/60 dark:bg-amber-950/20",
          "backdrop-blur-sm",
        )}
      >
        <div className="flex items-center gap-2.5 min-w-0">
          <AlertTriangle className="size-4 shrink-0 text-amber-500" />
          <span className="text-xs font-medium text-amber-800 dark:text-amber-200 truncate">
            {t.summaryStatus?.contextWarning ?? "上下文使用率较高，建议开始新会话以保持最佳性能"}
          </span>
        </div>
        {onNewChat && (
          <Button
            variant="outline"
            size="sm"
            className="h-7 shrink-0 gap-1.5 rounded-lg border-amber-300/60 bg-white/60 dark:bg-amber-950/30 text-amber-700 dark:text-amber-300 hover:bg-amber-100 dark:hover:bg-amber-900/40 text-xs"
            onClick={onNewChat}
          >
            <SquarePen className="size-3.5" />
            <span>{t.chatHeader?.newSession ?? "新会话"}</span>
            <ArrowRight className="size-3" />
          </Button>
        )}
      </div>
    </div>
  );
}
