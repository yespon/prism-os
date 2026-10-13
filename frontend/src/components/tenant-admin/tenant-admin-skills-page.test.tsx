import { describe, expect, it, vi } from "vitest";

import { SkillMutationError } from "@/core/skills/mutations";
import { act, fireEvent, render, screen } from "@/test/utils";


import { TenantAdminSkillsPage } from "./tenant-admin-skills-page";

const mocks = vi.hoisted(() => ({
  identity: "tenant-a/user-a",
  current: true,
  success: vi.fn(),
  useAvailableSkills: vi.fn(),
  useCreateTenantSkill: vi.fn(),
  useDeleteTenantSkill: vi.fn(),
  useImportTenantSkill: vi.fn(),
  usePatchTenantSkill: vi.fn(),
  useUpdateTenantSkill: vi.fn(),
}));

vi.mock("@/core/skills/import-context", () => ({ useSkillImportContext: () => ({key: mocks.identity, identityReady: true, canShare: true, isCurrent: () => mocks.current}) }));

vi.mock("sonner", () => ({toast: {success: mocks.success, error: vi.fn()}}));

vi.mock("@/core/skills/hooks", () => ({
  useAvailableSkills: mocks.useAvailableSkills,
  useCreateTenantSkill: mocks.useCreateTenantSkill,
  useDeleteTenantSkill: mocks.useDeleteTenantSkill,
  useImportTenantSkill: mocks.useImportTenantSkill,
  usePatchTenantSkill: mocks.usePatchTenantSkill,
  useUpdateTenantSkill: mocks.useUpdateTenantSkill,
}));

