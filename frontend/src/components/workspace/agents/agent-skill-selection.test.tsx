import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";

import type { Skill } from "@/core/agents/types";

import { AgentSkillSelection } from "./agent-skill-selection";
const choices: Skill[] = ["global", "tenant", "personal"].map((scope) => ({
  name: "collision",
  description: scope,
  category: scope === "global" ? "public" : "custom",
  scope: scope as Skill["scope"],
  resource_id: `instance:${scope}`,
  enabled: true,
}));
afterEach(cleanup);
it("keeps same-name personal and tenant choices separate and sends the selected generation", () => {
  const change = vi.fn();
  render(
    <AgentSkillSelection
      choices={choices}
      value={{ mode: "selected", resources: [] }}
      onChange={change}
      shared={false}
      category="custom"
    />,
  );
  fireEvent.click(screen.getByRole("checkbox", { name: "collision personal" }));
  expect(change).toHaveBeenCalledWith({
    mode: "selected",
    resources: [
      {
        name: "collision",
        scope: "personal",
        resource_id: "instance:personal",
      },
    ],
  });
  expect(
    screen.getByRole("checkbox", { name: "collision tenant" }),
  ).not.toBeChecked();
});
it("prevents carrying a personal choice into shared configuration", () => {
  render(
    <AgentSkillSelection
      choices={choices}
      value={{ mode: "selected", resources: [] }}
      onChange={vi.fn()}
      shared
      category="custom"
    />,
  );
  expect(
    screen.getByRole("checkbox", { name: "collision personal" }),
  ).toBeDisabled();
  expect(
    screen.getByRole("checkbox", { name: "collision tenant" }),
  ).not.toBeDisabled();
});
it("requires explicit legacy reselection without silently checking any same-name source", () => {
  const replace = vi.fn();
  render(
    <AgentSkillSelection
      choices={choices}
      value={{ mode: "selected", resources: [] }}
      onChange={vi.fn()}
      shared={false}
      category="custom"
      legacyNames={["collision"]}
      onReplaceLegacy={replace}
    />,
  );
  expect(
    screen.getByRole("checkbox", { name: "collision personal" }),
  ).not.toBeChecked();
  expect(
    screen.getByRole("checkbox", { name: "collision personal" }),
  ).toBeDisabled();
  fireEvent.click(screen.getByRole("button", { name: "重新选择旧名称来源" }));
  expect(replace).toHaveBeenCalledOnce();
});
it("separates explicit zero from all-current selection", () => {
  const change = vi.fn();
  render(
    <AgentSkillSelection
      choices={choices}
      value={{ mode: "selected", resources: [] }}
      onChange={change}
      shared={false}
      category="custom"
    />,
  );
  expect(screen.getByText(/当前未选择技能/)).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "所有当前可用技能" }));
  expect(change).toHaveBeenCalledWith({ mode: "all", resources: [] });
});
