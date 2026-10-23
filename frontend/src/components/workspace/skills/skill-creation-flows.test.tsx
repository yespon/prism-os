import { beforeEach, expect, it, vi } from "vitest";

import { SaveAsSkillDialog as IncidentDialog } from "@/components/workspace/incidents/save-as-skill-dialog";
import { SaveAsSkillDialog as TerminalDialog } from "@/components/workspace/terminal/save-as-skill-dialog";
import { SkillMutationError } from "@/core/skills/mutations";
import { act, fireEvent, render, screen, waitFor } from "@/test/utils";

const mock = vi.hoisted(() => ({key: "tenant-a/user-a", current: true, create: vi.fn(), refine: vi.fn(), success: vi.fn(), push: vi.fn()}));
vi.mock("next/navigation", () => ({useRouter: () => ({push: mock.push})}));
vi.mock("sonner", () => ({toast: {success: mock.success}}));
vi.mock("@/core/skills/import-context", () => ({useSkillImportContext: () => ({key: mock.key, identityReady: true, canShare: false, isCurrent: () => mock.current})}));
vi.mock("@/core/skills/api", () => ({createPersonalSkill: mock.create, summarizeDiagnosis: mock.refine}));
vi.mock("@/components/workspace/messages/markdown-content", () => ({MarkdownContent: ({content}: {content: string}) => <div>{content}</div>}));
beforeEach(() => {
  vi.clearAllMocks(); mock.key = "tenant-a/user-a"; mock.current = true;
  mock.refine.mockResolvedValue({suggested_name: "reviewed-sop", suggested_description: "Reviewed description", instructions: "Reviewed instruction", suggested_tools: [], suggested_category: "custom"});
});
async function preview(kind: "incident" | "terminal") {
  const view = render(kind === "incident" ? <IncidentDialog incidentTitle="Owned incident" diagnosisText="Owned diagnosis" /> : <TerminalDialog sessionTitle="Owned terminal" diagnosisText="Owned diagnosis" />);
  fireEvent.click(screen.getByRole("button", {name: "存为 Skill"}));
  fireEvent.click(screen.getByRole("button", {name: "开始 AI 提炼"}));
  await waitFor(() => expect(screen.getByRole("button", {name: "保存为 Skill"})).toBeInTheDocument());
  return view;
}
it.each(["incident", "terminal"] as const)("%s unknown creation blocks repeats and offers original recovery inspection", async kind => {
  mock.create.mockRejectedValueOnce(new SkillMutationError(503, "skill:current", true, "Inspect", "a".repeat(32)));
  await preview(kind); fireEvent.click(screen.getByRole("button", {name: "保存为 Skill"}));
  await waitFor(() => expect(screen.getByRole("button", {name: "保存为 Skill"})).toBeDisabled());
  expect(screen.getByRole("button", {name: "检查创建记录"})).toBeInTheDocument();
  expect(screen.getByText("a".repeat(32))).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", {name: "保存为 Skill"}));
  expect(mock.create).toHaveBeenCalledOnce(); expect(mock.success).not.toHaveBeenCalled(); expect(mock.push).not.toHaveBeenCalled();
});
it.each(["incident", "terminal"] as const)("%s closing invalidates late creation success and navigation", async kind => {
  let resolve!: (value: object) => void;
  mock.create.mockReturnValueOnce(new Promise(done => {resolve = done;}));
  await preview(kind); fireEvent.click(screen.getByRole("button", {name: "保存为 Skill"}));
  await waitFor(() => expect(mock.create).toHaveBeenCalledOnce());
  fireEvent.keyDown(screen.getByRole("dialog"), {key: "Escape"});
  await act(async () => resolve({name: "reviewed-sop"}));
  expect(mock.success).not.toHaveBeenCalled(); expect(mock.push).not.toHaveBeenCalled();
  const options = mock.create.mock.calls[0]?.[1] as {isCurrent: () => boolean}; expect(options.isCurrent()).toBe(false);
});
it.each(["incident", "terminal"] as const)("%s identity change discards late refinement", async kind => {
  let resolve!: (value: object) => void;
  mock.refine.mockReturnValueOnce(new Promise(done => {resolve = done;}));
  const props = {diagnosisText: "Owned diagnosis"};
  const view = render(kind === "incident" ? <IncidentDialog {...props} incidentTitle="Owned incident" /> : <TerminalDialog {...props} />);
  fireEvent.click(screen.getByRole("button", {name: "存为 Skill"})); fireEvent.click(screen.getByRole("button", {name: "开始 AI 提炼"}));
  mock.key = "tenant-b/user-b";
  view.rerender(kind === "incident" ? <IncidentDialog {...props} incidentTitle="New incident" /> : <TerminalDialog {...props} />);
  await act(async () => resolve({suggested_name: "old-private", suggested_description: "Old private", instructions: "OLD PRIVATE", suggested_tools: [], suggested_category: "custom"}));
  fireEvent.click(screen.getByRole("button", {name: "存为 Skill"}));
  expect(screen.queryByText("OLD PRIVATE")).not.toBeInTheDocument(); expect(mock.create).not.toHaveBeenCalled();
});
