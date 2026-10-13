"use client";

import { BotIcon, XIcon, AlertCircleIcon, ChevronDown, SparklesIcon } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { useAgent, useSkills, useUpdateAgent } from "@/core/agents";
import type { UpdateAgentRequest } from "@/core/agents";
import { AgentMutationError } from "@/core/agents/api";
import { useDraftIsCurrent } from "@/core/agents/draft-scope";
import type { AgentQuickPrompt } from "@/core/agents/types";
import { useI18n } from "@/core/i18n/hooks";
import { useAvailableMcpConfig } from "@/core/mcp/hooks";
import { useAvailableModels } from "@/core/models/hooks";
import { isTenantAdminRole } from "@/core/permissions/scope";
import { useSkillImportContext } from "@/core/skills/import-context";
import { useCurrentTenant } from "@/core/tenants/hooks";
import { cn } from "@/lib/utils";

import { AgentPresentationEditor } from "./agent-presentation-editor";
import { AgentSkillSelection, type AgentSkillSelectionValue } from "./agent-skill-selection";
import { AgentTemplatePicker } from "./agent-template-picker";


interface EditAgentDialogProps {
  agentName: string | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSuccess?: () => void;
}

export function EditAgentDialog(props: EditAgentDialogProps) {
  const { key: tenant } = useSkillImportContext();
  const { locale } = useI18n();
  return <EditAgentDialogFields key={`${tenant}:${locale}:${props.open}:${props.agentName ?? ""}`} {...props} />;
}

