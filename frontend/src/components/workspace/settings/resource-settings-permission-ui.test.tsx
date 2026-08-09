import { describe, expect, it, vi } from "vitest";

import { render, screen } from "@/test/utils";

import { ModelLifecycleSettingsPage } from "./model-lifecycle-settings-page";
import { SkillSettingsPage } from "./skill-settings-page";
import { ToolSettingsPage } from "./tool-settings-page";

const mocks = vi.hoisted(() => ({
  useI18n: vi.fn(),
  useCurrentTenant: vi.fn(),
  useAvailableModels: vi.fn(),
  useRegisterModel: vi.fn(),
  useUpdateModel: vi.fn(),
  useDeleteModel: vi.fn(),
  useDeleteTenantModel: vi.fn(),
  useUpdateTenantModel: vi.fn(),
  useTestModelConnection: vi.fn(),
  getDisabledModelsStore: vi.fn(),
  setDisabledModelsStore: vi.fn(),
  useAvailableMcpConfig: vi.fn(),
  useEnableMCPServer: vi.fn(),
  useCreateMCPServer: vi.fn(),
  useUpdateSingleMCPServer: vi.fn(),
  useDeleteMCPServer: vi.fn(),
  usePingMCPServer: vi.fn(),
  useUpdateSingleTenantMCPServer: vi.fn(),
  useDeleteTenantMCPServer: vi.fn(),
  useEnableTenantMCPServer: vi.fn(),
  useAvailableSkills: vi.fn(),
  useUpdateTenantSkill: vi.fn(),
}));

vi.mock("@/core/i18n/hooks", () => ({
  useI18n: mocks.useI18n,
}));

vi.mock("@/core/tenants/hooks", () => ({
  useCurrentTenant: mocks.useCurrentTenant,
}));

vi.mock("@/core/models/hooks", () => ({
  useAvailableModels: mocks.useAvailableModels,
  useRegisterModel: mocks.useRegisterModel,
  useUpdateModel: mocks.useUpdateModel,
  useDeleteModel: mocks.useDeleteModel,
  useDeleteTenantModel: mocks.useDeleteTenantModel,
  useUpdateTenantModel: mocks.useUpdateTenantModel,
  useTestModelConnection: mocks.useTestModelConnection,
  getDisabledModelsStore: mocks.getDisabledModelsStore,
  setDisabledModelsStore: mocks.setDisabledModelsStore,
}));

vi.mock("@/core/mcp/hooks", () => ({
  useAvailableMcpConfig: mocks.useAvailableMcpConfig,
  useEnableMCPServer: mocks.useEnableMCPServer,
  useCreateMCPServer: mocks.useCreateMCPServer,
  useUpdateSingleMCPServer: mocks.useUpdateSingleMCPServer,
  useDeleteMCPServer: mocks.useDeleteMCPServer,
  usePingMCPServer: mocks.usePingMCPServer,
  useUpdateSingleTenantMCPServer: mocks.useUpdateSingleTenantMCPServer,
  useDeleteTenantMCPServer: mocks.useDeleteTenantMCPServer,
  useEnableTenantMCPServer: mocks.useEnableTenantMCPServer,
}));

vi.mock("@/core/skills/hooks", () => ({
  useAvailableSkills: mocks.useAvailableSkills,
  useUpdateTenantSkill: mocks.useUpdateTenantSkill,
}));

vi.mock("@/env", () => ({
  env: { NEXT_PUBLIC_STATIC_WEBSITE_ONLY: "false" },
}));

describe("Resource settings permission UI", () => {
  it("hides model/tool/skill creation entry for tenant members", () => {
    mocks.useI18n.mockReturnValue({
      t: {
        common: {
          loading: "loading",
          public: "public",
          custom: "custom",
        },
        settings: {
          modelLifecycle: {
            title: "模型设置",
            description: "模型描述",
            register: {
              open: "新建模型",
              emptyHint: "empty",
            },
          },
          tools: {
            title: "工具设置",
            description: "工具描述",
            registerTool: "新建 Tool",
            noDescription: "none",
            active: "active",
            disabled: "disabled",
            edit: "edit",
            builtIn: "built-in",
            deleteConfirm: "delete",
          },
          skills: {
            title: "技能设置",
            description: "技能描述",
            createSkill: "创建 Skill",
            emptyTitle: "empty title",
            emptyDescription: "empty desc",
            emptyButton: "empty button",
          },
        },
      },
    });

    mocks.useCurrentTenant.mockReturnValue({ data: { tenant_id: "tenant-a", role: "tenant_member" } });

    mocks.useAvailableModels.mockReturnValue({ models: [], isLoading: false, error: null });
    mocks.useRegisterModel.mockReturnValue({ mutateAsync: vi.fn(), isPending: false });
    mocks.useUpdateModel.mockReturnValue({ mutateAsync: vi.fn(), isPending: false });
    mocks.useDeleteModel.mockReturnValue({ mutateAsync: vi.fn(), isPending: false });
    mocks.useDeleteTenantModel.mockReturnValue({ mutateAsync: vi.fn(), isPending: false });
    mocks.useUpdateTenantModel.mockReturnValue({ mutateAsync: vi.fn(), isPending: false });
    mocks.useTestModelConnection.mockReturnValue({ mutateAsync: vi.fn(), isPending: false });
    mocks.getDisabledModelsStore.mockReturnValue([]);
    mocks.setDisabledModelsStore.mockReturnValue(undefined);

    mocks.useAvailableMcpConfig.mockReturnValue({
      config: { mcp_servers: {} },
      rawArray: [],
      isLoading: false,
      error: null,
    });
    mocks.useEnableMCPServer.mockReturnValue({ mutate: vi.fn() });
    mocks.useCreateMCPServer.mockReturnValue({ mutateAsync: vi.fn(), isPending: false });
    mocks.useUpdateSingleMCPServer.mockReturnValue({ mutateAsync: vi.fn(), isPending: false });
    mocks.useDeleteMCPServer.mockReturnValue({ mutate: vi.fn() });
    mocks.usePingMCPServer.mockReturnValue({ mutateAsync: vi.fn(), isPending: false });
    mocks.useUpdateSingleTenantMCPServer.mockReturnValue({ mutateAsync: vi.fn(), isPending: false });
    mocks.useDeleteTenantMCPServer.mockReturnValue({ mutate: vi.fn() });
    mocks.useEnableTenantMCPServer.mockReturnValue({ mutate: vi.fn() });

    mocks.useAvailableSkills.mockReturnValue({ skills: [], isLoading: false, error: null });
    mocks.useUpdateTenantSkill.mockReturnValue({ mutate: vi.fn() });

    const { rerender } = render(<ModelLifecycleSettingsPage />);
    expect(screen.queryByRole("button", { name: "新建模型" })).not.toBeInTheDocument();

    rerender(<ToolSettingsPage />);
    expect(screen.queryByRole("button", { name: "新建 Tool" })).not.toBeInTheDocument();

    rerender(<SkillSettingsPage />);
    expect(screen.queryByRole("button", { name: "创建 Skill" })).not.toBeInTheDocument();
  });
});
