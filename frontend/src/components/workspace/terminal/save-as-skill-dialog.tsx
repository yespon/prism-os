"use client";

import { BookmarkIcon, Loader2Icon, SparklesIcon, FileTextIcon, GitCompareIcon, CheckIcon } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { MarkdownContent } from "@/components/workspace/messages/markdown-content";
import { SkillCreationInspection } from "@/components/workspace/skills/skill-creation-inspection";
import { summarizeDiagnosis, createPersonalSkill } from "@/core/skills/api";
import { useSkillImportContext } from "@/core/skills/import-context";
import { SkillMutationError, skillMutationMessage } from "@/core/skills/mutations";
import type { ToolCallSummary } from "@/core/skills/type";
import type { TerminalMessage } from "@/core/terminal-agent/message-types";

/**
 * Extracts terminal session context into a format suitable for Skill summarization.
 * Converts message history + tool calls into a plain-text diagnosis narrative.
 */
export function extractTerminalSession(messages: TerminalMessage[]): {
  title: string;
  diagnosisText: string;
  diagnosisSteps: string[];
  toolCallsSummary: ToolCallSummary[];
} {
  const steps: string[] = [];
  const toolSummaries: ToolCallSummary[] = [];
  const parts: string[] = [];

  for (const m of messages) {
    const role = m.role ?? m.type;
    const content = typeof m.content === 'string' ? m.content : '';

    // Collect AI reasoning text
    if (role === 'assistant' && content) {
      parts.push(content);
    }

    // Collect user input
    if (role === 'user' && content && !content.startsWith('[SYSTEM_INTERNAL]')) {
      steps.push(`用户: ${content.slice(0, 100)}`);
    }

    // Collect tool call summaries from parts
    if (m.parts && Array.isArray(m.parts)) {
      for (const p of m.parts) {
        const command = p.input?.command;
        if (p.toolName === 'execute_command' && typeof command === 'string') {
          steps.push(`执行命令: ${command}`);
          toolSummaries.push({
            tool: 'execute_command',
            description: command.slice(0, 80),
          });
        } else if (p.toolName && p.toolName !== 'execute_command') {
          steps.push(`工具调用: ${p.toolName}`);
          toolSummaries.push({
            tool: p.toolName,
            description: p.input ? JSON.stringify(p.input).slice(0, 80) : '',
          });
        }
      }
    }
  }

  // Derive a title from the first user message
  const firstUserMsg = messages.find(m => (m.role ?? m.type) === 'user');
  const title = firstUserMsg
    ? (typeof firstUserMsg.content === 'string' ? firstUserMsg.content : '').slice(0, 60).replace(/\\n/g, ' ')
    : '终端排查会话';

  return {
    title,
    diagnosisText: parts.join('\n\n'),
    diagnosisSteps: steps,
    toolCallsSummary: toolSummaries,
  };
}

/**
 * Normalize a skill name to hyphen-case (lowercase, digits, hyphens only).
 * Converts underscores, spaces, and uppercase to valid hyphen-case.
 */
function normalizeSkillName(raw: string): string {
  return raw
    .toLowerCase()
    .replace(/[\s_]+/g, '-')
    .replace(/[^a-z0-9-]/g, '')
    .replace(/--+/g, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, 64) || 'terminal-skill';
}

interface Props {
  sessionTitle?: string;
  diagnosisText: string;
  diagnosisSteps?: string[];
  toolCallsSummary?: ToolCallSummary[];
}

type Stage = "trigger" | "refining" | "preview" | "saving";

