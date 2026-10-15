"use client";

import { useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import {
  AgentMutationError,
  AgentReadError,
  copyAgent,
  getAgent,
  useSkills,
} from "@/core/agents";
import type { Agent } from "@/core/agents";
import { useDraftIsCurrent } from "@/core/agents/draft-scope";
import { isTenantAdminRole } from "@/core/permissions/scope";
import { useSkillImportContext } from "@/core/skills/import-context";
import { useCurrentTenant } from "@/core/tenants/hooks";

import {
  AgentSkillSelection,
  type AgentSkillSelectionValue,
} from "./agent-skill-selection";

export function CopyAgentDialog(props: {
  agent: Agent | null;
  onClose: () => void;
  onSuccess?: () => void;
}) {
  const { key } = useSkillImportContext();
  return props.agent ? (
    <CopyAgentFields
      key={`${key}:${props.agent.id}`}
      {...props}
      agent={props.agent}
    />
  ) : null;
}

function CopyAgentFields({
  agent,
  onClose,
  onSuccess,
}: {
  agent: Agent;
  onClose: () => void;
  onSuccess?: () => void;
}) {
  const isCurrent = useDraftIsCurrent();
  const { data: tenant } = useCurrentTenant();
  const { skills } = useSkills();
  const [source, setSource] = useState(agent);
  const [name, setName] = useState(`${agent.name}-copy`);
  const [attemptedName, setAttemptedName] = useState(name);
  const [shared, setShared] = useState(false);
  const [pending, setPending] = useState(false);
  const [inspect, setInspect] = useState(false);
  const [selection, setSelection] = useState<AgentSkillSelectionValue>({
    mode: agent.skill_binding_mode === "all" ? "all" : "selected",
    resources:
      agent.skill_binding_mode === "selected"
        ? (agent.skill_resources ?? [])
        : [],
  });
  const forbiddenPersonal =
    shared &&
    selection.resources.some((resource) => resource.scope === "personal");
  async function save() {
    if (!source.revision || pending || inspect || !isCurrent()) return;
    setAttemptedName(name);
    setPending(true);
    try {
      await copyAgent(
        source.name,
        {
          name,
          source_agent_id: source.id,
          source_revision: source.revision,
          is_shared: shared,
          skill_binding_mode: selection.mode,
          skill_resources: selection.resources,
        },
        { isCurrent },
      );
      if (!isCurrent()) return;
      toast.success("已创建新 Agent");
      onSuccess?.();
      onClose();
    } catch (error) {
      if (!isCurrent()) return;
      if (
        error instanceof AgentMutationError &&
        (error.inspectionRequired || error.status === 409)
      )
        setInspect(true);
      toast.error(error instanceof Error ? error.message : "复制失败");
    } finally {
      if (isCurrent()) setPending(false);
    }
  }
  async function inspectSource() {
    if (!isCurrent()) return;
    setPending(true);
    try {
      try {
        const existing = await getAgent(attemptedName);
        if (!isCurrent()) return;
        toast.info(
          `目标 ${existing.name} 已存在，请从列表核对；没有重复提交。`,
        );
        onSuccess?.();
        onClose();
        return;
      } catch (error) {
        if (!(error instanceof AgentReadError) || error.status !== 404)
          throw error;
      }
      if (!isCurrent()) return;
      const current = await getAgent(source.name);
      if (!isCurrent()) return;
      setSource(current);
      setInspect(false);
    } catch (error) {
      if (isCurrent())
        toast.error(error instanceof Error ? error.message : "读取来源失败");
    } finally {
      if (isCurrent()) setPending(false);
    }
  }
  return (
    <Dialog
      open
      onOpenChange={(open) => {
        if (!open && !pending) onClose();
      }}
    >
      <DialogContent className="max-h-[85vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>复制 Agent</DialogTitle>
          <DialogDescription>
            来源：{source.name}。请确认新 Agent 的名称、共享范围和可用技能。
          </DialogDescription>
        </DialogHeader>
        <label>
          新名称
          <Input
            value={name}
            onChange={(event) => setName(event.target.value)}
            disabled={pending}
          />
        </label>
        <label className="flex items-center gap-2">
          <Switch
            checked={shared}
            onCheckedChange={setShared}
            disabled={pending || !isTenantAdminRole(tenant?.role)}
          />
          共享到当前租户
        </label>
        {!source.skill_binding_mode ||
        source.skill_binding_mode === "unresolved" ? (
          <p>旧技能名称尚未确认来源，请明确选择；当前默认不绑定技能。</p>
        ) : null}
        <Button
          variant="outline"
          onClick={() => setSelection({ mode: "selected", resources: [] })}
          disabled={pending}
        >
          清空并重新选择技能
        </Button>
        <AgentSkillSelection
          choices={skills}
          value={selection}
          onChange={setSelection}
          shared={shared}
          category="public"
        />
        <AgentSkillSelection
          choices={skills}
          value={selection}
          onChange={setSelection}
          shared={shared}
          category="custom"
        />
        {forbiddenPersonal ? (
          <p role="alert">
            共享 Agent 不能保留个人技能，请移除个人选择或取消共享。
          </p>
        ) : null}
        {inspect ? (
          <div role="alert">
            <p>
              复制结果或来源已变化。请先检查列表是否已存在目标
              Agent，再重新读取来源；不会自动重复提交。
            </p>
            <Button
              variant="outline"
              onClick={() => void inspectSource()}
              disabled={pending}
            >
              重新读取来源
            </Button>
          </div>
        ) : null}
        <Button
          onClick={() => void save()}
          disabled={
            pending ||
            inspect ||
            forbiddenPersonal ||
            !source.revision ||
            !/^[A-Za-z0-9-]+$/.test(name)
          }
        >
          {pending ? "正在复制…" : "确认创建副本"}
        </Button>
      </DialogContent>
    </Dialog>
  );
}
