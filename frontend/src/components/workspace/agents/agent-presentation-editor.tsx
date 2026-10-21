"use client";

import { useEffect, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import {
  loadAgentAvatars,
  loadPersonalityQuestions,
  scorePersonality,
  type AgentAvatar as AgentAvatarOption,
  type PersonalityQuestion,
  type PersonalityResult,
} from "@/core/agents/catalog";
import { useTenantKey } from "@/core/agents/hooks";
import type { AgentQuickPrompt } from "@/core/agents/types";

import { AgentAvatar } from "./agent-avatar";

interface Props {
  quickPrompts: AgentQuickPrompt[];
  onQuickPrompts: (prompts: AgentQuickPrompt[]) => void;
  open: boolean;
  locale: "zh" | "en";
  welcomeMessage: string;
  avatarId: string;
  onWelcome: (message: string) => void;
  onAvatar: (id: string) => void;
  onPersona: (code: string) => void;
}

export function AgentPresentationEditor(props: Props) {
  const {
    open,
    locale,
    welcomeMessage,
    avatarId,
    onWelcome,
    onAvatar,
    onPersona,
    quickPrompts,
    onQuickPrompts,
  } = props;
  const tenant = useTenantKey();
  // Remount all questionnaire state when the editing context changes.
  return (
    <PresentationFields
      key={`${tenant}:${locale}:${open}`}
      {...{
        open,
        locale,
        welcomeMessage,
        avatarId,
        onWelcome,
        onAvatar,
        onPersona,
        quickPrompts,
        onQuickPrompts,
      }}
    />
  );
}

function PresentationFields({
  open,
  locale,
  welcomeMessage,
  avatarId,
  onWelcome,
  onAvatar,
  onPersona,
  quickPrompts,
  onQuickPrompts,
}: Props) {
  const zh = locale === "zh";
  const [avatars, setAvatars] = useState<AgentAvatarOption[]>([]);
  const [questions, setQuestions] = useState<PersonalityQuestion[]>([]);
  const [answers, setAnswers] = useState<Record<string, "A" | "B">>({});
  const [result, setResult] = useState<PersonalityResult | null>(null);
  const [testing, setTesting] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [retry, setRetry] = useState(0);
  const scoreController = useRef<AbortController | null>(null);
  useEffect(() => {
    const request = new AbortController();
    if (open) {
      setError("");
      void Promise.all([
        loadAgentAvatars(request.signal),
        loadPersonalityQuestions(locale, request.signal),
      ])
        .then(([images, test]) => {
          if (!request.signal.aborted) {
            setAvatars(images.avatars);
            setQuestions(test.questions);
          }
        })
        .catch(() => {
          if (!request.signal.aborted)
            setError(
              zh
                ? "头像与测验暂时不可用。"
                : "Avatars and questionnaire unavailable.",
            );
        });
    }
    return () => {
      request.abort();
      scoreController.current?.abort();
    };
  }, [open, locale, retry, zh]);

  async function score() {
    scoreController.current?.abort();
    const request = new AbortController();
    scoreController.current = request;
    setBusy(true);
    setError("");
    try {
      const scored = await scorePersonality(answers, request.signal);
      if (!request.signal.aborted) setResult(scored);
    } catch {
      if (!request.signal.aborted)
        setError(
          zh
            ? "测验提交失败，请重试。"
            : "Could not score the questionnaire. Retry.",
        );
    } finally {
      if (!request.signal.aborted) setBusy(false);
    }
  }

  return (
    <section className="space-y-3 rounded-lg border p-3">
      <label className="block space-y-1 text-xs">
        <span>{zh ? "欢迎语" : "Welcome message"}</span>
        <Textarea
          aria-label={zh ? "欢迎语" : "Welcome message"}
          maxLength={2000}
          value={welcomeMessage}
          onChange={(event) => onWelcome(event.target.value)}
        />
      </label>
      <div className="flex items-center gap-3">
        <AgentAvatar avatarId={avatarId} />
        <label className="grow text-xs">
          {zh ? "头像" : "Avatar"}
          <select
            aria-label={zh ? "头像" : "Avatar"}
            className="bg-background mt-1 block w-full rounded border p-2"
            value={avatarId}
            onChange={(event) => onAvatar(event.target.value)}
          >
            <option value="">{zh ? "默认图标" : "Default icon"}</option>
            {avatarId && !avatars.some((item) => item.id === avatarId) && (
              <option value={avatarId}>{avatarId.split(":")[1]}</option>
            )}
            {avatars.map((item) => (
              <option key={item.id} value={item.id}>
                {item.label}
              </option>
            ))}
          </select>
        </label>
      </div>
      <div className="space-y-2 text-xs">
        <p>
          {zh
            ? "快捷提问（点击后填入聊天草稿）"
            : "Starter questions (fill the chat draft)"}
        </p>
        {quickPrompts.map((item, index) => (
          <div key={index} className="space-y-1 rounded border p-2">
            <input
              aria-label={`${zh ? "快捷提问标题" : "Starter title"} ${index + 1}`}
              className="bg-background w-full rounded border p-1"
              maxLength={100}
              value={item.title}
              onChange={(event) =>
                onQuickPrompts(
                  quickPrompts.map((old, at) =>
                    at === index ? { ...old, title: event.target.value } : old,
                  ),
                )
              }
            />
            <Textarea
              aria-label={`${zh ? "快捷提问内容" : "Starter question"} ${index + 1}`}
              maxLength={4000}
              value={item.prompt}
              onChange={(event) =>
                onQuickPrompts(
                  quickPrompts.map((old, at) =>
                    at === index ? { ...old, prompt: event.target.value } : old,
                  ),
                )
              }
            />
            <Button
              type="button"
              variant="ghost"
              onClick={() =>
                onQuickPrompts(quickPrompts.filter((_, at) => at !== index))
              }
            >
              {zh ? "移除" : "Remove"}
            </Button>
          </div>
        ))}
        <Button
          type="button"
          variant="outline"
          disabled={quickPrompts.length >= 32}
          onClick={() =>
            onQuickPrompts([
              ...quickPrompts,
              {
                title: zh ? "新提问" : "New question",
                prompt: zh ? "请帮助我…" : "Please help me…",
                description: "",
              },
            ])
          }
        >
          {zh ? "添加快捷提问" : "Add starter question"}
        </Button>
      </div>
      <Button
        type="button"
        variant="outline"
        disabled={!questions.length}
        onClick={() => {
          scoreController.current?.abort();
          setBusy(false);
          setTesting(!testing);
        }}
      >
        {zh
          ? testing
            ? "收起人格测验"
            : "通过测验选择人格"
          : testing
            ? "Close questionnaire"
            : "Choose personality with a questionnaire"}
      </Button>
      {testing && (
        <div className="space-y-3">
          <p className="text-muted-foreground text-xs">
            {zh
              ? "用于选择智能体的交流风格；完成后可确认应用到草稿。"
              : "Choose your agent’s communication style, then apply the result to the draft."}
          </p>
          <div className="max-h-64 space-y-3 overflow-auto">
            {questions.map((question) => (
              <fieldset key={question.id} className="space-y-1 text-xs">
                <legend>
                  {question.id}. {question.question}
                </legend>
                {(["A", "B"] as const).map((choice) => (
                  <label className="block" key={choice}>
                    <input
                      type="radio"
                      name={`personality-${question.id}`}
                      aria-label={`${question.id} ${choice}`}
                      checked={answers[String(question.id)] === choice}
                      disabled={busy}
                      onChange={() => {
                        setAnswers((previous) => ({
                          ...previous,
                          [question.id]: choice,
                        }));
                        setResult(null);
                      }}
                    />{" "}
                    {choice === "A" ? question.option_a : question.option_b}
                  </label>
                ))}
              </fieldset>
            ))}
          </div>
          <Button
            type="button"
            disabled={busy || Object.keys(answers).length !== questions.length}
            onClick={() => void score()}
          >
            {zh
              ? `查看结果 (${Object.keys(answers).length}/${questions.length})`
              : `See result (${Object.keys(answers).length}/${questions.length})`}
          </Button>
          {result && (
            <div role="status" className="space-y-2 text-xs">
              <p>
                {result.code} ·{" "}
                {Object.entries(result.dimensions)
                  .map(([axis, [pole, pct]]) => `${axis}: ${pole} ${pct}%`)
                  .join(" · ")}
              </p>
              <Button
                type="button"
                onClick={() => {
                  onPersona(result.code);
                  setTesting(false);
                }}
              >
                {zh ? "将此人格应用到草稿" : "Apply this personality to draft"}
              </Button>
            </div>
          )}
        </div>
      )}
      {error && (
        <div role="alert" className="text-destructive text-xs">
          {error}{" "}
          <Button
            type="button"
            variant="ghost"
            onClick={() => setRetry((value) => value + 1)}
          >
            {zh ? "重试" : "Retry"}
          </Button>
        </div>
      )}
    </section>
  );
}