export function SaveAsSkillDialog({
  sessionTitle = "终端排查会话",
  diagnosisText,
  diagnosisSteps = [],
  toolCallsSummary = [],
}: Props) {
  const creationContext = useSkillImportContext();
  const creationIdentity = useRef(creationContext.key);
  creationIdentity.current = creationContext.key;
  const creationGeneration = useRef(0);
  const creationBusy = useRef(false);
  const [creationUnknown, setCreationUnknown] = useState(false);
  const [creationOperation, setCreationOperation] = useState<string | undefined>();
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [stage, setStage] = useState<Stage>("trigger");
  const [error, setError] = useState<string | null>(null);

  // AI refined result
  const [refinedName, setRefinedName] = useState("");
  const [refinedDescription, setRefinedDescription] = useState("");
  const [refinedInstructions, setRefinedInstructions] = useState("");
  const [refinedTools, setRefinedTools] = useState<string[]>([]);
  const [refinedCategory, setRefinedCategory] = useState("custom");

  // Editable fields
  const [editedName, setEditedName] = useState("");
  const [editedDescription, setEditedDescription] = useState("");

  useEffect(() => {creationGeneration.current += 1; creationBusy.current = false; setOpen(false); setStage("trigger"); setCreationUnknown(false);}, [creationContext.key]);

  const handleOpenChange = (newOpen: boolean) => {
    creationGeneration.current += 1;
    creationBusy.current = false;
    setCreationUnknown(false);
    setCreationOperation(undefined);
    if (!newOpen) {
      // Reset state when closing
      setStage("trigger");
      setError(null);
    }
    setOpen(newOpen);
  };

  const handleStartRefine = async () => {
    if (creationUnknown || !creationContext.isCurrent()) return;
    const owner = creationContext.key;
    const generation = ++creationGeneration.current;
    const current = () => creationIdentity.current === owner && creationGeneration.current === generation && creationContext.isCurrent();
    setStage("refining");
    setError(null);

    try {
      const result = await summarizeDiagnosis({
        incident_title: sessionTitle || null,
        diagnosis_result: diagnosisText,
        diagnosis_steps: diagnosisSteps.length > 0 ? diagnosisSteps : undefined,
        tool_calls_summary: toolCallsSummary.length > 0 ? toolCallsSummary : undefined,
      }, {isCurrent: current});
      if (!current()) return;

      // Normalize the AI-suggested name to valid hyphen-case
      const safeName = normalizeSkillName(result.suggested_name);
      setRefinedName(safeName);
      setRefinedDescription(result.suggested_description);
      setRefinedInstructions(result.instructions);
      setRefinedTools(result.suggested_tools);
      setRefinedCategory(result.suggested_category);

      setEditedName(safeName);
      setEditedDescription(result.suggested_description);

      setStage("preview");
    } catch (err) {
      if (!current()) return;
      setError(err instanceof Error ? err.message : "AI 提炼失败");
      setStage("trigger");
    }
  };

  const handleSave = async () => {
    if (creationUnknown || creationBusy.current || !creationContext.isCurrent()) return;
    const owner = creationContext.key;
    const generation = creationGeneration.current;
    const current = () => creationIdentity.current === owner && creationGeneration.current === generation && creationContext.isCurrent();
    creationBusy.current = true;
    setStage("saving");
    setError(null);

    // Normalize name to valid hyphen-case before saving
    const rawName = editedName || refinedName || 'terminal-skill';
    const name = normalizeSkillName(rawName);
    const description = editedDescription || refinedDescription || 'Skill created from terminal session';

    try {
      await createPersonalSkill({
        name,
        description,
        instructions: refinedInstructions,
        enabled: true,
      }, {isCurrent: current});
      if (!current()) return;

      toast.success("Skill 已创建，可在 Skills Plaza 的「我的 Skill」中查看");
      setOpen(false);
      // Redirect to Skills Plaza (personal skill detail page doesn't exist yet)
      router.push("/workspace/skills?filter=personal");
    } catch (err) {
      if (!current()) return;
      if (err instanceof TypeError || (err instanceof SkillMutationError && (err.inspectionRequired || err.status === 409))) {setCreationUnknown(true); if (err instanceof SkillMutationError) setCreationOperation(err.operationId);}
      setError(skillMutationMessage(err));
      setStage("preview");
    } finally {if (current()) creationBusy.current = false;}
  };

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogTrigger asChild>
        <Button
          size="sm"
          variant="outline"
          className="gap-1.5 h-8 text-xs font-semibold border-emerald-200 text-emerald-700 hover:bg-emerald-50 hover:text-emerald-800 dark:border-emerald-900 dark:text-emerald-400 dark:hover:bg-emerald-950/30"
        >
          <BookmarkIcon className="h-3.5 w-3.5" />
          存为 Skill
        </Button>
      </DialogTrigger>

      <DialogContent className="sm:max-w-2xl max-h-[90vh] overflow-hidden flex flex-col">
        {creationUnknown && <SkillCreationInspection scope="personal" operationId={creationOperation} />}
        {/* Stage: Refining (loading) */}
        {stage === "refining" && (
          <div className="flex flex-col items-center justify-center py-16 space-y-6">
            <div className="relative">
              <div className="w-16 h-16 rounded-2xl bg-gradient-to-br from-emerald-400 to-indigo-500 animate-pulse flex items-center justify-center">
                <SparklesIcon className="h-8 w-8 text-white" />
              </div>
              <div className="absolute -bottom-1 -right-1 w-6 h-6 rounded-full bg-white dark:bg-zinc-900 flex items-center justify-center">
                <Loader2Icon className="h-4 w-4 text-emerald-500 animate-spin" />
              </div>
            </div>
            <div className="text-center space-y-2">
              <DialogTitle className="text-lg font-bold bg-gradient-to-r from-emerald-600 to-indigo-600 bg-clip-text text-transparent">
                AI 正在提炼排查经验
              </DialogTitle>
              <DialogDescription className="text-sm max-w-sm">
                正在分析排查过程，提取通用 SOP，去除实例信息，生成可复用的 Skill 指令...
              </DialogDescription>
            </div>
            <div className="flex gap-1.5">
              <span className="w-2 h-2 rounded-full bg-emerald-400 animate-bounce" style={{ animationDelay: "0ms" }} />
              <span className="w-2 h-2 rounded-full bg-emerald-400 animate-bounce" style={{ animationDelay: "150ms" }} />
              <span className="w-2 h-2 rounded-full bg-emerald-400 animate-bounce" style={{ animationDelay: "300ms" }} />
            </div>
          </div>
        )}

        {/* Stage: Preview (three tabs) or Saving */}
        {(stage === "preview" || stage === "saving") && (
          <>
            <DialogHeader>
              <DialogTitle className="flex items-center gap-2">
                <SparklesIcon className="h-5 w-5 text-emerald-500" />
                AI 提炼结果预览
              </DialogTitle>
              <DialogDescription>
                AI 已将排查经验提炼为结构化 Skill。你可以直接保存或修改后保存。
              </DialogDescription>
            </DialogHeader>

            <div className="space-y-4 mt-2">
              {/* Editable name & description */}
              <div className="grid grid-cols-1 gap-3">
                <div className="space-y-1.5">
                  <label className="text-xs font-medium">Skill 名称</label>
                  <div className="flex items-center gap-2">
                    <Input
                      value={editedName}
                      onChange={(e) => setEditedName(e.target.value)}
                      className="flex-1 h-9 text-sm font-mono"
                    />
                    {refinedTools.length > 0 && (
                      <div className="flex gap-1 shrink-0">
                        {refinedTools.slice(0, 3).map((t) => (
                          <Badge key={t} variant="secondary" className="text-[10px] h-5 px-1.5">
                            {t}
                          </Badge>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
                <div className="space-y-1.5">
                  <label className="text-xs font-medium">描述</label>
                  <Input
                    value={editedDescription}
                    onChange={(e) => setEditedDescription(e.target.value)}
                    className="h-9 text-sm"
                  />
                </div>
              </div>

              {/* Three-tab preview */}
              <Tabs defaultValue="refined" className="w-full">
                <TabsList className="w-full grid grid-cols-3 h-9">
                  <TabsTrigger value="refined" className="text-xs gap-1.5">
                    <SparklesIcon className="h-3 w-3" />
                    AI 提炼
                  </TabsTrigger>
                  <TabsTrigger value="original" className="text-xs gap-1.5">
                    <FileTextIcon className="h-3 w-3" />
                    原始排查
                  </TabsTrigger>
                  <TabsTrigger value="diff" className="text-xs gap-1.5">
                    <GitCompareIcon className="h-3 w-3" />
                    差异对比
                  </TabsTrigger>
                </TabsList>

                <TabsContent value="refined" className="mt-3 max-h-[40vh] overflow-y-auto">
                  <div className="rounded-lg border border-emerald-100 dark:border-emerald-900/50 bg-emerald-50/30 dark:bg-emerald-950/10 p-4">
                    <div className="text-sm text-zinc-700 dark:text-zinc-300 leading-relaxed">
                      <MarkdownContent content={refinedInstructions} isLoading={false} rehypePlugins={null} />
                    </div>
                  </div>
                </TabsContent>

                <TabsContent value="original" className="mt-3 max-h-[40vh] overflow-y-auto">
                  <div className="rounded-lg border border-zinc-200 dark:border-zinc-800 bg-zinc-50/30 dark:bg-zinc-900/10 p-4">
                    <div className="text-sm text-zinc-600 dark:text-zinc-400 leading-relaxed whitespace-pre-wrap">
                      {diagnosisText}
                    </div>
                  </div>
                </TabsContent>

                <TabsContent value="diff" className="mt-3 max-h-[40vh] overflow-y-auto">
                  <div className="rounded-lg border border-zinc-200 dark:border-zinc-800 bg-zinc-50/30 dark:bg-zinc-900/10 p-4 space-y-3">
                    <div className="space-y-1.5">
                      <p className="text-xs font-semibold text-emerald-600 dark:text-emerald-400">
                        + 新增结构
                      </p>
                      <p className="text-xs text-zinc-500 dark:text-zinc-400 leading-relaxed">
                        AI 增加了适用场景、排查步骤、关键检查点、常见根因、修复建议和参考命令等结构化章节，使排查经验更容易被其他 Agent 复用。
                      </p>
                    </div>
                    <div className="space-y-1.5">
                      <p className="text-xs font-semibold text-amber-600 dark:text-amber-400">
                        - 去除实例信息
                      </p>
                      <p className="text-xs text-zinc-500 dark:text-zinc-400 leading-relaxed">
                        AI 移除了排查过程中具体的 Pod 名称、IP 地址、时间戳、具体数值等实例信息，将其替换为通用占位符或参数化描述。
                      </p>
                    </div>
                    <div className="space-y-1.5">
                      <p className="text-xs font-semibold text-indigo-600 dark:text-indigo-400">
                        ~ 保留领域知识
                      </p>
                      <p className="text-xs text-zinc-500 dark:text-zinc-400 leading-relaxed">
                        关键的检查命令、排查思路、根因分类和阈值建议被完整保留，确保了 Skill 的实用性。
                      </p>
                    </div>
                    {refinedTools.length > 0 && (
                      <div className="space-y-1.5">
                        <p className="text-xs font-semibold text-zinc-600 dark:text-zinc-400">
                          🔧 建议绑定工具
                        </p>
                        <div className="flex gap-1 flex-wrap">
                          {refinedTools.map((t) => (
                            <Badge key={t} variant="outline" className="text-[10px]">
                              {t}
                            </Badge>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                </TabsContent>
              </Tabs>

              {/* Error message */}
              {error && (
                <div className="rounded-lg border border-rose-200 dark:border-rose-900/50 bg-rose-50 dark:bg-rose-950/10 p-3">
                  <p className="text-xs text-rose-600 dark:text-rose-400">{error}</p>
                </div>
              )}
            </div>

            {/* Action buttons */}
            <div className="flex items-center justify-between pt-2 border-t border-zinc-100 dark:border-zinc-800">
              <div className="flex items-center gap-2">
                <Badge variant="outline" className="text-[10px] gap-1">
                  <CheckIcon className="h-3 w-3" />
                  分类: {refinedCategory}
                </Badge>
              </div>
              <div className="flex gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => {
                    setStage("trigger");
                    setOpen(false);
                  }}
                  disabled={stage === "saving" || creationUnknown}
                >
                  取消
                </Button>
                <Button
                  size="sm"
                  onClick={handleSave}
                  disabled={stage === "saving" || creationUnknown}
                  className="bg-emerald-600 hover:bg-emerald-700 text-white gap-1.5"
                >
                  {stage === "saving" ? (
                    <>
                      <Loader2Icon className="h-3.5 w-3.5 animate-spin" />
                      保存中...
                    </>
                  ) : (
                    <>
                      <BookmarkIcon className="h-3.5 w-3.5" />
                      保存为 Skill
                    </>
                  )}
                </Button>
              </div>
            </div>
          </>
        )}

        {/* Stage: Trigger (initial) */}
        {stage === "trigger" && (
          <>
            <DialogHeader>
              <DialogTitle>保存为可复用 Skill</DialogTitle>
              <DialogDescription>
                将本次排查经验保存为 Skill。AI 会自动提炼排查过程，生成结构化的 SOP 指令，供后续类似告警或排查复用。
              </DialogDescription>
            </DialogHeader>

            <div className="space-y-4 py-4">
              <div className="rounded-lg border border-emerald-100 dark:border-emerald-900/50 bg-emerald-50/30 dark:bg-emerald-950/10 p-4 space-y-2">
                <p className="text-xs font-semibold text-emerald-700 dark:text-emerald-400 flex items-center gap-1.5">
                  <SparklesIcon className="h-3.5 w-3.5" />
                  AI 提炼流程
                </p>
                <ul className="space-y-1.5">
                  <li className="text-xs text-zinc-600 dark:text-zinc-400 flex items-start gap-2">
                    <span className="text-emerald-500 mt-0.5">1.</span>
                    分析排查步骤，提取通用 SOP 流程
                  </li>
                  <li className="text-xs text-zinc-600 dark:text-zinc-400 flex items-start gap-2">
                    <span className="text-emerald-500 mt-0.5">2.</span>
                    去除实例信息（IP、Pod、时间戳等），保留领域知识
                  </li>
                  <li className="text-xs text-zinc-600 dark:text-zinc-400 flex items-start gap-2">
                    <span className="text-emerald-500 mt-0.5">3.</span>
                    生成结构化指令，包含排查步骤、检查点、根因和修复建议
                  </li>
                </ul>
              </div>

              {error && (
                <div className="rounded-lg border border-rose-200 dark:border-rose-900/50 bg-rose-50 dark:bg-rose-950/10 p-3">
                  <p className="text-xs text-rose-600 dark:text-rose-400">{error}</p>
                </div>
              )}
            </div>

            <div className="flex justify-end gap-2">
              <Button variant="outline" size="sm" onClick={() => handleOpenChange(false)}>
                取消
              </Button>
              <Button
                size="sm"
                onClick={handleStartRefine}
                className="bg-gradient-to-r from-emerald-600 to-indigo-600 hover:from-emerald-700 hover:to-indigo-700 text-white gap-1.5"
              >
                <SparklesIcon className="h-3.5 w-3.5" />
                开始 AI 提炼
              </Button>
            </div>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}