describe("TenantAdminSkillsPage", () => {
  const createSkill = vi.fn();
  const importSkill = vi.fn();
  const patchSkill = vi.fn();
  const toggleSkill = vi.fn();

  const renderPage = () => {
    mocks.identity = "tenant-a/user-a";
    mocks.current = true;
    mocks.success.mockClear();
    createSkill.mockReset();
    importSkill.mockReset();
    patchSkill.mockReset();
    toggleSkill.mockReset();
    mocks.useAvailableSkills.mockReturnValue({
      skills: [
        {
          name: "builtin-skill",
          description: "系统内置说明",
          category: "public",
          license: "MIT",
          enabled: true,
          scope: "global",
          source: "platform_builtin",
          managed_by_current_user: false,
          effective_permissions: ["read", "use"],
        },
        {
          name: "custom-skill-a",
          resource_id: "skill:current",
          file_sha256: "a".repeat(64),
          description: "自定义说明",
          category: "custom",
          license: "MIT",
          enabled: true,
          scope: "tenant",
          source: "tenant_shared",
          managed_by_current_user: true,
          effective_permissions: ["read", "use", "manage"],
          bound_tools: ["jira"],
          prompt_template: "You are tenant assistant",
          strategy: "guided",
          instructions: "Use jira to analyze issues",
        },
      ],
      isLoading: false,
      error: null,
    });

    mocks.useCreateTenantSkill.mockReturnValue({ mutateAsync: createSkill });
    mocks.useDeleteTenantSkill.mockReturnValue({ mutateAsync: vi.fn() });
    mocks.useImportTenantSkill.mockReturnValue({ mutateAsync: importSkill, isPending: false });
    mocks.usePatchTenantSkill.mockReturnValue({ mutateAsync: patchSkill });
    mocks.useUpdateTenantSkill.mockReturnValue({ mutateAsync: toggleSkill, canToggleResource: () => true, enablementNeedsInspection: false });

    return render(<TenantAdminSkillsPage />);
  };

  const activateTab = (name: string) => {
    const tab = screen.getByRole("tab", { name });
    fireEvent.pointerDown(tab);
    fireEvent.mouseDown(tab);
    fireEvent.click(tab);
  };

  it("passes the listed concrete instance with enablement", async () => {
    renderPage(); activateTab("团队技能 (1)");
    toggleSkill.mockResolvedValueOnce({});
    fireEvent.click(screen.getByRole("switch"));
    expect(toggleSkill).toHaveBeenCalledWith({skillName: "custom-skill-a", enabled: false, expectedResourceId: "skill:current"});
  });

  it("unknown shared manual creation blocks repeats and offers current operation inspection", async () => {
    renderPage(); createSkill.mockRejectedValueOnce(new SkillMutationError(503, "skill:current", true, "Inspect", "a".repeat(32)));
    fireEvent.click(screen.getByRole("button", {name: "新建 / 导入"}));
    fireEvent.change(screen.getByLabelText(/名称/), {target: {value: "manual-owned"}});
    fireEvent.change(screen.getByLabelText(/描述/), {target: {value: "Owned shared"}});
    fireEvent.click(screen.getByRole("button", {name: "保存"}));
    await act(async () => {await Promise.resolve();});
    expect(screen.getByRole("button", {name: "保存"})).toBeDisabled(); expect(screen.getByRole("button", {name: "检查创建记录"})).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", {name: "保存"})); expect(createSkill).toHaveBeenCalledOnce();
  });

  it("late shared creation success after identity change does not show success", async () => {
    const view = renderPage(); let resolve!: (value: object) => void; createSkill.mockReturnValueOnce(new Promise(done => {resolve = done;}));
    fireEvent.click(screen.getByRole("button", {name: "新建 / 导入"}));
    fireEvent.change(screen.getByLabelText(/名称/), {target: {value: "manual-owned"}}); fireEvent.change(screen.getByLabelText(/描述/), {target: {value: "Owned shared"}});
    fireEvent.click(screen.getByRole("button", {name: "保存"})); mocks.identity = "tenant-b/user-b"; view.rerender(<TenantAdminSkillsPage />);
    await act(async () => resolve({})); expect(mocks.success).not.toHaveBeenCalled();
  });

  it("splits built-in and custom skills into separate tabs", () => {
    renderPage();

    expect(screen.getByRole("heading", { name: "技能管理" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /系统内置/ })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /团队技能/ })).toBeInTheDocument();
    expect(screen.getByText("builtin-skill")).toBeInTheDocument();

    activateTab("团队技能 (1)");

    expect(screen.getByText("custom-skill-a")).toBeInTheDocument();
  });

  it("creates a manual tenant skill with description and instructions", async () => {
    createSkill.mockResolvedValueOnce({});
    renderPage();

    fireEvent.click(screen.getByRole("button", { name: "新建 / 导入" }));
    fireEvent.change(screen.getByLabelText(/名称/), { target: { value: "jira-analyst" } });
    fireEvent.change(screen.getByLabelText(/描述/), { target: { value: "Analyze jira issues" } });
    fireEvent.change(screen.getByLabelText("指令"), { target: { value: "Review tickets and summarize blockers" } });
    fireEvent.change(screen.getByLabelText("绑定工具"), { target: { value: "jira, confluence" } });
    fireEvent.click(screen.getByRole("button", { name: "保存" }));

    expect(createSkill).toHaveBeenCalledWith({
      name: "jira-analyst",
      description: "Analyze jira issues",
      instructions: "Review tickets and summarize blockers",
      enabled: true,
      bound_tools: ["jira", "confluence"],
      prompt_template: null,
      strategy: "default",
    });
  });

  it("imports a .zip skill archive from the dialog", async () => {
    importSkill.mockResolvedValueOnce({});
    renderPage();

    fireEvent.click(screen.getByRole("button", { name: "新建 / 导入" }));
    activateTab("导入");

    const file = new File(["zip-content"], "demo-skill.zip", { type: "application/zip" });
    const input = document.querySelector('input[type="file"]');
    if (!input) {
      throw new Error("file input not found");
    }
    fireEvent.change(input, { target: { files: [file] } });
    fireEvent.click(screen.getByRole("button", { name: "导入" }));

    expect(importSkill).toHaveBeenCalledWith(file);
  });

  it("keeps import button disabled until archive is selected", () => {
    renderPage();

    fireEvent.click(screen.getByRole("button", { name: "新建 / 导入" }));
    activateTab("导入");

    expect(screen.getByRole("button", { name: "导入" })).toBeDisabled();

    const input = document.querySelector('input[type="file"]');
    if (!input) {
      throw new Error("file input not found");
    }

    const file = new File(["zip-content"], "demo-skill.zip", { type: "application/zip" });
    fireEvent.change(input, { target: { files: [file] } });

    expect(screen.getByRole("button", { name: "导入" })).not.toBeDisabled();
  });
  it.each(["tenant", "close"])("does not apply an old upload response after %s changes", async kind => {
    const view = renderPage();
    let resolve!: (value: unknown) => void;
    importSkill.mockReturnValueOnce(new Promise(done => {resolve = done;}));
    fireEvent.click(screen.getByRole("button", {name: "新建 / 导入"}));
    activateTab("导入");
    const file = new File(["zip"], "demo.zip");
    fireEvent.change(document.querySelector('input[type="file"]')!, {target: {files: [file]}});
    fireEvent.click(screen.getByRole("button", {name: "导入"}));
    expect(importSkill).toHaveBeenCalledOnce();
    if (kind === "tenant") {
      mocks.identity = "tenant-b/user-a";
      view.rerender(<TenantAdminSkillsPage />);
    } else {
      fireEvent.click(screen.getByRole("button", {name: "取消"}));
    }
    await act(async () => resolve({}));
    expect(mocks.success).not.toHaveBeenCalled();
  });

  it("shared edit sends the listed instance and digest and blocks retry until inspection", async () => {
    renderPage();
    patchSkill.mockRejectedValueOnce(new SkillMutationError(503, "skill:current", true));
    activateTab("团队技能 (1)");
    fireEvent.click(screen.getByRole("button", {name: "编辑"}));
    fireEvent.click(screen.getByRole("button", {name: "保存"}));
    const inspect = await screen.findByRole("button", {name: "重新检查资源列表"});
    expect(screen.getByRole("button", {name: "保存"})).toBeDisabled();
    expect(patchSkill.mock.calls[0]?.[0]).toMatchObject({expected_resource_id: "skill:current", expected_file_sha256: "a".repeat(64)});
    fireEvent.click(inspect);
    expect(patchSkill).toHaveBeenCalledOnce();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

});
