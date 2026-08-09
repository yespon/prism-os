import { describe, expect, it, vi } from "vitest";

import { fireEvent, render, screen } from "@/test/utils";

import { TenantAdminSkillsPage } from "./tenant-admin-skills-page";

const mocks = vi.hoisted(() => ({
  useAvailableSkills: vi.fn(),
  useCreateTenantSkill: vi.fn(),
  useDeleteTenantSkill: vi.fn(),
  useImportTenantSkill: vi.fn(),
  usePatchTenantSkill: vi.fn(),
  useUpdateTenantSkill: vi.fn(),
}));

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

  const renderPage = () => {
    createSkill.mockReset();
    importSkill.mockReset();
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
    mocks.usePatchTenantSkill.mockReturnValue({ mutateAsync: vi.fn() });
    mocks.useUpdateTenantSkill.mockReturnValue({ mutateAsync: vi.fn() });

    return render(<TenantAdminSkillsPage />);
  };

  const activateTab = (name: string) => {
    const tab = screen.getByRole("tab", { name });
    fireEvent.pointerDown(tab);
    fireEvent.mouseDown(tab);
    fireEvent.click(tab);
  };

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
});
