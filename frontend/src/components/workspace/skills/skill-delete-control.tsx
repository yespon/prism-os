"use client";

import { useQueryClient } from "@tanstack/react-query";
import { Trash2 } from "lucide-react";
import { useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  deleteOwnedSkill,
  loadSkillDeletionPreflight,
  type SkillDeletionPreflight,
} from "@/core/skills/deletions";
import { useSkillImportContext } from "@/core/skills/import-context";
import type { SkillImportScope } from "@/core/skills/imports";
import { SkillMutationError } from "@/core/skills/mutations";

import { SkillImportOperations } from "./skill-import-operations";

export function SkillDeleteControl({
  name,
  resourceId,
  scope,
  locale = "zh",
  disabled = false,
}: {
  name: string;
  resourceId?: string | null;
  scope: SkillImportScope;
  locale?: "zh" | "en";
  disabled?: boolean;
}) {
  const context = useSkillImportContext();
  const queryClient = useQueryClient();
  const zh = locale === "zh";
  const key = JSON.stringify([context.key, name, resourceId, scope]);
  const live = useRef(key);
  live.current = key;
  const generation = useRef(0);
  const busy = useRef<string | null>(null);
  const [opened, setOpened] = useState<string | null>(null);
  const [plan, setPlan] = useState<{
    key: string;
    value: SkillDeletionPreflight;
  } | null>(null);
  const [working, setWorking] = useState<string | null>(null);
  const [blocked, setBlocked] = useState<{
    key: string;
    operationId?: string;
  } | null>(null);
  const [message, setMessage] = useState<{ key: string; text: string } | null>(
    null,
  );
  const allowed =
    context.identityReady &&
    context.isCurrent() &&
    (scope === "personal" || context.canShare) &&
    !disabled &&
    !!resourceId;
  const locked = blocked?.key === key;
  const selected = plan?.key === key ? plan.value : null;
  const open = opened === key;
  function changeOpen(value: boolean) {
    generation.current += 1;
    setOpened(value ? key : null);
    setPlan(null);
    setWorking(null);
    setMessage(null);
  }
  async function perform(remove = false) {
    if (
      !allowed ||
      locked ||
      busy.current === key ||
      (remove && !selected?.eligible)
    )
      return;
    const version = generation.current;
    const current = () =>
      live.current === key &&
      generation.current === version &&
      context.isCurrent();
    busy.current = key;
    setWorking(key);
    setMessage(null);
    if (remove) setBlocked({ key }); // A dispatched deletion needs inspection until its completion is known.
    try {
      if (remove && selected) {
        await deleteOwnedSkill(scope, name, {
          expectedResourceId: selected.resource_id,
          expectedTreeSha256: selected.tree_sha256,
          expectedFileSha256: selected.file_sha256 ?? undefined,
          isCurrent: current,
        });
        if (!current()) return;
        setBlocked(null);
        setPlan(null);
        setMessage({
          key,
          text: zh
            ? "删除与回收已完成。"
            : "Withdrawal and reclamation completed.",
        });
        for (const queryKey of [
          ["skills"],
          ["availableSkills"],
          ["tenantSkills"],
        ])
          void queryClient.invalidateQueries({ queryKey });
      } else {
        const value = await loadSkillDeletionPreflight(scope, name, {
          expectedResourceId: resourceId ?? undefined,
          isCurrent: current,
        });
        if (current()) setPlan({ key, value });
      }
    } catch (error) {
      if (!current()) return;
      setPlan(null);
      if (remove && error instanceof SkillMutationError && !error.inspectionRequired && error.status < 500) {
        setBlocked(null);
        setMessage({key,text:zh ? "删除未执行。请重新核对当前实例与权限后再确认。" : "Deletion was rejected. Inspect the current instance and permission before confirming again."});
      } else if (remove) {
        setBlocked({
          key,
          operationId:
            error instanceof SkillMutationError ? error.operationId : undefined,
        });
        setMessage({
          key,
          text: zh
            ? "删除尚未确认。请检查记录，勿重复删除。"
            : "Deletion is unconfirmed. Inspect records before taking another action.",
        });
      } else
        setMessage({
          key,
          text: zh
            ? "当前实例、目录或权限无法核对，请刷新资源列表。"
            : "Current instance, contents or permission could not be verified. Refresh the resource list.",
        });
    } finally {
      if (busy.current === key) busy.current = null;
      if (current()) setWorking(null);
    }
  }
  return (
    <Dialog open={open} onOpenChange={changeOpen}>
      <Button
        type="button"
        size="icon"
        variant="ghost"
        disabled={!allowed}
        aria-label={`${zh ? "删除" : "Delete"} ${name}`}
        onClick={(event) => {
          event.stopPropagation();
          changeOpen(true);
        }}
      >
        <Trash2 className="h-4 w-4" />
      </Button>
      <DialogContent onClick={(event) => event.stopPropagation()}>
        <DialogHeader>
          <DialogTitle>
            {zh ? "核对并删除" : "Inspect and delete"} {name}
          </DialogTitle>
          <DialogDescription>
            {zh
              ? "删除当前登记与配置，并回收经核对的自有目录。公共源文件保留。"
              : "Withdraw the current registration and configuration, and reclaim verified owned contents. Public source files are retained."}
          </DialogDescription>
        </DialogHeader>
        {message?.key === key && <p role="status">{message.text}</p>}
        {!locked && (
          <Button
            type="button"
            variant="outline"
            disabled={!allowed || working === key}
            onClick={() => void perform()}
          >
            {zh ? "核对当前删除范围" : "Inspect current deletion scope"}
          </Button>
        )}
        {selected && (
          <section className="space-y-2 text-sm">
            <p className="break-all">{selected.resource_id}</p>
            <p className="break-all">{selected.tree_sha256}</p>
            <p>
              {zh
                ? `自有文件 ${selected.members} 项；关联 Agent ${selected.references} 项。`
                : `${selected.members} owned files; ${selected.references} Agent references.`}
            </p>
            {!selected.eligible && (
              <p>
                {zh
                  ? "名称引用尚未解除，无法回收。请检查关联 Agent 后重新核对。"
                  : "Unresolved name references block reclamation. Inspect related Agents and check again."}{" "}
                <a className="underline" href="/workspace/agents">
                  {zh ? "查看 Agent" : "Inspect Agents"}
                </a>
              </p>
            )}
            {selected.target_kind === "missing" && (
              <p>
                {zh
                  ? "原目录缺失；本次仅撤回登记与配置。"
                  : "The original directory is missing; only registration and configuration will be withdrawn."}
              </p>
            )}
            <Button
              type="button"
              variant="destructive"
              disabled={!allowed || working === key || !selected.eligible}
              onClick={() => void perform(true)}
            >
              {zh ? "确认删除当前实例" : "Confirm deletion of this instance"}
            </Button>
          </section>
        )}
        {locked && (
          <section className="space-y-2">
            <p className="break-all">{blocked.operationId}</p>
            <SkillImportOperations scope={scope} locale={locale} deletion />
          </section>
        )}
      </DialogContent>
    </Dialog>
  );
}
