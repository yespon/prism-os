"use client";

import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import type { Skill, SkillResourceReference } from "@/core/agents/types";

export interface AgentSkillSelectionValue {
  mode: "all" | "selected";
  resources: SkillResourceReference[];
}
export function AgentSkillSelection({
  choices,
  value,
  onChange,
  shared,
  category,
  legacyNames = [],
  onReplaceLegacy,
}: {
  choices: Skill[];
  value: AgentSkillSelectionValue;
  onChange: (value: AgentSkillSelectionValue) => void;
  shared: boolean;
  category: "custom" | "public";
  legacyNames?: string[];
  onReplaceLegacy?: () => void;
}) {
  const visible = choices.filter((item) =>
    category === "public" ? item.scope === "global" : item.scope !== "global",
  );
  const toggle = (item: Skill) => {
    if (!item.resource_id || !item.scope || legacyNames.length) return;
    const existing = value.resources.some(
      (r) => r.resource_id === item.resource_id,
    );
    onChange({
      mode: "selected",
      resources: existing
        ? value.resources.filter((r) => r.resource_id !== item.resource_id)
        : [
            ...value.resources,
            {
              name: item.name,
              scope: item.scope,
              resource_id: item.resource_id,
            },
          ],
    });
  };
  return (
    <section className="space-y-2 text-xs" aria-label="具体 Skill 选择">
      {legacyNames.length > 0 && (
        <div role="alert">
          <p>
            旧名称尚未确认具体来源：{legacyNames.join("、")}
            。保留原配置，或明确重新选择。
          </p>
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={onReplaceLegacy}
          >
            重新选择旧名称来源
          </Button>
        </div>
      )}
      <div className="flex gap-2">
        <Button
          type="button"
          size="sm"
          variant={value.mode === "all" ? "default" : "outline"}
          disabled={legacyNames.length > 0}
          onClick={() => onChange({ mode: "all", resources: [] })}
        >
          所有当前可用技能
        </Button>
        <Button
          type="button"
          size="sm"
          variant={value.mode === "selected" ? "default" : "outline"}
          disabled={legacyNames.length > 0}
          onClick={() =>
            onChange({ mode: "selected", resources: value.resources })
          }
        >
          仅明确选择的技能
        </Button>
      </div>
      {value.mode === "selected" && value.resources.length === 0 && (
        <p>当前未选择技能；不会自动使用所有技能。</p>
      )}
      {visible.map((item) => (
        <label
          key={item.resource_id ?? `${item.scope}:${item.name}`}
          className="flex items-start gap-2 rounded border p-2"
        >
          <Checkbox
            aria-label={`${item.name} ${item.scope}`}
            checked={
              value.mode === "selected" &&
              value.resources.some((r) => r.resource_id === item.resource_id)
            }
            disabled={
              !item.resource_id ||
              !item.scope ||
              (shared && item.scope === "personal") ||
              legacyNames.length > 0
            }
            onCheckedChange={() => toggle(item)}
          />
          <span>
            <span className="font-medium">
              {item.name} ·{" "}
              {item.scope === "global"
                ? "公共"
                : item.scope === "tenant"
                  ? "租户共享"
                  : "个人"}
            </span>
            <span className="text-muted-foreground block break-all">
              {item.resource_id}
            </span>
            <span className="block">
              {item.description}
              {!item.enabled ? "（已禁用，保存选择不代表可运行）" : ""}
            </span>
          </span>
        </label>
      ))}
      {value.resources
        .filter((r) => !choices.some((c) => c.resource_id === r.resource_id))
        .map((r) => (
          <p key={r.resource_id} className="break-all">
            {r.name} · {r.scope}：已选实例当前不可用{" "}
            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={() =>
                onChange({
                  mode: "selected",
                  resources: value.resources.filter(
                    (item) => item.resource_id !== r.resource_id,
                  ),
                })
              }
            >
              解除此选择
            </Button>
          </p>
        ))}
    </section>
  );
}