function EditAgentDialogFields({ agentName, open, onOpenChange, onSuccess }: EditAgentDialogProps) {
  const { t, locale } = useI18n();
  const templateLocale = locale === "en-US" ? "en" : "zh";
  const isCurrent = useDraftIsCurrent();
  const [saveNeedsInspection, setSaveNeedsInspection] = useState(false);
  const [personaCode, setPersonaCode] = useState("");
  const [welcomeMessage, setWelcomeMessage] = useState("");
  const [avatarId, setAvatarId] = useState("");
  const [quickPrompts, setQuickPrompts] = useState<AgentQuickPrompt[]>([]);

  const { agent, isLoading } = useAgent(agentName ?? "");
  const { skills } = useSkills();
  const updateAgent = useUpdateAgent();
  const { rawArray: availableMcps, isLoading: isLoadingMcps } = useAvailableMcpConfig();
  const { models: availableModels, isLoading: isLoadingModels } = useAvailableModels();

  // Form states
  const [systemPrompt, setSystemPrompt] = useState("");
  const [description, setDescription] = useState("");
  const [selectedModel, setSelectedModel] = useState<string>("");
  const [skillSelection, setSkillSelection] = useState<AgentSkillSelectionValue>({mode:"all",resources:[]});
  const [selectionEdited, setSelectionEdited] = useState(false);
  const [legacyNames, setLegacyNames] = useState<string[]>([]);
  const [selectedSkills, setSelectedSkills] = useState<Set<string>>(new Set());
  const [selectedToolGroups, setSelectedToolGroups] = useState<Set<string>>(new Set());
  const [tags, setTags] = useState<string[]>([]);
  const [tagInput, setTagInput] = useState("");
  const [enabled, setEnabled] = useState(true);
  const [isShared, setIsShared] = useState(false);
  const [activeTab, setActiveTab] = useState<"mcp" | "custom" | "public">("mcp");

  const { data: currentTenant } = useCurrentTenant();
  const isTenantAdmin = isTenantAdminRole(currentTenant?.role);

  // Populate form when agent data loads
  useEffect(() => {
    if (agent && open) {
      setSystemPrompt(agent.base_system_prompt ?? agent.system_prompt ?? "");
      setPersonaCode(agent.presentation?.persona_mbti ?? "");
      setWelcomeMessage(agent.presentation?.welcome_message ?? "");
      setAvatarId(agent.presentation?.avatar_id ?? "");
      setQuickPrompts(agent.presentation?.quick_prompts ?? []);
      setDescription(agent.description ?? "");
      setSelectedModel(agent.model ?? "");
      setSelectedSkills(new Set(agent.skills ?? []));
      setSkillSelection({mode: agent.skill_binding_mode === "all" || (!agent.skill_binding_mode && !agent.skills.length) ? "all" : "selected",resources:agent.skill_resources ?? []});
      setSelectionEdited(false);
      setLegacyNames(agent.skill_binding_mode === "unresolved" || (!agent.skill_binding_mode && agent.skills.length > 0) ? agent.skills : []);
      setSelectedToolGroups(new Set(agent.tool_groups ?? []));
      setTags(agent.tags ?? []);
      setEnabled(agent.enabled);
      setIsShared(agent.is_shared ?? false);
      setActiveTab("mcp");
    }
  }, [agent, open]);

  // Group skills by category
  const skillsByCategory = skills.reduce(
    (acc, skill) => {
      const cat = skill.category || "other";
      acc[cat] ??= [];
      acc[cat].push(skill);
      return acc;
    },
    {} as Record<string, typeof skills>,
  );

  const toggleToolGroup = (groupName: string) => {
    const next = new Set(selectedToolGroups);
    if (next.has(groupName)) {
      next.delete(groupName);
    } else {
      next.add(groupName);
    }
    setSelectedToolGroups(next);
  };

  const addTag = useCallback(() => {
    const trimmed = tagInput.trim().toLowerCase();
    if (trimmed && !tags.includes(trimmed)) {
      setTags([...tags, trimmed]);
    }
    setTagInput("");
  }, [tagInput, tags]);

  const removeTag = (tag: string) => {
    setTags(tags.filter((t) => t !== tag));
  };

  const handleTagKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter") {
      e.preventDefault();
      addTag();
    } else if (e.key === "Backspace" && !tagInput && tags.length > 0) {
      const lastTag = tags[tags.length - 1];
      if (lastTag) {
        removeTag(lastTag);
      }
    }
  };

  const getActiveList = () => {
    if (activeTab === "mcp") return availableMcps || [];
    if (activeTab === "custom") return skillsByCategory.custom ?? [];
    return skillsByCategory.public ?? [];
  };

  const activeList = getActiveList();
  const isAllSelected = (() => {
    if (activeList.length === 0) return false;
    if (activeTab === "mcp") {
      return activeList.every((item) => selectedToolGroups.has(item.name));
    } else {
      return activeList.every((item) => selectedSkills.has(item.name));
    }
  })();

  const handleToggleSelectAll = () => {
    if (activeTab === "mcp") {
      const next = new Set(selectedToolGroups);
      if (isAllSelected) {
        activeList.forEach((item) => next.delete(item.name));
      } else {
        activeList.forEach((item) => next.add(item.name));
      }
      setSelectedToolGroups(next);
    } else {
      const next = new Set(selectedSkills);
      if (isAllSelected) {
        activeList.forEach((item) => next.delete(item.name));
      } else {
        activeList.forEach((item) => next.add(item.name));
      }
      setSelectedSkills(next);
    }
  };

  const renderToolList = () => {
    if (activeTab === "mcp") {
      if (isLoadingMcps) {
        return <div className="text-xs text-muted-foreground py-8 text-center">正在加载 MCP 扩展...</div>;
      }
      if (!availableMcps || availableMcps.length === 0) {
        return <div className="text-xs text-muted-foreground py-8 text-center">暂无已启用的 MCP 扩展工具</div>;
      }
      return availableMcps.map((mcp) => (
        <label
          key={mcp.name}
          className="flex cursor-pointer items-start gap-2.5 rounded-md px-2 py-1.5 hover:bg-muted/50 transition-colors"
        >
          <Checkbox
            checked={selectedToolGroups.has(mcp.name)}
            onCheckedChange={() => toggleToolGroup(mcp.name)}
          />
          <div className="min-w-0 -mt-0.5">
            <div className="text-xs font-medium flex items-center gap-1.5">
              {mcp.name}
              <span className="text-[9px] px-1 bg-muted rounded font-mono text-muted-foreground uppercase">{mcp.scope}</span>
            </div>
            {mcp.description && (
              <div className="text-[11px] text-muted-foreground line-clamp-1 mt-0.5">
                {mcp.description}
              </div>
            )}
          </div>
        </label>
      ));
    }
    return <AgentSkillSelection choices={skills} value={skillSelection} shared={isShared} category={activeTab === "public" ? "public" : "custom"} legacyNames={legacyNames} onReplaceLegacy={() => {setLegacyNames([]);setSelectionEdited(true);setSkillSelection({mode:"selected",resources:[]});}} onChange={(value) => {setSkillSelection(value);setSelectionEdited(true);}} />;
  };

  const handleSave = async () => {
    if (saveNeedsInspection) return;
    if (isShared && skillSelection.resources.some((r) => r.scope === "personal")) { toast.error("共享前请解除个人 Skill 选择或改选共享来源。"); return; }
    if (!agentName) return;

    const request: UpdateAgentRequest = {
      system_prompt: systemPrompt,
      persona_mbti: personaCode || null,
      template_locale: templateLocale,
      welcome_message: welcomeMessage,
      avatar_id: avatarId || null,
      quick_prompts: quickPrompts,
      description,
      model: selectedModel || null,
      skills: selectionEdited ? Array.from(new Set(skillSelection.resources.map((r) => r.name))) : Array.from(selectedSkills),
      expected_agent_id: agent?.id,
      expected_revision: agent?.revision ?? undefined,
      ...(selectionEdited ? {skill_binding_mode:skillSelection.mode,skill_resources:skillSelection.resources} : {}),
      tags,
      tool_groups: selectedToolGroups.size > 0 ? Array.from(selectedToolGroups) : null,
      enabled,
      ...(isTenantAdmin ? { is_shared: isShared } : {}),
    };

    try {
      if (!isCurrent()) return;
      await updateAgent.mutateAsync({ name: agentName, request });
      if (!isCurrent()) return;
      toast.success(t.agents.edit.saveSuccess);
      onOpenChange(false);
      onSuccess?.();
    } catch (err) {
      if (!isCurrent()) return;
      if ((err instanceof AgentMutationError && err.inspectionRequired) || err instanceof TypeError) setSaveNeedsInspection(true);
      toast.error(
        err instanceof Error ? err.message : t.agents.edit.saveError,
      );
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="w-[94vw] sm:max-w-[90vw] md:max-w-[85vw] lg:max-w-6xl xl:max-w-7xl h-[85vh] p-0 flex flex-col overflow-hidden gap-0 bg-card border border-border shadow-2xl rounded-xl">
        {saveNeedsInspection && <div role="alert" className="p-3 text-sm">保存结果需要核对，请勿重复提交。<a className="ml-2 underline" href="/workspace/agents">查看当前 Agent 配置</a></div>}
        {/* Header */}
        <header className="flex items-center justify-between border-b px-6 py-4 shrink-0">
          <div className="flex items-center gap-2.5">
            <div className="bg-primary/10 text-primary flex h-8 w-8 shrink-0 items-center justify-center rounded-lg">
              <BotIcon className="h-5 w-5" />
            </div>
            <DialogTitle className="text-base font-semibold text-foreground">
              {agent ? t.agents.edit.pageTitle.replace("{name}", agent.name) : "编辑智能体"}
            </DialogTitle>
            <DialogDescription className="sr-only">{locale === "en-US" ? "Configure this agent’s instructions, personality and welcome content." : "配置智能体的提示词、人格和欢迎内容。"}</DialogDescription>
          </div>
        </header>

        {isLoading ? (
          <div className="flex-1 flex items-center justify-center bg-zinc-50/10 dark:bg-zinc-950/10">
            <div className="text-muted-foreground text-sm">正在加载智能体数据...</div>
          </div>
        ) : !agent ? (
          <div className="flex-1 flex items-center justify-center p-6 bg-zinc-50/10 dark:bg-zinc-950/10">
            <div className="flex flex-col items-center gap-3 border rounded-xl bg-card p-8 shadow-sm">
              <AlertCircleIcon className="h-8 w-8 text-destructive animate-bounce" />
              <div className="text-sm font-medium">未找到该智能体</div>
              <Button size="sm" onClick={() => onOpenChange(false)}>
                关闭窗口
              </Button>
            </div>
          </div>
        ) : (
          <>
            {/* Body (Two Column Split Layout) */}
            <div className="flex flex-col md:flex-row divide-y md:divide-y-0 md:divide-x divide-border flex-1 overflow-hidden min-h-0">
              {/* Left Column (42% width) */}
              <div className="w-full md:w-[42%] p-6 flex flex-col gap-5 overflow-y-auto min-h-0 h-full">
                <div className="flex items-center justify-between pb-2 border-b shrink-0">
                  <h2 className="text-sm font-semibold text-foreground">基础设定</h2>
                  <div className="flex items-center gap-4">
                    {isTenantAdmin && (
                      <div className="flex items-center gap-1.5">
                        <span className="text-xs text-muted-foreground">共享工作空间</span>
                        <Switch checked={isShared} onCheckedChange={setIsShared} />
                      </div>
                    )}
                    <div className="flex items-center gap-1.5">
                      <span className="text-xs font-semibold text-primary">启</span>
                      <Switch checked={enabled} onCheckedChange={setEnabled} />
                    </div>
                  </div>
                </div>

                <AgentTemplatePicker templateReadOnly open={open} locale={templateLocale} templateId={agent.presentation?.template_id ?? ""} personaCode={personaCode} onPersona={setPersonaCode} onTemplate={() => undefined} />
                <AgentPresentationEditor quickPrompts={quickPrompts} onQuickPrompts={setQuickPrompts} open={open} locale={templateLocale} welcomeMessage={welcomeMessage} avatarId={avatarId} onWelcome={setWelcomeMessage} onAvatar={setAvatarId} onPersona={setPersonaCode} />
                {agent.presentation?.excluded_resources?.length ? <p className="text-muted-foreground text-xs">{templateLocale === "zh" ? "配套能力待独立实现：" : "Independent implementations pending: "}{agent.presentation.excluded_resources.join(", ")}</p> : null}

                {/* Read-only Identity Name */}
                <div className="space-y-2 shrink-0">
                  <label className="text-xs font-medium text-muted-foreground flex items-center gap-0.5">
                    <span className="text-destructive font-bold">*</span> 名称 (不可修改)
                  </label>
                  <Input
                    disabled
                    value={agent.name}
                    className="h-9 bg-zinc-100 dark:bg-zinc-800 cursor-not-allowed border-zinc-200"
                  />
                </div>

                {/* Model Selection */}
                <div className="space-y-2 shrink-0">
                  <label className="text-xs font-medium text-muted-foreground flex items-center gap-0.5">
                    <SparklesIcon className="h-3.5 w-3.5 text-amber-500" /> 模型选择
                  </label>
                  <Select
                    value={selectedModel}
                    onValueChange={setSelectedModel}
                  >
                    <SelectTrigger className="w-full h-9">
                      <SelectValue placeholder={isLoadingModels ? "加载模型中..." : "选择默认推理模型 (可选)"} />
                    </SelectTrigger>
                    <SelectContent>
                      {isLoadingModels ? (
                        <div className="px-2 py-3 text-xs text-muted-foreground text-center">加载中...</div>
                      ) : availableModels.length === 0 ? (
                        <div className="px-2 py-3 text-xs text-muted-foreground text-center">暂无可选模型</div>
                      ) : (
                        availableModels.map((m) => (
                          <SelectItem key={m.name} value={m.name}>
                            <div className="flex items-center gap-2">
                              <span>{m.display_name || m.model}</span>
                              <span className="text-[10px] px-1.5 py-0.5 rounded bg-muted font-mono text-muted-foreground uppercase">
                                {m.scope}
                              </span>
                            </div>
                          </SelectItem>
                        ))
                      )}
                    </SelectContent>
                  </Select>
                  <p className="text-[10px] text-muted-foreground leading-normal">
                    不选择则使用工作空间默认模型
                  </p>
                </div>

                {/* System Prompt */}
                <div className="space-y-2 flex-1 flex flex-col min-h-[160px]">
                  <label className="text-xs font-medium text-muted-foreground flex items-center gap-0.5">
                    <span className="text-destructive font-bold">*</span> 系统提示词 (System Prompt)
                  </label>
                  <Textarea
                    value={systemPrompt}
                    onChange={(e) => setSystemPrompt(e.target.value)}
                    placeholder="设定智能体的人格、职责 and 行为规范..."
                    className="flex-1 font-mono text-sm leading-relaxed resize-none border border-input focus-visible:ring-1 focus-visible:ring-ring focus-visible:border-primary"
                  />
                </div>

                {/* Tags */}
                <div className="space-y-2 shrink-0">
                  <label className="text-xs font-medium text-muted-foreground">标签</label>
                  <div className="relative flex flex-wrap gap-1.5 w-full rounded-md border border-input bg-background pl-2 pr-10 py-1.5 min-h-[36px] shadow-sm transition-colors focus-within:ring-1 focus-within:ring-ring focus-within:border-primary">
                    {tags.map((tag) => (
                      <span
                        key={tag}
                        className="bg-secondary text-secondary-foreground inline-flex items-center gap-1 rounded-md px-2 py-0.5 text-xs font-medium animate-in fade-in zoom-in-95 duration-150 shrink-0"
                      >
                        {tag}
                        <button
                          type="button"
                          onClick={() => removeTag(tag)}
                          className="hover:text-destructive text-muted-foreground/80 transition-colors ml-0.5"
                        >
                          <XIcon className="h-3 w-3" />
                        </button>
                      </span>
                    ))}
                    <input
                      value={tagInput}
                      onChange={(e) => setTagInput(e.target.value)}
                      onKeyDown={handleTagKeyDown}
                      placeholder={tags.length === 0 ? "添加标签 (按回车添加)" : ""}
                      className="flex-1 bg-transparent border-none outline-none p-0 text-sm focus:ring-0 placeholder:text-muted-foreground/60 min-w-[100px] h-6"
                    />
                    <div className="absolute inset-y-0 right-3 flex items-center pointer-events-none text-muted-foreground">
                      <ChevronDown className="h-4 w-4" />
                    </div>
                  </div>
                </div>

                {/* Description */}
                <div className="space-y-2 shrink-0">
                  <label className="text-xs font-medium text-muted-foreground">描述</label>
                  <Textarea
                    value={description}
                    onChange={(e) => setDescription(e.target.value)}
                    placeholder="简要描述智能体功能..."
                    className="min-h-[72px] text-sm leading-relaxed resize-none"
                  />
                </div>
              </div>

              {/* Right Column (58% width) */}
              <div className="w-full md:w-[58%] p-6 flex flex-col gap-6 overflow-hidden h-full">
                <div className="pb-2 border-b shrink-0">
                  <h2 className="text-sm font-semibold text-foreground">能力配置</h2>
                </div>

                {/* Toolsets */}
                <div className="space-y-3 flex-1 flex flex-col overflow-hidden min-h-0">
                  <div className="flex flex-col gap-0.5 border-l-2 border-primary pl-2.5 shrink-0">
                    <h3 className="text-sm font-semibold text-foreground">工具集</h3>
                    <p className="text-xs text-muted-foreground">配置智能体可调用的外部工具能力</p>
                  </div>

                  {/* Tabs */}
                  <div className="flex gap-2 shrink-0">
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      className={cn(
                        "px-4 py-1.5 h-8 text-xs font-medium transition-all rounded-md border",
                        activeTab === "mcp"
                          ? "border-primary text-primary bg-primary/5 hover:bg-primary/10"
                          : "text-muted-foreground hover:text-foreground"
                      )}
                      onClick={() => setActiveTab("mcp")}
                    >
                      MCP工具
                    </Button>
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      className={cn(
                        "px-4 py-1.5 h-8 text-xs font-medium transition-all rounded-md border",
                        activeTab === "custom"
                          ? "border-primary text-primary bg-primary/5 hover:bg-primary/10"
                          : "text-muted-foreground hover:text-foreground"
                      )}
                      onClick={() => setActiveTab("custom")}
                    >
                      自定义技能
                    </Button>
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      className={cn(
                        "px-4 py-1.5 h-8 text-xs font-medium transition-all rounded-md border",
                        activeTab === "public"
                          ? "border-primary text-primary bg-primary/5 hover:bg-primary/10"
                          : "text-muted-foreground hover:text-foreground"
                      )}
                      onClick={() => setActiveTab("public")}
                    >
                      内置技能
                    </Button>
                  </div>

                  {/* Tool list panel */}
                  <div className="border border-border rounded-lg bg-zinc-50/50 dark:bg-zinc-900/10 p-3 flex flex-col gap-2.5 flex-1 overflow-y-auto min-h-0">
                    <label className="flex cursor-pointer items-center gap-2.5 px-1 py-1 rounded hover:bg-muted/50 border-b pb-2 border-border/50 text-xs font-medium shrink-0">
                      <Checkbox
                        disabled={activeTab !== "mcp"}
                    checked={isAllSelected}
                        onCheckedChange={handleToggleSelectAll}
                      />
                      <span>全选</span>
                    </label>

                    <div className="space-y-1.5 overflow-y-auto pr-1 flex-1">
                      {renderToolList()}
                    </div>
                  </div>
                </div>
              </div>
            </div>

            {/* Footer Actions */}
            <footer className="border-t bg-zinc-50/50 dark:bg-zinc-900/10 px-6 py-4 flex items-center justify-end gap-3 shrink-0">
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => onOpenChange(false)}
              >
                取消
              </Button>
              <Button
                type="button"
                size="sm"
                className="bg-primary hover:bg-primary/95 text-primary-foreground font-medium px-5"
                onClick={handleSave}
                disabled={updateAgent.isPending || saveNeedsInspection}
              >
                {updateAgent.isPending ? "保存中..." : "保存配置"}
              </Button>
            </footer>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}
