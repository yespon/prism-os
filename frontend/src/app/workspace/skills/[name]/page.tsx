"use client";

import {
  ArrowLeft,
  Bot,
  Save,
  Sparkles,
  Loader2,
} from "lucide-react";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { useEffect, useRef, useState, useMemo } from "react";
import { toast } from "sonner";
import { v4 as uuidv4 } from "uuid";


import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { MarkdownContent } from "@/components/workspace/messages/markdown-content";
import { useSkillQueryIdentity } from "@/core/skills/query-identity";
import { useAvailableModels } from "@/core/models/hooks";
import {
  getSkillDetail,
  patchTenantSkill,
  patchPersonalSkill,
  createPersonalSkill,
  generateInstructions,
} from "@/core/skills/api";
import type { SkillDetail } from "@/core/skills/type";
import type { TerminalMessagePart, TerminalToolCall } from "@/core/terminal-agent/message-types";
import { useTerminalAgent } from "@/core/terminal-agent/useTerminalAgent";

export default function SkillDetailPage() {
  const identity = useSkillQueryIdentity();
  const params = useParams();
  const search = useSearchParams();
  return <SkillDetailContent key={JSON.stringify([identity.key, params.name, search.get("scope"), search.get("resource_id")])} />;
}

function SkillDetailContent() {
  const params = useParams();
  const router = useRouter();
  const skillName = params.name as string;
  const identity = useSkillQueryIdentity();
  const search = useSearchParams();
  const scope = search.get("scope") ?? undefined;
  const resourceId = search.get("resource_id") ?? undefined;
  const contextKey = JSON.stringify([identity.key, skillName, scope, resourceId]);
  const liveContext = useRef(contextKey);
  liveContext.current = contextKey;
  const [loadedContext, setLoadedContext] = useState("");
  const isNew = skillName === "new";

  const [skill, setSkill] = useState<SkillDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [aiLoading, setAiLoading] = useState(false);

  const { models: availableModels } = useAvailableModels();
  const [selectedModel, setSelectedModel] = useState("gpt-4o");

  // Edit state
  const [instructions, setInstructions] = useState("");
  const [description, setDescription] = useState("");
  const [boundToolsText, setBoundToolsText] = useState("");
  const [strategy, setStrategy] = useState("default");

  // For new skill creation
  const [newName, setNewName] = useState("");

  // AI generation prompt
  const [genPrompt, setGenPrompt] = useState("");
  const [dirty, setDirty] = useState(false);

  const sessionId = useMemo(() => uuidv4(), []);

  // Real test chat using the LangGraph backend agent
  const {
    messages,
    input: testInput,
    handleInputChange,
    handleSubmit,
    sendMessage,
    isLoading: testLoading,
  } = useTerminalAgent({
    taskId: sessionId,
    mode: "agent",
    modelName: selectedModel,
    skillInstructions: instructions,
    onExecuteCommand: async () => {
      toast.error("Sandbox 环境不支持手动执行终端命令");
      return "";
    },
  });

  const instructionsRef = useRef<HTMLTextAreaElement>(null);
  const mounted = useRef(true);
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);
  const currentView = () => mounted.current && liveContext.current === contextKey && identity.isCurrent();

  useEffect(() => {
    if (!skillName || !identity.identityReady) return;
    const controller = new AbortController();
    const valid = () => !controller.signal.aborted && liveContext.current === contextKey && identity.isCurrent();
    setSkill(null);
    setInstructions("");
    setDescription("");
    setDirty(false);

    if (isNew) {
      setSkill({
        name: "New Skill",
        scope: "personal",
        managed_by_current_user: true,
        description: "",
        instructions: "",
        bound_tools: [],
        enabled: true,
        category: "uncategorized",
        license: "private",
      } as unknown as SkillDetail);
      setLoading(false);
      setLoadedContext(contextKey);
      return () => controller.abort();
    }

    setLoading(true);
    getSkillDetail(skillName, {scope, resourceId, signal: controller.signal})
      .then((data) => {
        if (!valid()) return;
        setLoadedContext(contextKey);
        setSkill(data);
        setInstructions(data.instructions ?? "");
        setDescription(data.description ?? "");
        setBoundToolsText((data.bound_tools ?? []).join(", "));
        setStrategy(data.strategy ?? "default");
      })
      .catch(() => { if (valid()) toast.error("加载 Skill 详情失败"); })
      .finally(() => { if (valid()) setLoading(false); });
    return () => controller.abort();
  }, [contextKey, identity.identityReady, skillName, isNew, scope, resourceId]);

  const handleSave = async () => {
    if (!skill || loadedContext !== contextKey || !currentView()) return;
    if (isNew) {
      if (!newName.trim()) {
        toast.error("请输入 Skill 英文名称");
        return;
      }
      if (!/^[a-z0-9_]+$/.test(newName)) {
        toast.error("名称只能包含小写字母、数字和下划线");
        return;
      }
    }

    if (!description.trim()) {
      toast.error("请输入简短描述");
      return;
    }

    setSaving(true);
    try {
      if (isNew) {
        await createPersonalSkill({
          name: newName,
          description: description.trim() || "",
          instructions: instructions.trim() || null,
          enabled: true,
          bound_tools: boundToolsText.split(",").map((t) => t.trim()).filter(Boolean),
          strategy: strategy || null,
        });
        if (!currentView()) return;
        toast.success("创建成功");
        setDirty(false);
        router.push("/workspace/skills");
        return;
      }

      const payload = {
        description: description.trim() || null,
        instructions: instructions.trim() || null,
        bound_tools: boundToolsText
          .split(",")
          .map((t) => t.trim())
          .filter(Boolean),
        strategy: strategy || null,
      };

      if (skill.scope === "personal") {
        await patchPersonalSkill(skill.name, payload);
      } else {
        await patchTenantSkill(skill.name, payload);
      }

      if (!currentView()) return;
      setDirty(false);
      toast.success("保存成功");
      router.push("/workspace/skills");
    } catch (err) {
      if (currentView()) toast.error(err instanceof Error ? err.message : "保存失败");
    } finally {
      if (currentView()) setSaving(false);
    }
  };

  const handleAIGenerate = async () => {
    if (!currentView()) return;
    if (!genPrompt.trim()) {
      toast.error("请输入你想让 Skill 做什么");
      return;
    }
    setAiLoading(true);
    try {
      const result = await generateInstructions(genPrompt.trim(), selectedModel);
      if (!currentView()) return;
      setInstructions(result.instructions);
      setDirty(true);
      toast.success("AI 已生成 Instructions，请检查并调整");
    } catch (err) {
      if (currentView()) toast.error(err instanceof Error ? err.message : "生成失败");
    } finally {
      if (currentView()) setAiLoading(false);
    }
  };

  const handleTest = (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    if (!currentView() || !testInput.trim() || testLoading) return;
    void sendMessage({ text: testInput.trim() });
  };

  if (loading || !identity.identityReady || (skill !== null && loadedContext !== contextKey)) {
    return (
      <div className="flex size-full items-center justify-center">
        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (!skill) {
    return (
      <div className="flex size-full items-center justify-center text-muted-foreground">
        Skill 未找到
      </div>
    );
  }

  // User can edit if they manage it (either they are admin for tenant skills, or it's their personal skill)
  // Global skills are built-in and never editable.
  const canEdit = skill.managed_by_current_user && skill.scope !== "global";

  return (
    <div className="flex size-full flex-col bg-zinc-50/50 dark:bg-zinc-950/20 overflow-hidden animate-in fade-in duration-300">
      {/* Header */}
      <div className="flex shrink-0 items-center justify-between border-b px-6 py-4">
        <div className="flex items-center gap-3">
          <Button
            variant="ghost"
            size="icon"
            onClick={() => router.back()}
          >
            <ArrowLeft className="h-5 w-5" />
          </Button>
          <div>
            {isNew ? (
              <h1 className="text-xl font-semibold">新建 Skill</h1>
            ) : (
              <>
                <h1 className="text-xl font-semibold">{skill.name}</h1>
                <div className="mt-1 flex items-center gap-2 text-xs text-muted-foreground">
                  <Badge
                    variant="secondary"
                    className="text-[10px]"
                  >
                    v{skill.version ?? 1}
                  </Badge>
                  {skill.category && (
                    <span>{skill.category}</span>
                  )}
                  {skill.usage_count !== undefined && skill.usage_count > 0 && (
                    <span>· 使用 {skill.usage_count} 次</span>
                  )}
                </div>
              </>
            )}
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Select
            value={selectedModel}
            onValueChange={setSelectedModel}
            disabled={aiLoading || testLoading}
          >
            <SelectTrigger className="w-[180px] h-9">
              <SelectValue placeholder="选择模型" />
            </SelectTrigger>
            <SelectContent>
              {availableModels?.map((model) => (
                <SelectItem key={model.name} value={model.name}>
                  <div className="flex items-center gap-2">
                    <Sparkles className="h-3 w-3 text-muted-foreground" />
                    {model.name}
                  </div>
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Button
            variant="outline"
            onClick={handleSave}
            disabled={!canEdit || saving}
          >
            <Save className="mr-2 h-4 w-4" />
            {saving ? "保存中..." : "保存"}
          </Button>
        </div>
      </div>

      {/* Main content: left edit + right test */}
      <div className="flex flex-1 overflow-hidden p-6 gap-6">
        {/* Left panel — Instructions editor */}
        <div className="flex w-3/5 flex-col bg-card rounded-xl border shadow-sm overflow-hidden">
          {/* Header for Left Panel */}
          <div className="flex items-center gap-2 border-b px-4 py-3 bg-muted/30">
            <span className="text-sm font-medium">配置说明</span>
            <span className="text-[10px] text-muted-foreground ml-auto">
              编写 Skill 的核心逻辑和执行步骤
            </span>
          </div>

          <div className="flex-1 overflow-y-auto p-6 flex flex-col gap-6">
            {/* Name (New Mode) */}
            {isNew && (
              <div>
                <label className="text-sm font-medium">名称<span className="text-red-500 ml-1">*</span></label>
                <Input
                  value={newName}
                  onChange={e => { setNewName(e.target.value); setDirty(true); }}
                  placeholder="输入小写英文名称"
                  className="mt-1.5 font-semibold text-sm"
                />
                <span className="text-[10px] text-muted-foreground mt-1 block">仅限小写字母、数字、下划线</span>
              </div>
            )}

            {/* Description */}
            <div>
              <label className="text-sm font-medium">描述<span className="text-red-500 ml-1">*</span></label>
              <Input
                value={description}
                onChange={(e) => {
                  setDescription(e.target.value);
                  setDirty(true);
                }}
                placeholder="简短描述这个 Skill 做什么"
                disabled={!canEdit}
                className="mt-1.5"
              />
            </div>

          {/* Instructions Section */}
          <div className="flex-1 flex flex-col min-h-0 gap-3">
            <label className="text-sm font-medium flex items-center justify-between">
              <span>Instructions<span className="text-red-500 ml-1">*</span></span>
              {dirty && (
                <span className="text-[10px] text-amber-600">未保存</span>
              )}
            </label>

            {/* AI auto-generate panel */}
            <div className="rounded-lg border bg-card p-4 shrink-0">
              <div className="flex items-center gap-2 text-sm font-medium mb-2">
                <Sparkles className="h-4 w-4 text-primary" />
                AI 自动生成
              </div>
              <p className="text-xs text-muted-foreground mb-3">
                描述你想让 Agent 掌握什么能力，AI 会自动为你生成结构化的执行流与规则
              </p>
              <div className="flex gap-2">
                <Input
                  value={genPrompt}
                  onChange={(e) => setGenPrompt(e.target.value)}
                  placeholder='例如："帮我总结每周的研发工作周报" 或 "分析代码库并提供审查意见"'
                  className="flex-1"
                  disabled={!canEdit}
                />
                <Button
                  onClick={handleAIGenerate}
                  disabled={!canEdit || aiLoading}
                  size="sm"
                >
                  {aiLoading ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    "生成"
                  )}
                </Button>
              </div>
            </div>

            <Textarea
              ref={instructionsRef}
              value={instructions}
              onChange={(e) => {
                setInstructions(e.target.value);
                setDirty(true);
              }}
              placeholder={`## 目标\n\n### 第一阶段：准备工作\n1. 执行 ...\n2. 检查 ...\n\n### 第二阶段：核心执行\n1. ...\n`}
              className="flex-1 min-h-[300px] font-mono text-sm"
              disabled={!canEdit}
            />
          </div>
          </div>
        </div>

        {/* Right panel — Test chat */}
        <div className="flex w-2/5 flex-col bg-card rounded-xl border shadow-sm overflow-hidden">
          <div className="flex items-center gap-2 border-b px-4 py-3 bg-muted/30">
            <Bot className="h-4 w-4 text-primary" />
            <span className="text-sm font-medium">测试沙盒</span>
            <span className="text-[10px] text-muted-foreground ml-auto">
              使用当前配置的指令进行排练
            </span>
          </div>

          {/* Chat messages */}
          <div className="flex-1 overflow-y-auto p-4 space-y-4">
            {messages.length === 0 && (
              <div className="text-center text-sm text-muted-foreground mt-10">
                发送问题，例如：“帮我排查一下 192.168.1.1 上的 Pod 状态”
              </div>
            )}
            {messages.map((msg, idx) => {
              const role = msg.role ?? msg.type;
              const isUser = role === "user" || role === "human";
              let textContent = "";
              if (typeof msg.content === "string") textContent = msg.content;
              else if (Array.isArray(msg.content)) {
                textContent = msg.content.filter((p: TerminalMessagePart) => p.type === "text").map((p) => p.text ?? "").join("\n");
              }

              // Find tools if any
              const toolCalls = Array.isArray(msg.tool_calls) ? msg.tool_calls : [];

              return (
                <div
                  key={msg.id ?? idx}
                  className={`flex flex-col gap-1 ${isUser ? "items-end" : "items-start"
                    }`}
                >
                  {isUser && textContent && (
                    <div className="max-w-[85%] rounded-2xl rounded-tr-sm bg-primary px-4 py-2 text-[13px] text-primary-foreground shadow-sm whitespace-pre-wrap">
                      {textContent}
                    </div>
                  )}

                  {!isUser && (
                    <div className="flex flex-col gap-2 max-w-[90%]">
                      {textContent && (
                        <div className="markdown-body text-[13px] text-zinc-800 leading-relaxed bg-muted/30 px-4 py-3 rounded-2xl rounded-tl-sm border shadow-sm">
                          <MarkdownContent content={textContent} isLoading={false} rehypePlugins={null} />
                        </div>
                      )}
                      {toolCalls.map((tc: TerminalToolCall) => (
                        <div key={tc.id ?? tc.name ?? "tool"} className="text-[11px] text-muted-foreground font-mono bg-muted px-2 py-1 rounded">
                          $ {tc.name ?? "tool"}(...)
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              );
            })}

            {testLoading && (
              <div className="flex justify-start">
                <div className="max-w-[80%] flex items-center gap-2 rounded-lg bg-muted px-3 py-2 text-sm text-muted-foreground">
                  <Loader2 className="h-4 w-4 animate-spin" />
                  Agent 思考中...
                </div>
              </div>
            )}
          </div>

          <div className="border-t p-3">
            <form onSubmit={handleTest} className="flex gap-2">
              <Input
                value={testInput}
                onChange={handleInputChange}
                placeholder='输入测试告警，例如："K8s Pod CPU 高"'
                className="flex-1"
              />
              <Button type="submit" disabled={testLoading || !testInput.trim()}>
                发送
              </Button>
            </form>
          </div>
        </div>
      </div>
    </div>
  );
}
