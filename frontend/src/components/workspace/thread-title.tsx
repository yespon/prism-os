"use client";

import type { BaseStream } from "@langchain/langgraph-sdk";
import { Pencil } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { useI18n } from "@/core/i18n/hooks";
import type { AgentThreadState } from "@/core/threads";
import { useRenameThread } from "@/core/threads/hooks";
import { cn } from "@/lib/utils";

import { useThreadChat } from "./chats";
import { FlipDisplay } from "./flip-display";

export function ThreadTitle({
  threadId,
  thread,
  className,
}: {
  className?: string;
  threadId: string;
  thread: BaseStream<AgentThreadState>;
}) {
  const { t } = useI18n();
  const { isNewThread } = useThreadChat();
  const { mutate: renameThread } = useRenameThread();

  const [isEditing, setIsEditing] = useState(false);
  const [editValue, setEditValue] = useState("");
  const [optimisticTitle, setOptimisticTitle] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const streamTitle = thread.values?.title;
  const resolvedTitle = streamTitle
    ? streamTitle
    : isNewThread
      ? t.pages.newChat
      : t.pages.untitled;
  const displayTitle = optimisticTitle ?? resolvedTitle;

  useEffect(() => {
    if (optimisticTitle && streamTitle === optimisticTitle) {
      setOptimisticTitle(null);
    }
  }, [streamTitle, optimisticTitle]);

  useEffect(() => {
    setOptimisticTitle(null);
  }, [threadId]);

  useEffect(() => {
    let _title = t.pages.untitled;

    if (optimisticTitle) {
      _title = optimisticTitle;
    } else if (thread.values?.title) {
      _title = thread.values.title;
    } else if (isNewThread) {
      _title = t.pages.newChat;
    }
    if (thread.isThreadLoading) {
      document.title = `Loading... - ${t.pages.appName}`;
    } else {
      document.title = `${_title} - ${t.pages.appName}`;
    }
  }, [
    optimisticTitle,
    isNewThread,
    t.pages.newChat,
    t.pages.untitled,
    t.pages.appName,
    thread.isThreadLoading,
    thread.values,
  ]);

  useEffect(() => {
    if (isEditing && inputRef.current) {
      inputRef.current.focus();
      inputRef.current.select();
    }
  }, [isEditing]);

  const handleStartEdit = () => {
    if (!threadId || threadId === "new") return;
    setEditValue(displayTitle);
    setIsEditing(true);
  };

  const handleSubmit = () => {
    const trimmed = editValue.trim();
    if (trimmed && trimmed !== displayTitle) {
      setOptimisticTitle(trimmed);
      renameThread({ threadId, title: trimmed });
    }
    setIsEditing(false);
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter") {
      handleSubmit();
    } else if (e.key === "Escape") {
      setIsEditing(false);
    }
  };

  if (isEditing) {
    return (
      <input
        ref={inputRef}
        type="text"
        value={editValue}
        onChange={(e) => setEditValue(e.target.value)}
        onBlur={handleSubmit}
        onKeyDown={handleKeyDown}
        className={cn(
          "bg-transparent outline-none border-b border-primary/40 pb-0.5",
          "text-[13px] font-medium tracking-tight",
          "min-w-[80px] max-w-[300px]",
          className,
        )}
      />
    );
  }

  const canEdit = threadId && threadId !== "new";

  return (
    <FlipDisplay uniqueKey={threadId}>
      <span
        onClick={canEdit ? handleStartEdit : undefined}
        className={cn(
          "inline-flex items-center gap-1.5",
          canEdit &&
            "cursor-pointer group/title hover:text-foreground transition-colors",
          className,
        )}
        title={canEdit ? t.chatHeader.clickToRename : undefined}
      >
        <span className="border-b border-dashed border-transparent group-hover/title:border-border/60 transition-colors pb-0.5">
          {displayTitle}
        </span>
        {canEdit && (
          <Pencil className="size-3 text-muted-foreground/0 group-hover/title:text-muted-foreground/50 transition-all" />
        )}
      </span>
    </FlipDisplay>
  );
}
