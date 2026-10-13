"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { useSkillImportContext } from "@/core/skills/import-context";
import {
  changeSkillImportOperation,
  loadSkillImportOperations,
  SkillImportError,
  type SkillImportOperation,
  type SkillImportScope,
} from "@/core/skills/imports";

const states: Record<string, [string, string]> = {
  registered: ["已登记", "Registered"],
  registration_pending: [
    "文件已发布，待核对登记",
    "Published, registration pending",
  ],
  publication_pending: [
    "暂存完整，待发布",
    "Complete stage, publication pending",
  ],
  registration_conflict: [
    "登记冲突，保留现状",
    "Registration conflict, contents preserved",
  ],
  files_unverified: ["内容或位置无法核对", "Contents or location unverified"],
  aborted: ["已放弃暂存", "Staging aborted"],
  receipt_unavailable: [
    "记录无法核对，内容保留",
    "Receipt unverified, contents preserved",
  ],
};

export function SkillImportOperations({
  scope,
  locale,
  open = true,
  creation = false,
}: {
  scope: SkillImportScope;
  locale: "zh" | "en";
  open?: boolean;
  creation?: boolean;
}) {
  const context = useSkillImportContext();
  const queryClient = useQueryClient();
  const zh = locale === "zh";
  const key = JSON.stringify([context.key, scope, locale, open, creation]);
  const live = useRef(key);
  live.current = key;
  const controller = useRef<AbortController | null>(null);
  const busy = useRef(false);
  const [result, setResult] = useState<{
    key: string;
    operations: SkillImportOperation[];
    nextCursor: string | null;
    total: number;
  } | null>(null);
  const [message, setMessage] = useState<{ key: string; text: string } | null>(
    null,
  );
  const [working, setWorking] = useState("");
  const [confirm, setConfirm] = useState<{
    key: string;
    operation: SkillImportOperation;
    action: "recover" | "abort";
  } | null>(null);
  useEffect(() => {
    controller.current?.abort();
    busy.current = false;
    setResult(null);
    setMessage(null);
    setWorking("");
    setConfirm(null);
    return () => {
      controller.current?.abort();
    };
  }, [key]);
  const valid = (request: AbortController) =>
    !request.signal.aborted && live.current === key && context.isCurrent();
  const allowed =
    context.identityReady && (scope === "personal" || context.canShare);
  async function inspect(more = false) {
    if (!allowed || !context.isCurrent() || busy.current) return;
    const previous = more && result?.key === key ? result : null;
    if (more && !previous?.nextCursor) return;
    busy.current = true;
    controller.current?.abort();
    const request = new AbortController();
    controller.current = request;
    setWorking(more ? "more" : "inspect");
    setMessage(null);
    setConfirm(null);
    try {
      const body = await loadSkillImportOperations(
        scope,
        request.signal,
        previous?.nextCursor ?? undefined,
      );
      if (valid(request)) {
        const merged = new Map(
          (previous?.operations ?? []).map((operation) => [
            operation.operation_id,
            operation,
          ]),
        );
        for (const operation of body.operations)
          merged.set(operation.operation_id, operation);
        setResult({
          key,
          operations: Array.from(merged.values()),
          nextCursor: body.next_cursor ?? null,
          total: body.total ?? body.operations.length,
        });
      }
    } catch (error) {
      if (valid(request)) {
        if (
          !more ||
          (error instanceof SkillImportError &&
            [400, 401, 403].includes(error.status))
        )
          setResult(null);
        setMessage({
          key,
          text: zh
            ? "记录核对失败，请重试。"
            : "Import records unavailable. Please retry.",
        });
      }
    } finally {
      if (valid(request)) {
        busy.current = false;
        setWorking("");
      }
    }
  }
  async function act() {
    if (
      confirm?.key !== key ||
      !allowed ||
      !context.isCurrent() ||
      busy.current
    )
      return;
    busy.current = true;
    controller.current?.abort();
    const request = new AbortController();
    controller.current = request;
    const selected = confirm;
    setConfirm(null);
    setWorking(selected.action);
    setMessage(null);
    try {
      const outcome = await changeSkillImportOperation(
        scope,
        selected.operation.operation_id,
        selected.action,
        request.signal,
      );
      if (!valid(request)) return;
      if (outcome.operation_id !== selected.operation.operation_id)
        throw new SkillImportError(503);
      const body = await loadSkillImportOperations(scope, request.signal);
      if (!valid(request)) return;
      const operations = body.operations.some(
        (operation) => operation.operation_id === outcome.operation_id,
      )
        ? body.operations
        : [outcome, ...body.operations];
      setResult({
        key,
        operations,
        nextCursor: body.next_cursor ?? null,
        total: body.total ?? body.operations.length,
      });
      setMessage({
        key,
        text: zh
          ? "已重新核对当前记录。登记不代表已绑定或可执行。"
          : "Current records checked. Registration does not imply bindings or execution rights.",
      });
      for (const queryKey of [
        ["skills"],
        ["availableSkills"],
        ["tenantSkills"],
      ])
        void queryClient.invalidateQueries({ queryKey });
    } catch {
      if (valid(request)) {
        setResult(null);
        setMessage({
          key,
          text: zh
            ? "结果暂无法确认或存在冲突。文件已保留；先检查记录，再决定后续操作。"
            : "Outcome uncertain or conflicting. Contents were preserved; inspect records before taking another action.",
        });
      }
    } finally {
      if (valid(request)) {
        busy.current = false;
        setWorking("");
      }
    }
  }
  const visible = result?.key === key ? result.operations : null;
  const nextCursor = result?.key === key ? result.nextCursor : null;
  const choice = confirm?.key === key ? confirm : null;
  if (!open) return null;
  return (
    <section
      className="space-y-2 rounded border p-3 text-sm"
      aria-label={creation ? (zh ? "Skill 创建记录" : "Skill creation records") : (zh ? "Skill 导入记录" : "Skill import records")}
    >
      <p>
        {zh
          ? "请求中断不代表服务器回滚。先核对记录，避免重复导入。"
          : "An interrupted request does not prove server rollback. Inspect records before importing again."}
      </p>
      <Button
        type="button"
        variant="outline"
        disabled={!allowed || !!working}
        onClick={() => void inspect()}
      >
        {working === "inspect"
          ? zh
            ? "正在检查记录…"
            : "Inspecting records…"
          : zh
            ? (creation ? "检查创建记录" : "检查导入记录")
            : (creation ? "Inspect creation records" : "Inspect import records")}
      </Button>
      {!allowed && (
        <p>
          {zh
            ? "请使用当前会话；租户共享记录需要当前租户管理员权限。"
            : "Use the current session. Tenant shared records require the current tenant admin role."}
        </p>
      )}
      {message?.key === key && <p role="status">{message.text}</p>}
      {visible?.length === 0 && (
        <p>{zh ? "暂无导入记录。" : "No import records."}</p>
      )}
      {visible && (
        <ul className="max-h-64 space-y-2 overflow-auto">
          {visible.map((operation) => (
            <li className="rounded border p-2" key={operation.operation_id}>
              <p>
                {operation.name ||
                  (zh ? "无法核对的记录" : "Unverified receipt")}{" "}
                ·{" "}
                {
                  (states[operation.state] ?? ["待核对", "Needs inspection"])[
                    zh ? 0 : 1
                  ]
                }
                {operation.registered && operation.enabled === false
                  ? zh
                    ? "，已禁用"
                    : ", disabled"
                  : ""}
              </p>
              <p className="text-muted-foreground text-xs break-all">
                {operation.operation_id}
              </p>
              {operation.kind === "manual_create" && <p className="text-xs">
                {zh ? "本次创建的配置阶段：" : "Configuration phase of this creation: "}
                {({pending: ["尚未完成", "Pending"], confirmed: ["已完成", "Completed"], unknown: ["待核对", "Needs inspection"]}[operation.configuration_phase ?? "pending"])[zh ? 0 : 1]}
                {operation.registered && operation.resource_id && <a className="ml-2 underline" href={`/workspace/skills/${encodeURIComponent(operation.name)}?scope=${scope}&resource_id=${encodeURIComponent(operation.resource_id)}`}>{zh ? "查看当前资源与配置" : "Inspect current resource and configuration"}</a>}
              </p>}
              {!operation.registered &&
                ((operation.state === "registration_pending" &&
                  operation.files_verified) ||
                  (operation.state === "publication_pending" &&
                    operation.staged_files_verified)) && (
                  <Button
                    type="button"
                    variant="outline"
                    disabled={!!working}
                    onClick={() =>
                      setConfirm({ key, operation, action: "recover" })
                    }
                  >
                    {zh ? "继续核对并登记" : "Continue and register"}
                  </Button>
                )}
              {!operation.registered &&
                !operation.files_verified &&
                ["allocated", "staging", "prepared"].includes(
                  operation.phase ?? "",
                ) && (
                  <Button
                    type="button"
                    variant="outline"
                    disabled={!!working}
                    onClick={() =>
                      setConfirm({ key, operation, action: "abort" })
                    }
                  >
                    {zh ? "放弃自有暂存" : "Abort owned staging"}
                  </Button>
                )}
            </li>
          ))}
        </ul>
      )}
      {visible && (
        <p>
          {zh
            ? `已检查 ${visible.length} 条 / 当前 ${result?.total ?? 0} 条；所有记录均保留。新产生的记录请重新检查。`
            : `Inspected ${visible.length} / ${result?.total ?? 0} current records. All receipts are retained; inspect again for new records.`}
        </p>
      )}
      {nextCursor && (
        <Button
          type="button"
          variant="outline"
          disabled={!allowed || !!working}
          onClick={() => void inspect(true)}
        >
          {working === "more"
            ? zh
              ? "正在加载…"
              : "Loading…"
            : zh
              ? "加载更多记录"
              : "Load more records"}
        </Button>
      )}
      {choice && (
        <div
          role="group"
          aria-label={zh ? "确认导入恢复操作" : "Confirm import recovery"}
          className="rounded border p-2"
        >
          <p>
            {choice.action === "recover"
              ? zh
                ? `确认核对 ${choice.operation.name}，必要时发布并登记到当前${scope === "tenant" ? "租户共享" : "个人"}范围？`
                : `Inspect ${choice.operation.name}, and publish/register if needed in the current ${scope} scope?`
              : zh
                ? `确认放弃 ${choice.operation.name} 的自有暂存？已发布文件不会按此操作删除。`
                : `Abort owned staging for ${choice.operation.name}? This action cannot delete published files.`}
          </p>
          <Button type="button" disabled={!!working} onClick={() => void act()}>
            {zh ? "确认操作" : "Confirm action"}
          </Button>
          <Button
            type="button"
            variant="ghost"
            disabled={!!working}
            onClick={() => setConfirm(null)}
          >
            {zh ? "返回" : "Back"}
          </Button>
        </div>
      )}
      {working && working !== "inspect" && working !== "more" && (
        <p role="status">
          {zh
            ? "正在处理；离开页面后请重新核对结果。"
            : "Processing; inspect the outcome again if you leave this page."}
        </p>
      )}
    </section>
  );
}
