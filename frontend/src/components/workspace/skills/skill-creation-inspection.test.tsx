import { expect, it, vi } from "vitest";

import { act, fireEvent, render, screen } from "@/test/utils";

import { SkillCreationInspection } from "./skill-creation-inspection";
const mock = vi.hoisted(() => ({load: vi.fn()}));
vi.mock("@/core/skills/import-context", () => ({useSkillImportContext: () => ({key: "tenant-a/user-a", identityReady: true, isCurrent: () => true})}));
vi.mock("@/core/skills/imports", async importOriginal => ({...await importOriginal<typeof import("@/core/skills/imports")>(), loadSkillImportOperations: mock.load}));
it("shows historical configuration phase and the current concrete recovered resource", async () => {
  mock.load.mockResolvedValueOnce({operations: [{operation_id: "a".repeat(32), name: "recovered", scope: "personal", state: "registered", registered: true, enabled: false, files_verified: true, kind: "manual_create", configuration_phase: "unknown", resource_id: "skill:current"}], next_cursor: null, total: 1});
  render(<SkillCreationInspection scope="personal" operationId={"a".repeat(32)} />);
  await act(async () => fireEvent.click(screen.getByRole("button", {name: "检查创建记录"})));
  const detail = screen.getByRole("link", {name: "查看当前资源与配置"});
  expect(detail).toHaveAttribute("href", "/workspace/skills/recovered?scope=personal&resource_id=skill%3Acurrent");
  expect(screen.getByText(/本次创建的配置阶段/)).toBeInTheDocument(); expect(screen.getByText(/已禁用/)).toBeInTheDocument();
});
