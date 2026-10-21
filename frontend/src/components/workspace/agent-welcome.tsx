"use client";

import { usePromptInputController } from "@/components/ai-elements/prompt-input";
import { Button } from "@/components/ui/button";
import { type Agent } from "@/core/agents";
import { cn } from "@/lib/utils";

import { AgentAvatar } from "./agents/agent-avatar";

export function AgentWelcome({
  className,
  agent,
  agentName,
  disabled = false,
}: {
  className?: string;
  agent: Agent | null | undefined;
  agentName: string;
  disabled?: boolean;
}) {
  const { textInput } = usePromptInputController();
  const displayName = agent?.name ?? agentName;
  const description = agent?.description;

  return (
    <div
      className={cn(
        "mx-auto flex w-full flex-col items-center justify-center gap-2 px-8 py-4 text-center",
        className,
      )}
    >
      <div className="bg-primary/10 flex h-12 w-12 items-center justify-center rounded-full">
        <AgentAvatar avatarId={agent?.presentation?.avatar_id} className="h-10 w-10" />
      </div>
      <div className="text-2xl font-bold">{displayName}</div>
      {agent?.presentation?.welcome_message && <p className="max-w-sm whitespace-pre-wrap text-sm">{agent.presentation.welcome_message}</p>}
      {!!agent?.presentation?.quick_prompts?.length && <div className="pointer-events-auto flex flex-wrap justify-center gap-2">{agent.presentation.quick_prompts.map((item, index) => <Button key={index} type="button" variant="outline" disabled={disabled} title={item.description} onClick={() => textInput.setInput(item.prompt)}>{item.title}</Button>)}</div>}
      {description && (
        <p className="text-muted-foreground max-w-sm text-sm">{description}</p>
      )}
    </div>
  );
}
